from quart import Quart, render_template, redirect, request, session, url_for
import logging
import aiohttp
from typing import Optional

import secret_keys
from beatmaker_playlist import BeatmakerPlaylist, BeatmakerPlaylistResults


class CustomQuart(Quart):
    client: Optional[aiohttp.ClientSession] = None
    playlist_manager: Optional[BeatmakerPlaylist] = None


app = CustomQuart(__name__)
app.secret_key = secret_keys.FLASK_SECRET_KEY


@app.before_serving
async def startup():
    app.client = aiohttp.ClientSession()
    app.playlist_manager = BeatmakerPlaylist(client=app.client, faster_tests=secret_keys.FASTER_TESTS)


@app.after_serving
async def close():
    await app.client.close()


@app.route("/")
async def index():
    return await render_template("homepage.html", title="Home")


@app.route("/login")
async def login():
    """"""
    auth_url = app.playlist_manager.get_spotify_auth_url()
    return redirect(auth_url)


@app.route("/callback")
async def callback():
    """"""
    code = request.args.get("code")
    access_token = await app.playlist_manager.get_spotify_access_token(code)
    if not access_token:
        return redirect(url_for("login"))
    return redirect(url_for("beatmaker"))


@app.route("/beatmaker")
async def beatmaker():
    """"""
    user = await app.playlist_manager.get_spotify_user_profile()
    profile_image = await app.playlist_manager.get_spotify_profile_image()

    return await render_template("logged_in.html", profile_image=profile_image, user=user)


@app.route("/create_playlist", methods=["POST"])
async def create_playlist():
    """"""
    beatmaker_name = (await request.form).get("user_input")  # Récupérer la valeur de l'input
    if not beatmaker_name:
        return "Error : no beatmaker name given", 400

    beatmaker_playlist_results = await app.playlist_manager.make_playlist(beatmaker_name)

    return await render_template(
        "create_playlist.html",
        playlist_name=beatmaker_playlist_results.playlist.name,
        playlist_url=beatmaker_playlist_results.playlist.url,
        playlist_image=beatmaker_playlist_results.playlist.image,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="{asctime} - {levelname} - {message}", style="{")
    app.run(debug=True, port=8000)
