import requests
import pandas as pd
import json
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from spotipy.oauth2 import SpotifyOAuth
import base64
from urllib.parse import urlencode
import webbrowser
import textdistance
from unidecode import unidecode
from datetime import datetime
import re
import api_key

from lib import _get, _put, write_json


search_term = 'Artist-name Track-name'


### Base URLs for API calls
GENIUS_BASE_URL = "https://api.genius.com"
SPOTIFY_BASE_URL = "https://api.spotify.com/v1"




### Get song id produced by the target producer
r = _get(GENIUS_BASE_URL, api_key.GENIUS_CLIENT_ACCESS_TOKEN, "search", {'q':search_term})
found_song_id = r['response']['hits'][0]['result']['id']

#write_json('json_song_search.json', r)
print("Found song \'", r['response']['hits'][0]['result']['full_title'], "\' with song id", found_song_id)


### Get song info from song id
path = "songs/{}".format(found_song_id)
r = _get(GENIUS_BASE_URL, api_key.GENIUS_CLIENT_ACCESS_TOKEN, path=path)

#write_json('json_song_get.json', r)


### Get producer id from song info
found_producer_name = r['response']['song']['producer_artists'][0]['name']
print("Found producer : " + found_producer_name)
found_producer_id = r['response']['song']['producer_artists'][0]['id']


### Get producer image from Genius.com
path = "artists/{}".format(found_producer_id)
r = _get(GENIUS_BASE_URL, api_key.GENIUS_CLIENT_ACCESS_TOKEN, path=path)
image_url = r['response']['artist']['image_url']

#write_json('producer_info.json', r)


### Get all songs from producer
path = "artists/{}/songs".format(found_producer_id)
songs = []
current_page = 1
next_page = True

while next_page:
    params = {'sort': "popularity", 'page': current_page}
    r = _get(GENIUS_BASE_URL, api_key.GENIUS_CLIENT_ACCESS_TOKEN, path=path, params=params)
    page_songs = r['response']['songs']
    if page_songs:
        songs += page_songs
        current_page += 1
    else:
        next_page = False

#write_json('json_song_from_producer_get.json', songs)


### Build song search list (title + artist name) for spotify

spot_search = []
not_produced_by = []

for song in songs:
    # Build query string from track title and artist name
    pair = []
    pair.append(json.dumps(song['title'], ensure_ascii=False).replace('"', ''))
    pair.append(json.dumps(song['primary_artist']['name'], ensure_ascii=False).replace('"', ''))
    # Check is the song is produced by the target producer
    path = "songs/{}".format(song['id'])
    r = _get(GENIUS_BASE_URL, api_key.GENIUS_CLIENT_ACCESS_TOKEN, path=path)
    produced_by = False
    for producer in r['response']['song']['producer_artists']:
        if(producer['id'] == found_producer_id):
            produced_by = True
            spot_search.append(pair)
            break
    if(produced_by == False):
        not_produced_by.append(pair)


### Build song id list
sp_Client = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=api_key.SPOTIFY_CLIENT_ID, client_secret=api_key.SPOTIFY_CLIENT_SECRET))

tracks_id = []
not_found = []
for count, query_list in enumerate(spot_search):
    found=False
    query = query_list[0] + " " + query_list[1]
    track_search = sp_Client.search(query[0:100], type='track', limit=5, market=api_key.SPOTIFY_COUNTRY_CODE)
    track_searched = re.sub("[\(\[].*?[\)\]]", "", unidecode(spot_search[count][0]).lower())
    artist_searched = re.sub("[\(\[].*?[\)\]]", "", unidecode(spot_search[count][1]).lower())
    #write_json('track_search.json', track_search)
    #print("SEARCHING FOR : <" + query + ">")
    for i in range(min(track_search['tracks']['total'], track_search['tracks']['limit'])):
        dis = textdistance.jaccard.normalized_distance
        op = textdistance.overlap.normalized_distance
        s = track_search['tracks']['items'][i]['name'] + " " + track_search['tracks']['items'][i]['artists'][0]['name']
        track_found = re.sub("[\(\[].*?[\)\]]", "", unidecode(track_search['tracks']['items'][i]['name']).lower())
        artist_found = re.sub("[\(\[].*?[\)\]]", "", unidecode(track_search['tracks']['items'][i]['artists'][0]['name']).lower())
        dis_track = dis(track_searched, track_found)
        dis_artist = dis(artist_searched, artist_found)
        op_track = op(track_searched, track_found)
        op_artist = op(artist_searched, artist_found)
        #print(s, "{:.2f}".format(dis_track), "{:.2f}".format(dis_artist), "{:.2f}".format(op_track), "{:.2f}".format(op_artist))
        if((op_track <= 0.3) & (op_artist <= 0.3) & (dis_artist <= 0.3) & (dis_track <= 0.5)):
            tracks_id.append(track_search['tracks']['items'][i]['id'])    
            found=True
            break
    if(found==False):
        not_found.append(query)



print("--- Following tracks were not found :")
for count, song in enumerate(not_found):
    print("[" + str(count) + "]" + " " + song)

print("")
print(" -------------------------------------------------------------")
print("")
print("--- Following tracks were not produced by " + found_producer_name + " so they weren't added to the playlist :")
for count, song in enumerate(not_produced_by):
    print("[" + str(count) + "]" + " " + song[0] + " " + song[1])


### Create Auth Manager
scope="playlist-modify-public, playlist-modify-public, ugc-image-upload"
auth_manager = SpotifyOAuth(scope=scope, client_id=api_key.SPOTIFY_CLIEsNT_ID, client_secret=api_key.SPOTIFY_CLIENT_SECRET, redirect_uri=api_key.SPOTIPY_REDIRECT_URI, open_browser=True)
sp_OAuth = spotipy.Spotify(auth_manager=auth_manager)


### Create playlist
user = sp_OAuth.me()['id']
playlist_name="Produced by " + found_producer_name
now = datetime.now()
description = "Songs produced by " + found_producer_name + ", creation date : " + now.strftime("%d/%m/%Y")
playlist = sp_OAuth.user_playlist_create(user, playlist_name)
sp_OAuth.user_playlist_change_details(user, playlist['id'], description=description)


### Change playlist image cover
playlist_image = base64.b64encode(requests.get(image_url).content)
#TODO : resize image to max spotify image size/weight ?
sp_OAuth.playlist_upload_cover_image(playlist['id'], playlist_image)


### Add tracks by ids
l = len(tracks_id)//100
for i in range(l):
    sp_OAuth.user_playlist_add_tracks(user, playlist['id'], tracks_id[i*100:(i+1)*100])
sp_OAuth.user_playlist_add_tracks(user, playlist['id'], tracks_id[l*100:len(tracks_id)-1])
