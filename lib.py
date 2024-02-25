import requests
import json

### Get function
def _get(base_url, client_access_token, path, params=None, headers=None):

    # generate request URL
    requrl = '/'.join([base_url, path])
    token = "Bearer {}".format(client_access_token)
    if headers:
        headers['Authorization'] = token
    else:
        headers = {"Authorization": token}

    response = requests.get(url=requrl, params=params, headers=headers)
    response.raise_for_status()

    return response.json()

### Put function
def _put(base_url, client_access_token, path, params=None, headers=None):
    requrl = '/'.join([base_url, path])
    token = "Bearer {}".format(client_access_token)
    if headers:
        headers['Authorization'] = token
    else:
        headers = {"Authorization": token}
    response = requests.put(url=requrl, params=params, headers=headers)
    response.raise_for_status()
    return response.json()

# Write json
def write_json(path, json_file):
    with open(path, 'w') as f:
        json.dump(json_file, f, indent=4)