import asyncio
import aiohttp
import json
import time


class HTTPException(Exception):
    """A generic exception that's thrown when a HTTP operation fails."""

    def __init__(self, response, request_data):
        self.response = response
        self.request_data = request_data
        super().__init__(response, request_data, "test")


class Unauthorized(HTTPException):
    """An exception that's thrown when status code 401 occurs."""


class Forbidden(HTTPException):
    """An exception that's thrown when status code 403 occurs."""


class NotFound(HTTPException):
    """An exception that's thrown when status code 404 occurs."""


class BearerTokenError(HTTPException):
    """An exception that's thrown when Spotify could not provide a valid Bearer Token"""


class RateLimitedException(Exception):
    """An exception that gets thrown when a rate limit is encountered."""


class HttpClient:
    """"""

    RETRY_AMOUNT = 5

    def __init__(self, session: aiohttp.ClientSession):
        """"""
        self._session = session
        self.__request_barrier_lock = asyncio.Lock()
        self.__request_barrier = asyncio.Event()
        self.__request_barrier.set()

    async def request(
        self,
        method: str,
        url: str,
        data=None,
        params: dict = {},
        headers: dict = {},
    ):
        for current_retry in range(self.RETRY_AMOUNT):
            await self.__request_barrier.wait()
            request_data = (url, params, headers, data)
            response = await self._session.request(method=method, url=url, data=data, params=params, headers=headers)
            try:
                status = response.status
                if "application/json" in response.content_type:
                    data = json.loads(await response.text(encoding="utf-8"))
                elif "image/jpeg" in response.content_type:
                    data = await response.read()
                else:
                    data = {}
                if 300 > status >= 200:
                    return data
                if status == 429:  # Rate limited
                    self.__request_barrier.clear()
                    amount = int(response.headers.get("Retry-After"))
                    checkpoint = int(time.time())
                    async with self.__request_barrier_lock:
                        if (int(time.time()) - checkpoint) < amount:
                            self.__request_barrier.clear()
                            await asyncio.sleep(int(amount))
                            self.__request_barrier.set()
                    continue
                if status in (502, 503):
                    continue
                if status == 401:
                    raise Unauthorized(response, request_data)
                if status == 403:
                    raise Forbidden(response, request_data)
                if status == 404:
                    raise NotFound(response, request_data)
            finally:
                await response.release()
        if response.status == 429:
            raise RateLimitedException(response, request_data)
        raise HTTPException(response, request_data)

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
        response = await self.request("GET", url=url, params=params, headers=headers)
        return response

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
        response = await self.request("POST", url=url, data=data, params=params, headers=headers)
        return response

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
        response = await self.request("PUT", url=url, data=data, params=params, headers=headers)
        return response
