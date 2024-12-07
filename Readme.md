### Producer Playlist
Python script to create a Spotify playlist containing every song produced by a specified artist.

### Installation
Clone the repository and install dependencies in a virtual environment 
```
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
```
No the code is ready to run
### Usage

2) You first have to create an access to the Genius and Spotify APIs. Fill in the `secret_keys.py` file with your [Genius Access Token](https://genius.com/api-clients) and your [Spotify Client ID/Secret ID/Redirect URL](https://developer.spotify.com/documentation/general/guides/authorization/app-settings/). Also fill in your [Country Code](https://en.wikipedia.org/wiki/ISO_3166-1_alpha-2)
2) Unfortunately you cannot search directly for a specific artist with the Genius API. So the script takes as input a track which was produced by the target artist. To create a producer playlist, you must fill `search_term` with a song name (*Artist name* + *Track Name* works well) where the target producer is the **first one** listed in the "Produced by" credits on [Genius](https://genius.com/).
3) Launch the notebook with a working python environment (I use VS Code and a Conda environment for example)
4) The script will open the browser and ask for permission to create a Spotify Playlist and modify it. You just have to copy/paste the entire url from your browser to the prompt
5) Playlist is then created. Sometimes a song isn't found, either because it's simply not on Spotify or because the Genius title and the Spotify title are too far apart. Those songs are listed so you can add them manually