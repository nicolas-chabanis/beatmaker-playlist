import aiohttp
import json


class HttpClient:
    """"""

    def __init__(self, session: aiohttp.ClientSession):
        """"""
        self._session = session

    async def async_get(
        self,
        url: str,
        access_token=None,
        params: dict = {},
        headers: dict = {},
    ):
        """"""
        if access_token:
            token = "Bearer {}".format(access_token)
            headers["Authorization"] = token
        async with self._session.get(url=url, params=params, headers=headers) as response:
            content_type = response.headers.get("Content-Type", "")
            if "application/json" in content_type:
                return await response.json()
            else:
                return await response.read()

    async def async_post(
        self,
        url: str,
        data=None,
        access_token=None,
        params: dict = {},
        headers: dict = {},
    ):
        """"""
        if access_token:
            token = "Bearer {}".format(access_token)
            headers["Authorization"] = token
        async with self._session.post(url=url, data=data, params=params, headers=headers) as response:
            content_type = response.headers.get("Content-Type", "")
            if "application/json" in content_type:
                return await response.json()
            else:
                return await response.read()

    async def async_put(
        self,
        url: str,
        data=None,
        access_token=None,
        params: dict = {},
        headers: dict = {},
    ):
        """"""
        if access_token:
            token = "Bearer {}".format(access_token)
            headers["Authorization"] = token
        async with self._session.put(url=url, data=data, params=params, headers=headers) as response:
            content_type = response.headers.get("Content-Type", "")
            if "application/json" in content_type:
                return await response.json()
            else:
                return await response.read()
