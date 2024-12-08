import aiohttp
from dataclasses import dataclass

from utils import Match, Playlist
from spotify import Spotify
from genius import Genius


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

    def __init__(self, client: aiohttp.ClientSession, debug: bool = False, faster_tests: bool = False):
        """"""
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

    async def make_playlist(self, beatmaker_name: str) -> BeatmakerPlaylistResults:
        """"""
        # Get producer id from name
        genius_beatmaker_name, genius_beatmaker_id = await self._genius.get_producer_id(beatmaker_name)

        # Get all songs from producer
        genius_beatmaker_songs = await self._genius.get_songs(beatmaker_id=genius_beatmaker_id)

        # Build song search list (title + artist name) for Spotify
        genius_songs_produced, genius_songs_not_produced = await self._genius.build_song_search(
            genius_beatmaker_songs, genius_beatmaker_id
        )

        # Build the list of Spotify song IDs to add to the playlist
        matches = await self._spotify.build_song_id_list(genius_songs_produced)

        # Get producer image url from Genius
        beatmaker_image_url = await self._genius.get_producer_image_url(genius_beatmaker_id)

        # Create playlist
        playlist: Playlist = await self._spotify.create_playlist(genius_beatmaker_name, beatmaker_image_url)

        # Add tracks by ids
        await self._spotify.add_tracks(playlist, matches)

        beatmaker_playlist_results = BeatmakerPlaylistResults(
            genius_beatmaker_name,
            genius_beatmaker_id,
            genius_songs_produced,
            genius_songs_not_produced,
            matches,
            playlist,
        )
        return beatmaker_playlist_results
