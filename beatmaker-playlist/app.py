from quart import Quart, render_template, redirect, request, session, url_for, jsonify, websocket
from quart_cors import cors
import asyncio
import redis.asyncio as redis
import logging
import aiohttp
import secrets
from typing import Optional
import uuid
import json

import secret_keys
from beatmaker_playlist import BeatmakerPlaylist, BeatmakerPlaylistResults


app = Quart(__name__)
app = cors(app, allow_origin=["http://127.0.0.1:8000"], allow_credentials=True)
app.secret_key = secrets.token_hex(16)
app.client = None

playlist_tasks = {}


@app.before_serving
async def startup():
    """"""
    app.client = aiohttp.ClientSession()


@app.after_serving
async def close():
    """Before terminating the app, shutdown the needed objects"""
    await app.client.close()


@app.route("/")
async def index():
    """Base endpoint of the application"""

    # If user_id doesn't exist, this is the entry point for the user
    if "user_id" not in session:
        logging.info("Creating user_id and BeatmakerPlaylist object")
        user_id = str(uuid.uuid4())
        session["user_id"] = user_id
        playlist_tasks[user_id] = BeatmakerPlaylist(
            client=app.client, user_id=user_id, faster_tests=secret_keys.FASTER_TESTS
        )

    user_id = session["user_id"]
    playlist_manager: BeatmakerPlaylist = playlist_tasks.get(user_id)

    # If access_token doesn't exist, user is not logged in
    if "access_token" not in session:
        return await render_template("login.html")

    user = await playlist_manager.get_spotify_user_profile()
    profile_image = await playlist_manager.get_spotify_profile_image()
    return await render_template("homepage.html", profile_image=profile_image, user=user)


@app.route("/login")
async def login():
    """Endpoint to login to Spotify"""

    # If user_id or access_token doesn't exist, go back to index
    if "user_id" not in session:
        return redirect(url_for("index"))

    # Else, user has a session and is logged in to Spotify.
    # Generate the OAuth2 URL and redirect the user it.
    user_id = session["user_id"]
    playlist_manager: BeatmakerPlaylist = playlist_tasks.get(user_id)
    auth_url = playlist_manager.get_spotify_auth_url()
    return redirect(auth_url)


@app.route("/callback")
async def callback():
    """Callback endpoint of the Spotify OAuth2 flow"""
    if "user_id" not in session:
        return redirect(url_for("index"))

    code = request.args.get("code")

    user_id = session["user_id"]
    playlist_manager: BeatmakerPlaylist = playlist_tasks.get(user_id)
    # TODO: try..except for HTTPException ?
    access_token = await playlist_manager.get_spotify_access_token(code)

    if not access_token:
        return redirect(url_for("index"))

    session["access_token"] = access_token
    return redirect(url_for("index"))


@app.route("/create_playlist", methods=["POST"])
async def create_playlist():
    """Endpoint to start the make_playlist task"""
    logging.info("Create playlist request received")
    logging.info(f"Session: {session}")
    logging.info(f"User ID in session: {session.get('user_id')}")

    if "user_id" not in session:
        logging.info("No session linked to this request")
        return jsonify({"error": "No session linked to this request"}), 400
    if "access_token" not in session:
        logging.info("Not authenticated")
        return jsonify({"error": "Not authenticated"}), 401

    # Get Beatmaker name from input form
    form_data = await request.get_json()
    beatmaker_name = form_data.get("beatmaker_name")
    if not beatmaker_name:
        logging.info("No beatmaker name given")
        return jsonify({"error": "No beatmaker name given"}), 400

    # Create task_id
    task_id = str(uuid.uuid4())
    user_id = session["user_id"]
    playlist_manager: BeatmakerPlaylist = playlist_tasks.get(user_id)
    app.add_background_task(playlist_manager.make_playlist, beatmaker_name, task_id)

    logging.info(f"user_id: {user_id}, task_id: {task_id}")
    return (
        jsonify(
            {
                "task_id": task_id,
                "user_id": user_id,
                "message": "Task started successfully",
            }
        ),
        202,
    )


@app.route("/task-result/<user_id>/<task_id>")
async def get_task_result(user_id, task_id):
    """
    Endpoint to retrieve the final task result
    """
    logging.info("Trying to get task result")
    # Verify user authentication
    if "access_token" not in session or session["user_id"] != user_id:
        return jsonify({"error": "Unauthorized"}), 401

    try:
        playlist_manager: BeatmakerPlaylist = playlist_tasks.get(user_id)
        task_state = await playlist_manager.get_state(task_id)
        if not task_state["completed"]:
            return jsonify({"error": "Task not yet completed"}), 400
        if task_state["error"]:
            return jsonify({"status": "error", "error": task_state["error"]}), 500
        return jsonify({"status": "success", "result": task_state["result"]})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.websocket("/task-status/<user_id>/<task_id>")
async def get_task_status(user_id, task_id):
    """
    Endpoint to stream task status
    """
    try:
        logging.info(f"Opening websocker to get task status for used_id: {user_id}")
        logging.info(f"Session contents: {session}")

        if not session:
            logging.error("No session found")
            await websocket.close(1008, "No session found")
            return

        if "access_token" not in session:
            logging.error("No access token in session")
            await websocket.close(1008, "No access token")
            return

        if "user_id" not in session:
            logging.error("No user_id in session")
            await websocket.close(1008, "No user_id")
            return

        if session["user_id"] != user_id:
            logging.error("Unauthorized WebSocket connection attempt")
            await websocket.close(1008, "Unauthorized")
            return

        await websocket.accept()
        logging.info("WebSocket connection accepted")

        playlist_manager: BeatmakerPlaylist = playlist_tasks.get(user_id)
        if not playlist_manager:
            logging.error(f"No playlist manager found for user_id: {user_id}")
            await websocket.send(json.dumps({"error": "No task found"}))
            await websocket.close(1011, "No task found")
            return

        try:
            playlist_manager: BeatmakerPlaylist = playlist_tasks.get(user_id)
            task_state = await playlist_manager.get_state(task_id)

            while True:
                try:
                    task_state = await playlist_manager.get_state(task_id)
                    # logging.info(f"Task state: {task_state}")

                    await websocket.send(json.dumps(task_state))

                    if task_state["completed"] or task_state.get("error"):
                        logging.info("Task completed or error occurred, closing connection")
                        break

                    await asyncio.sleep(1)

                except Exception as e:
                    logging.error(f"Error during WebSocket communication: {e}")
                    await websocket.send(json.dumps({"error": str(e)}))
                    break

        except Exception as e:
            print(f"WebSocket error: {e}")
            await websocket.close(1011, str(e))

    except Exception as e:
        logging.error(f"WebSocket error: {e}")
        await websocket.close(1011, str(e))
    finally:
        await websocket.close(1011)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="{asctime} - {levelname} - {message}", style="{")
    app.run(debug=True, port=8000)
