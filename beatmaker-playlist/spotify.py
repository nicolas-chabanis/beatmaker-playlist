import datetime
from typing import Optional
from urllib import parse
import base64
import logging
import json
import asyncio
import aiohttp
import textdistance
import math

from http_client import HttpClient
import secret_keys
from utils import Track, normalize_string, Match, Playlist, resize_image, compress_image


class Spotify(HttpClient):
    """"""

    BASE_URL = "https://api.spotify.com/v1"
    SCOPES = "user-read-private user-read-email playlist-modify-public, playlist-modify-public, ugc-image-upload"
    OAUTH_AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
    OAUTH_TOKEN_URL = "https://accounts.spotify.com/api/token"

    def __init__(self, session: aiohttp.ClientSession, debug: bool = False, faster_tests: bool = False) -> None:
        """"""
        super().__init__(session=session)
        self._access_token_response = None
        self._user = None
        self._debug = debug
        self._faster_tests = faster_tests

    def set_access_token_response(self, access_token_response: dict) -> dict:
        """"""
        self._access_token_response = access_token_response

    def get_authorize_url(self) -> str:
        """"""
        payload = {
            "client_id": secret_keys.SPOTIFY_CLIENT_ID,
            "response_type": "code",
            "redirect_uri": secret_keys.SPOTIFY_REDIRECT_URI,
            "scope": self.SCOPES,
        }
        urlparams = parse.urlencode(payload)
        url = f"{self.OAUTH_AUTHORIZE_URL}?{urlparams}"
        return url

    async def get_access_token(self, code) -> str:
        """"""
        url = self.OAUTH_TOKEN_URL
        data = {
            "redirect_uri": secret_keys.SPOTIFY_REDIRECT_URI,
            "code": code,
            "grant_type": "authorization_code",
        }
        auth_header = base64.b64encode(
            str(secret_keys.SPOTIFY_CLIENT_ID + ":" + secret_keys.SPOTIFY_CLIENT_SECRET).encode("ascii")
        )
        headers = {
            "content-type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {auth_header.decode('ascii')}",
        }
        response = await self.async_post(url=url, data=data, headers=headers)
        logging.info(json.dumps(response))
        self._access_token_response = response
        return response.get("access_token", None)

    async def get_user_profile(self) -> dict:
        """"""
        token = self._access_token_response.get("access_token", "")
        url = f"{self.BASE_URL}/me"
        response = await self.async_get(url=url, access_token=token)
        logging.info(json.dumps(response))
        self._user = response
        return response

    async def get_user_profile_image(self) -> str:
        """"""
        profile_images = self._user.get("images", {})
        largest_image = max(profile_images, key=lambda img: img.get("height", 0))
        largest_image_url = largest_image.get("url", "")
        logging.info(f"Downloading profile image at {largest_image_url}")
        profile_image_bytes = await self.async_get(url=largest_image_url)
        profile_image_bytes_resized = resize_image(profile_image_bytes, width=150, height=150)
        profile_image_b64_str = base64.b64encode(profile_image_bytes_resized).decode("utf-8")
        profile_image = f"data:image/jpeg;base64,{profile_image_b64_str}"
        return profile_image

    async def build_song_id_list(self, tracks: list[Track]) -> list[Match]:
        """"""
        coros = []
        for track in tracks:
            coro = self.find_song(track=track)
            coros.append(coro)

        matches = await asyncio.gather(*coros)
        return matches

    async def find_song(self, track: Track) -> Match:
        """"""
        query = track.artist + " " + track.title
        query_result = await self.search(query)
        match = await self.find_match(track, query_result)
        return match

    async def search(self, query: str) -> dict:
        """"""
        token = self._access_token_response.get("access_token", None)
        query = query[0:100]  # Spotify limitation
        url = f"{self.BASE_URL}/search"
        limit = 50 if not self._faster_tests else 5
        market = self._user.get("country")
        params = {"query": query, "type": "track", "market": market, "limit": limit}
        result = await self.async_get(url=url, access_token=token, params=params)
        return result

    async def find_match(self, track: Track, query_result: json) -> Match:
        """"""
        logging.info(f"Searching for track {repr(track)} on Spotify...")
        items = query_result.get("tracks", {}).get("items", [])
        for item in items:
            item_id = item.get("id")
            item_title = item.get("name")
            item_artists = item.get("artists", [])
            for item_artist in item_artists:
                item_artist_name = item_artist.get("name")
                item_track = Track(item_artist_name, item_title)
                if self.tracks_match(track, item_track):
                    logging.info(f"    -> {repr(track)} * {repr(item_track)}")
                    return Match(track, item_id)
        logging.info("    No match found :(")
        return Match(track, None)

    def tracks_match(self, track: Track, item_track: Track) -> bool:
        """"""
        dis = textdistance.jaccard.normalized_distance
        overlap = textdistance.overlap.normalized_distance

        artist = normalize_string(track.artist)
        title = normalize_string(track.title)

        item_artist = normalize_string(item_track.artist)
        item_title = normalize_string(item_track.title)

        dis_artist = dis(artist, item_artist)
        dis_title = dis(title, item_title)
        overlap_artist = overlap(artist, item_artist)
        overlap_title = overlap(title, item_title)

        match = (overlap_title <= 0.3) & (overlap_artist <= 0.3) & (dis_artist <= 0.3) & (dis_title <= 0.5)

        track_match = (
            f"    {repr(track)} * {repr(item_track)} : {dis_artist} {dis_title} {overlap_artist} {overlap_title}"
        )
        logging.debug(track_match)

        return match

    async def get_tracks(self, id: str) -> dict:
        """"""
        token = self._access_token_response.get("access_token", None)
        url = f"{self.BASE_URL}/tracks/{id}"
        market = self._user.get("country")
        params = {"market": market}
        result = await self.async_get(url=url, access_token=token, params=params)
        return result

    async def create_playlist(self, beatmaker_name, playlist_image_url) -> Playlist:
        """"""
        response = await self._create_playlist(beatmaker_name=beatmaker_name)
        playlist_id = response.get("id")
        playlist_name = response.get("name")
        playlist_url = response.get("external_urls", {}).get("spotify", "")
        playlist_image = await self._upload_cover_image_playlist(playlist_id, playlist_image_url)
        logging.info(f"Playlist created with id {playlist_id}")
        return Playlist(playlist_id, playlist_name, playlist_url, playlist_image)

    async def _create_playlist(self, beatmaker_name: str) -> dict:
        """"""
        logging.info(f"Creating playlist for beatmaker {beatmaker_name}")
        token = self._access_token_response.get("access_token", None)
        user_id = self._user.get("id")
        url = f"{self.BASE_URL}/users/{user_id}/playlists"
        playlist_name = "Produced by " + beatmaker_name
        now = datetime.datetime.now()
        description = "Songs produced by " + beatmaker_name + ", creation date : " + now.strftime("%d/%m/%Y")
        data = {"name": playlist_name, "description": description, "public": True}
        data = json.dumps(data, separators=(",", ":"), ensure_ascii=True)
        headers = {"Content-Type": "application/json"}
        response = await self.async_post(url=url, data=data, access_token=token, headers=headers)
        return response

    async def _upload_cover_image_playlist(self, playlist_id: str, playlist_image_url: str) -> str:
        """"""
        logging.info(f"Uploading cover image to playlist {playlist_id}")

        # Download playlist image from Genius.com
        playlist_image_bytes = await self.async_get(url=playlist_image_url)

        # Upload playlist image to Spotify playlist, resized to 300x300 and with a maximum size of 256 kB
        playlist_image_compressed = compress_image(playlist_image_bytes, 256, 300, 300)
        playlist_image_b64 = base64.b64encode(playlist_image_compressed)
        token = self._access_token_response.get("access_token", None)
        url = f"{self.BASE_URL}/playlists/{playlist_id}/images"
        headers = {"Content-Type": "image/jpeg"}
        await self.async_put(url=url, data=playlist_image_b64, access_token=token, headers=headers)

        # Return playlist image for frontend, resized to 200x200
        playlist_image_bytes_resized = resize_image(playlist_image_bytes, width=200, height=200)
        playlist_image_b64_str = base64.b64encode(playlist_image_bytes_resized).decode("utf-8")
        playlist_image = f"data:image/jpeg;base64,{playlist_image_b64_str}"
        return playlist_image

    async def add_tracks(self, playlist: Playlist, matches: list[Match]) -> None:
        logging.info(f"Adding tracks to playlist {playlist.id}")
        token = self._access_token_response.get("access_token", None)
        url = f"{self.BASE_URL}/playlists/{playlist.id}/tracks"
        uris = [f"spotify:track:{match.id}" for match in matches if match.id is not None]
        number_of_batches = math.ceil(len(uris) / 100)  # Spotify limit : 100 items per request
        for batch in range(number_of_batches):
            if batch + 1 == number_of_batches:  # Last batch
                uri_batch = uris[batch * 100 :]
            else:
                uri_batch = uris[batch * 100 : (batch + 1) * 100]
            logging.info(f"    Batch {batch+1}/{number_of_batches}: {len(uri_batch)}")
            data = {"uris": uri_batch}
            data = json.dumps(data, separators=(",", ":"), ensure_ascii=True)
            headers = {"Content-Type": "application/json"}
            await self.async_post(url=url, data=data, access_token=token, headers=headers)
