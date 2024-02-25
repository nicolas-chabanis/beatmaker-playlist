import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from spotipy.oauth2 import SpotifyOAuth

import api_key
import lib

if __name__ == '__main__':
    producer_name = "Kosei"

    # Get producer id from name
    found_producer_name, producer_id = lib.genius_get_producer_id(producer_name)
    if (found_producer_name, producer_id) == (None, None):
        print(f"Producer {producer_name} not found, try to use it's Genius exact name")

    # Get all songs from producer
    songs = lib.genius_get_songs(producer_id)

    # Build song search list (title + artist name) for spotify
    songs_for_spotify, not_produced_by = lib.build_song_search(songs, producer_id)

    # Create spotify_client
    scopes="playlist-modify-public, playlist-modify-public, ugc-image-upload"
    spotify_client_manager = SpotifyClientCredentials(
        client_id=api_key.SPOTIFY_CLIENT_ID,
        client_secret=api_key.SPOTIFY_CLIENT_SECRET)
    spotify_client = spotipy.Spotify(client_credentials_manager=spotify_client_manager)

    # Build song id list
    tracks_id, not_found = lib.build_song_id_list(songs_for_spotify, spotify_client)

    if not_found:
        print("--- Following tracks were not found on Spotify :")
        for count, song in enumerate(not_found):
            print("[" + str(count) + "]" + " " + song)
        print("")
        print(" -------------------------------------------------------------")
        print("")

    if not_produced_by:
        print("--- Following tracks were not produced by " + producer_name + " so they weren't added to the playlist :")
        for count, song in enumerate(not_produced_by):
            print("[" + str(count) + "]" + " " + song[0] + " " + song[1])
    print("")

    # Create spotify_oauth
    spotify_oauth_manager = SpotifyOAuth(scope=scopes,
                                client_id=api_key.SPOTIFY_CLIENT_ID,
                                client_secret=api_key.SPOTIFY_CLIENT_SECRET,
                                redirect_uri=api_key.SPOTIFY_REDIRECT_URI,
                                open_browser=False)
    spotify_oauth = spotipy.Spotify(oauth_manager=spotify_oauth_manager)

    # Get producer image url from Genius
    image_url = lib.genius_producer_image_url(producer_id)

    # Create playlist
    playlist = lib.spotify_create_playlist(spotify_oauth, producer_name, image_url)

    # Add tracks by ids
    lib.spotify_add_tracks(spotify_oauth, playlist, tracks_id)