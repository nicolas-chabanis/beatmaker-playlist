import logging
import asyncio
import aiohttp

from http_client import HttpClient
from utils import Track, clean_json_str
import secret_keys


class Genius(HttpClient):
    """"""

    BASE_URL = "https://api.genius.com"

    def __init__(self, session: aiohttp.ClientSession, debug: bool = False, faster_tests: bool = False):
        """"""
        super().__init__(session=session)
        self._debug = debug
        self._faster_tests = faster_tests

    async def get_producer_id(self, beatmaker_name: str):
        """"""
        logging.info(f"Searching Genius.com producer_id from name '{beatmaker_name}'...")
        page = 1
        per_page = 3
        next_page = True
        while next_page:
            logging.info(f"    page: {page} ({per_page} elements)")
            url = f"{self.BASE_URL}/search"
            params = {"q": beatmaker_name, "per_page": per_page, "page": page}
            search_result = await self.async_get(
                url=url, access_token=secret_keys.GENIUS_CLIENT_ACCESS_TOKEN, params=params
            )

            tasks = []
            hits = search_result["response"]["hits"]
            if hits:
                for hit in hits:
                    # Get song info from song id
                    song_id = hit["result"]["id"]
                    full_title = hit["result"]["full_title"]
                    logging.info(f"    searching in song '{full_title}'")
                    url = f"{self.BASE_URL}/songs/{song_id}"
                    task = self.async_get(
                        url=url,
                        access_token=secret_keys.GENIUS_CLIENT_ACCESS_TOKEN,
                    )
                    tasks.append(task)

                songs = await asyncio.gather(*tasks)
                for song in songs:
                    # Get producer id from song info
                    producers = song["response"]["song"]["producer_artists"]
                    for producer in producers:
                        found_producer_name = producer["name"]
                        if found_producer_name.lower() == beatmaker_name.lower():
                            logging.info(f"    Found producer: {found_producer_name}")
                            found_producer_id = song["response"]["song"]["producer_artists"][0]["id"]
                            return found_producer_name, found_producer_id
                page += 1
                per_page = 5
            else:
                next_page = False
        logging.error(f"  Producer '{beatmaker_name}' not found on Genius.com")
        return None, None

    async def get_producer_image_url(self, producer_id):
        """"""
        url = f"{self.BASE_URL}/artists/{producer_id}"
        logging.info(f"Retrieving beatmaker image...")
        params = {"per_page": 1}
        response = await self.async_get(url=url, access_token=secret_keys.GENIUS_CLIENT_ACCESS_TOKEN, params=params)
        return response["response"]["artist"]["image_url"]

    async def get_songs(self, beatmaker_id):
        """Get songs from a producer"""
        logging.info(f"Searching for all songs from beatmaker with id {beatmaker_id} ...")
        url = f"{self.BASE_URL}/artists/{beatmaker_id}/songs"
        songs = []

        page = 1
        per_page = 50 if not self._faster_tests else 5
        while page:
            logging.info(f"    current page: {page} ({per_page} elements)")
            params = {"sort": "popularity", "per_page": per_page, "page": page}
            response = await self.async_get(
                url=url, access_token=secret_keys.GENIUS_CLIENT_ACCESS_TOKEN, params=params
            )
            page_songs = response["response"]["songs"]
            if page_songs:
                songs += page_songs
                page = response["response"]["next_page"] if not self._faster_tests else None

        logging.info(f"    found {len(songs)} songs")
        return songs

    async def build_song_search(self, songs, beatmaker_id):
        """"""
        logging.info(f"Building song list...")
        songs_produced: list[Track] = []
        songs_not_produced: list[Track] = []

        tasks = []
        for song in songs:
            song_id = song.get("id", None)
            url = f"{self.BASE_URL}/songs/{song_id}"
            task = self.async_get(
                url=url,
                access_token=secret_keys.GENIUS_CLIENT_ACCESS_TOKEN,
            )
            tasks.append(task)

        detailed_songs = await asyncio.gather(*tasks)

        for detailed_song in detailed_songs:
            title = clean_json_str(detailed_song["response"]["song"]["title"])
            artist = clean_json_str(detailed_song["response"]["song"]["primary_artist"]["name"])
            track = Track(artist=artist, title=title)
            # Check if the song is produced by the target producer
            producer_artists = detailed_song["response"]["song"]["producer_artists"]
            producer_artists_id = [producer["id"] for producer in producer_artists]
            if beatmaker_id in producer_artists_id:
                songs_produced.append(track)
            else:
                songs_not_produced.append(track)

        total_songs = len(songs_not_produced) + len(songs_produced)
        logging.info(f"    found {len(songs_produced)}/{total_songs} songs produced by '{beatmaker_id}' on Genius.com")
        return songs_produced, songs_not_produced
