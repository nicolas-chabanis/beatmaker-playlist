import datetime
from typing import Optional
from urllib import parse
import base64
import logging
import json
import asyncio
import aiohttp
import textdistance

from http_client import HttpClient
import secret_keys
from utils import write_json, Track, normalize_string, Match


class Spotify(HttpClient):
    """"""

    BASE_URL = "https://api.spotify.com/v1"
    SCOPES = "user-read-private user-read-email playlist-modify-public, playlist-modify-public, ugc-image-upload"
    OAUTH_AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
    OAUTH_TOKEN_URL = "https://accounts.spotify.com/api/token"

    def __init__(self, session: aiohttp.ClientSession, debug: bool = False, faster_tests: bool = False):
        """"""
        super().__init__(session=session)
        self._access_token_response = None
        self._user = None
        self._debug = debug
        self._faster_tests = faster_tests

    def set_access_token_response(self, access_token_response: dict):
        """"""
        self._access_token_response = access_token_response

    def get_authorize_url(self):
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

    async def get_access_token(self, code) -> None:
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

    async def get_user_profile(self):
        """"""
        token = self._access_token_response.get("access_token")
        url = f"{self.BASE_URL}/me"
        response = await self.async_get(url=url, access_token=token)
        logging.info(json.dumps(response))
        self._user = response
        return response

    async def get_user_profile_image(self) -> str:
        """"""
        profile_images = self._user.get("images", {})
        profile_image_url = ""
        for images in profile_images:
            if images.get("height", None) == 300:  # TODO: Robustify
                profile_image_url = images.get("url", "")
        logging.info(f"Downloading profile image at {profile_image_url}")
        profile_image_bytes = await self.async_get(url=profile_image_url)
        profile_image_encoded = base64.b64encode(profile_image_bytes).decode("utf-8")
        profile_image = f"data:image/jpeg;base64,{profile_image_encoded}"
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
        if type(query_result) is not dict:
            logging.error(f"this object is not a dict : {query_result}")
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
        # TODO : Robustify : 429 API rate limit exceeded
        return result

    async def find_match(self, track: Track, query_result: json) -> Optional[str]:
        """"""
        query = track.artist + " " + track.title
        # write_json(data=query_result, filename=query)

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
                    return Match(track, item_id)
        return Match(track, None)

    def tracks_match(self, track: Track, item_track: Track):
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

        match_string = "-> " if match else ""
        track_match = f"    {match_string}{repr(track)} * {repr(item_track)} : {dis_artist} {dis_title} {overlap_artist} {overlap_title}"
        logging.info(track_match)

        return match

    async def get_tracks(self, id: str):
        """"""
        token = self._access_token_response.get("access_token", None)
        url = f"{self.BASE_URL}/tracks/{id}"
        market = self._user.get("country")
        params = {"market": market}
        result = await self.async_get(url=url, access_token=token, params=params)
        return result

    async def create_playlist(self, beatmaker_name, playlist_image_url):
        """"""
        token = self._access_token_response.get("access_token", None)
        playlist_id = await self._create_playlist(beatmaker_name=beatmaker_name)
        logging.info(f"Playlist created with id {playlist_id}")
        playlist_image_bytes = await self.async_get(url=playlist_image_url, access_token=token)
        playlist_image_encoded = base64.b64encode(playlist_image_bytes)
        # playlist_image = base64.b64encode(requests.get(image_url).content)
        await self._upload_cover_image_playlist(playlist_id, playlist_image_encoded)
        return playlist_id

    async def _create_playlist(self, beatmaker_name: str):
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
        return response.get("id")

    async def _upload_cover_image_playlist(self, playlist_id, playlist_image_encoded):
        """"""
        logging.info(f"Uploading cover image for playlist {playlist_id}")
        token = self._access_token_response.get("access_token", None)
        url = f"{self.BASE_URL}/playlists/{playlist_id}/images"
        headers = {"Content-Type": "image/jpeg"}
        await self.async_put(url=url, data=playlist_image_encoded, access_token=token, headers=headers)

    # def add_tracks(self, playlist, matches: list[Match]):
    #     user = spotify_oauth.me()["id"]
    #     for match in matches:
    #         self._add_tracks(match)

    # def _add_tracks(self):
    #     """"""
    #     spotify_oauth.user_playlist_add_tracks(user, playlist["id"], match)
