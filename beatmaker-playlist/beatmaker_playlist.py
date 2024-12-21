import aiohttp
from dataclasses import dataclass, asdict
import uuid
import redis.asyncio as redis
import json
import logging

from utils import Match, Playlist
from spotify import Spotify
from genius import Genius
import secret_keys


@dataclass
class BeatmakerPlaylistResults:
    """"""

    genius_beatmaker_name: str
    genius_beatmaker_id: int
    genius_songs_produced: list
    genius_songs_not_produced: list
    matches: list[Match]
    playlist: Playlist


class BeatmakerPlaylist:
    """"""

    def __init__(self, client: aiohttp.ClientSession, user_id: str, debug: bool = False, faster_tests: bool = False):
        """"""
        self.user_id = user_id
        self.redis_client = redis.Redis(
            host=secret_keys.REDIS_HOST, port=secret_keys.REDIS_PORT, db=secret_keys.REDIS_DB
        )
        self._spotify: Spotify = Spotify(session=client, debug=debug, faster_tests=faster_tests)
        self._genius: Genius = Genius(session=client, debug=debug, faster_tests=faster_tests)

    def get_spotify_auth_url(self):
        """"""
        return self._spotify.get_authorize_url()

    async def get_spotify_access_token(self, code):
        """"""
        return await self._spotify.get_access_token(code=code)

    async def get_spotify_user_profile(self):
        """"""
        return await self._spotify.get_user_profile()

    async def get_spotify_profile_image(self):
        return await self._spotify.get_user_profile_image()

    def set_spotify_access_token_response(self, access_token_response: dict) -> None:
        """"""
        self._spotify.set_access_token_response(access_token_response=access_token_response)

    async def update_progress(self, task_id, progress, current_step):
        """Update task progress in Redis with user-specific namespace"""
        task_key = f"user:{self.user_id}:task:{task_id}"
        await self.redis_client.hset(task_key, mapping={"progress": progress, "current_step": current_step})
        await self.redis_client.expire(task_key, 3600)  # 1 hour expiration

    async def set_result(self, task_id, result):
        """Set task result with user-specific namespacing"""
        task_key = f"user:{self.user_id}:task:{task_id}"
        await self.redis_client.hset(task_key, mapping={"result": json.dumps(result), "completed": 1})
        await self.redis_client.expire(task_key, 3600)

    async def set_error(self, task_id, error):
        """Set error state with user-specific namespacing"""
        task_key = f"user:{self.user_id}:task:{task_id}"
        await self.redis_client.hset(task_key, mapping={"error": error, "completed": 1})
        await self.redis_client.expire(task_key, 3600)

    async def get_state(self, task_id):
        """Retrieve task state with user-specific namespacing"""
        task_key = f"user:{self.user_id}:task:{task_id}"
        task_state = await self.redis_client.hgetall(task_key)
        decoded_state = {k.decode(): v.decode() if isinstance(v, bytes) else v for k, v in task_state.items()}
        if "result" in decoded_state:
            decoded_state["result"] = json.loads(decoded_state["result"])
        dict = {
            "task_id": task_id,
            "progress": int(decoded_state.get("progress", 0)),
            "current_step": decoded_state.get("current_step"),
            "completed": bool(int(decoded_state.get("completed", 0))),
            "result": decoded_state.get("result"),
            "error": decoded_state.get("error"),
        }
        return dict

    async def make_playlist(self, beatmaker_name: str, task_id: str) -> BeatmakerPlaylistResults:
        """"""
        try:
            await self.update_progress(task_id, 0, f"Searching {beatmaker_name} on Genius")
            # Get producer id from name
            genius_beatmaker_name, genius_beatmaker_id = await self._genius.get_producer_id(beatmaker_name)

            # Get all songs from producer
            await self.update_progress(task_id, 10, f"Getting all songs from {beatmaker_name} on Genius")
            genius_beatmaker_songs = await self._genius.get_songs(beatmaker_id=genius_beatmaker_id)

            # Build song search list (title + artist name) for Spotify
            await self.update_progress(task_id, 20, f"Removing songs not produced by {beatmaker_name}")
            genius_songs_produced, genius_songs_not_produced = await self._genius.build_song_search(
                genius_beatmaker_songs, genius_beatmaker_id
            )

            # Build the list of Spotify song IDs to add to the playlist
            await self.update_progress(task_id, 30, "Matching songs on Spotify")
            matches = await self._spotify.build_song_id_list(genius_songs_produced)

            # Get producer image url from Genius
            await self.update_progress(task_id, 70, "Downloading beatmaker image from Genius")
            beatmaker_image_url = await self._genius.get_producer_image_url(genius_beatmaker_id)

            # Create playlist
            await self.update_progress(task_id, 80, "Creating Spotify playlist")
            playlist: Playlist = await self._spotify.create_playlist(genius_beatmaker_name, beatmaker_image_url)

            # Add tracks by ids
            await self.update_progress(task_id, 90, "Adding tracks to Spotify playlist")
            await self._spotify.add_tracks(playlist, matches)
            await self.update_progress(task_id, 100, "Finished!")

            beatmaker_playlist_results = BeatmakerPlaylistResults(
                genius_beatmaker_name,
                genius_beatmaker_id,
                genius_songs_produced,
                genius_songs_not_produced,
                matches,
                playlist,
            )

            # await self.set_result(task_id, asdict(beatmaker_playlist_results))
            await self.set_result(task_id, {"playlist_url": playlist.url})
            return beatmaker_playlist_results
        except Exception as e:
            logging.info(f"Exception raised in make_playlist: {e}")
            await self.set_error(task_id, str(e))
            raise
