import json
import textdistance
from unidecode import unidecode
import re
import datetime
import spotipy
import base64
import requests
import urllib
from tqdm import tqdm

import api_key

### Base URLs for API calls
GENIUS_BASE_URL = "https://api.genius.com"
SPOTIFY_BASE_URL = "https://api.spotify.com/v1"


def _get(base_url, client_access_token, path, params={}, headers={}):
    requrl = '/'.join([base_url, path])
    token = "Bearer {}".format(client_access_token)
    headers['Authorization'] = token
    # if "q" in params:
    #     params["q"] = urllib.parse.quote(params["q"], safe='/', encoding=None, errors=None)
    #     print(params["q"])
    response = requests.get(url=requrl, params=params, headers=headers)
    response.raise_for_status()
    return response.json()


def _put(base_url, client_access_token, path, params={}, headers={}):
    requrl = '/'.join([base_url, path])
    token = "Bearer {}".format(client_access_token)
    headers['Authorization'] = token
    response = requests.put(url=requrl, params=params, headers=headers)
    response.raise_for_status()
    return response.json()


def print_json(json_object):
    pretty_json = json.dumps(json_object, indent=2)
    print(pretty_json)


def write_json(path, json_file):
    with open(path, 'w') as f:
        json.dump(json_file, f, indent=4)


def genius_get_producer_id(producer_name: str):
    current_page = 1
    next_page = True
    while next_page:
        path="search"
        params = {"q": producer_name, "per_page": 50, "page": current_page}
        search_result = _get(GENIUS_BASE_URL, api_key.GENIUS_CLIENT_ACCESS_TOKEN, path=path, params=params)
        hits = search_result["response"]["hits"]
        if hits:
            for hit in hits:
                # Get song info from song id
                song_id = hit["result"]["id"]
                path = f"songs/{song_id}"
                params = {"per_page": 1}
                song = _get(GENIUS_BASE_URL, api_key.GENIUS_CLIENT_ACCESS_TOKEN, path=path, params=params)
                # Get producer id from song info
                producers = song["response"]["song"]["producer_artists"]
                for producer in producers:
                    found_producer_name = producer["name"]
                    if found_producer_name.lower() == producer_name.lower():
                        print("Found producer : " + found_producer_name)
                        found_producer_id = song["response"]["song"]["producer_artists"][0]["id"]
                        return found_producer_name, found_producer_id
            current_page += 1
        else:
            next_page = False
    return None, None


def genius_producer_image_url(producer_id):
    path = "artists/{}".format(producer_id)
    params = {"per_page": 1}
    r = _get(GENIUS_BASE_URL, api_key.GENIUS_CLIENT_ACCESS_TOKEN, path=path, params=params)
    return r["response"]["artist"]["image_url"]


def genius_get_songs(producer_id):
    """Get songs from a producer"""
    path = "artists/{}/songs".format(producer_id)
    songs = []
    current_page = 1
    next_page = True

    while next_page:
        params = {"sort": "popularity", "per_page": 10, "page": current_page}
        r = _get(GENIUS_BASE_URL, api_key.GENIUS_CLIENT_ACCESS_TOKEN, path=path, params=params)
        page_songs = r["response"]["songs"]
        if page_songs:
            songs += page_songs
            current_page += 1
            next_page = False
        else:
            next_page = False

    return songs


def build_song_search(songs, producer_id):
    spot_search = []
    not_produced_by = []

    for song in tqdm(songs, "Scraping genius.com for tracks"):
        # Build query string from track title and artist name
        pair = []
        pair.append(json.dumps(song["title"], ensure_ascii=False).replace('"', ''))
        pair.append(json.dumps(song["primary_artist"]["name"], ensure_ascii=False).replace('"', ''))
        # Check is the song is produced by the target producer
        path = "songs/{}".format(song["id"])
        params = {"per_page": 1}
        r = _get(GENIUS_BASE_URL, api_key.GENIUS_CLIENT_ACCESS_TOKEN, path=path, params=params)
        produced_by = False
        for producer in r["response"]["song"]["producer_artists"]:
            if(producer["id"] == producer_id):
                produced_by = True
                spot_search.append(pair)
                break
        if(produced_by == False):
            not_produced_by.append(pair)

    return spot_search, not_produced_by


def build_song_id_list(songs_for_spotify, sp_client: spotipy.Spotify):
    tracks_id = []
    not_found = []
    for count, query_list in enumerate(tqdm(songs_for_spotify, desc="Building track list for Spotify")):
        found=False
        query = query_list[0] + " " + query_list[1]
        track_search = sp_client.search(query[0:100], type="track", limit=5, market=api_key.SPOTIFY_COUNTRY_CODE)
        track_searched = re.sub("[\(\[].*?[\)\]]", "", unidecode(songs_for_spotify[count][0]).lower())
        artist_searched = re.sub("[\(\[].*?[\)\]]", "", unidecode(songs_for_spotify[count][1]).lower())
        #print("SEARCHING FOR : <" + query + ">")
        for i in range(min(track_search["tracks"]["total"], track_search["tracks"]["limit"])):
            dis = textdistance.jaccard.normalized_distance
            op = textdistance.overlap.normalized_distance
            s = track_search["tracks"]["items"][i]["name"] + " " + track_search["tracks"]["items"][i]["artists"][0]["name"]
            track_found = re.sub("[\(\[].*?[\)\]]", "", unidecode(track_search["tracks"]["items"][i]["name"]).lower())
            artist_found = re.sub("[\(\[].*?[\)\]]", "", unidecode(track_search["tracks"]["items"][i]["artists"][0]["name"]).lower())
            dis_track = dis(track_searched, track_found)
            dis_artist = dis(artist_searched, artist_found)
            op_track = op(track_searched, track_found)
            op_artist = op(artist_searched, artist_found)
            #print(s, "{:.2f}".format(dis_track), "{:.2f}".format(dis_artist), "{:.2f}".format(op_track), "{:.2f}".format(op_artist))
            if((op_track <= 0.3) & (op_artist <= 0.3) & (dis_artist <= 0.3) & (dis_track <= 0.5)):
                tracks_id.append(track_search["tracks"]["items"][i]["id"])    
                found=True
                break
        if(found==False):
            not_found.append(query)

    return tracks_id, not_found


def spotify_create_playlist(spotify_oauth: spotipy.Spotify, producer_name, image_url):
    user = spotify_oauth.me()["id"]
    playlist_name="Produced by " + producer_name
    now = datetime.datetime.now()
    description = "Songs produced by " + producer_name + ", creation date : " + now.strftime("%d/%m/%Y")
    playlist = spotify_oauth.user_playlist_create(user, playlist_name)
    spotify_oauth.user_playlist_change_details(user, playlist["id"], description=description)
    playlist_image = base64.b64encode(requests.get(image_url).content)
    spotify_oauth.playlist_upload_cover_image(playlist["id"], playlist_image)
    return playlist


def spotify_add_tracks(spotify_oauth: spotipy.Spotify, playlist, tracks_id):
    user = spotify_oauth.me()["id"]
    l = len(tracks_id)//100
    for i in tqdm(range(l), desc="Adding tracks to playlist"):
        spotify_oauth.user_playlist_add_tracks(user, playlist["id"], tracks_id[i*100:(i+1)*100])
    spotify_oauth.user_playlist_add_tracks(user, playlist["id"], tracks_id[l*100:len(tracks_id)-1])
