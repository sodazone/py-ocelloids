import json
from requests import get
from websockets.asyncio.client import connect as wsconn

API_WS_URL = "wss://api.ocelloids.net"
API_HTTP_URL = "https://api.ocelloids.net"


class Ocelloids:
    def __init__(
        self, http_url: str = API_HTTP_URL, ws_url: str = API_WS_URL, apikey: str = None
    ):
        self.ws_url = ws_url
        self.http_url = http_url
        self.apikey = apikey
        self.auth = apikey != None

    async def __connect(self, on_connection):
        ws_url_nod = self.ws_url + "/ws/subs"
        if self.auth:
            res = get(
                url=self.http_url + "/ws/nod",
                headers={"Authorization": "Bearer " + self.apikey},
            )
            if res.status_code == 200:
                nodtoken = res.json()["token"]
                ws_url_nod += "?nod=" + nodtoken
            else:
                raise Exception(f"error {res.status_code}")
        async with wsconn(ws_url_nod) as ws:
            self._ws = ws
            if self.auth:
                await ws.send(self.apikey)
                res = json.loads(await ws.recv())
                if res["error"] is True:
                    raise Exception(f"error {res['code']}")
            await on_connection(ws)

    def close(self):
        if self._ws != None:
            self._ws.close()

    async def subscribe(self, subscription: dict, on_message: callable):
        def a(subscription: dict, on_message: callable):
            async def b(ws):
                await ws.send(json.dumps(subscription))
                # Subscription OK
                await ws.recv()
                async for message in ws:
                    on_message(json.loads(message))

            return b

        await self.__connect(a(subscription, on_message))
