from time import perf_counter
import asyncio
import aiohttp
import logging

from beatmaker_playlist import BeatmakerPlaylist, BeatmakerPlaylistResults
import secret_keys


async def create_playlist(beatmaker_name: str) -> None:
    start_time = perf_counter()

    client = aiohttp.ClientSession()
    playlist_manager = BeatmakerPlaylist(client=client, debug=True, faster_tests=secret_keys.FASTER_TESTS)

    # Get access token
    playlist_manager.set_spotify_access_token_response(access_token_response=secret_keys.SPOTIFY_ACCESS_TOKEN_DEBUG)

    # Set Spotify market
    await playlist_manager.get_spotify_user_profile()

    # Create playlist
    beatmaker_playlist_results = await playlist_manager.make_playlist(beatmaker_name)

    logging.info(f"Spotify playlist url : {beatmaker_playlist_results.playlist_url}")

    end_time = perf_counter()
    total_time = end_time - start_time
    print(f"\n---Finished in: {total_time:02f} seconds---")

    await client.close()


if __name__ == "__main__":
    beatmaker_name = "Kosei"
    logging.basicConfig(level=logging.INFO, format="{asctime} - {levelname} - {message}", style="{")
    asyncio.run(create_playlist(beatmaker_name=beatmaker_name))
