#!/usr/bin/env python

import os
import asyncio

from dotenv import load_dotenv
import sys

sys.path.append(os.path.dirname(os.path.realpath(__file__)) + "/..")
from client.ocelloids import Ocelloids

load_dotenv()

sub = {
    "agent": "chainspy",
    "args": {"networks": ["urn:ocn:polkadot:0", "urn:ocn:polkadot:2034"]},
}


def on_message(message):
    print(f">> {message['metadata']}")


async def run():
    try:
        client = Ocelloids(
            # apikey=os.getenv("OC_API_KEY"),
            http_url=os.getenv("OC_HTTP_URL"),
            ws_url=os.getenv("OC_WS_URL"),
        )
        await client.subscribe(sub, on_message)
    except asyncio.CancelledError:
        print("Stopped")


if __name__ == "__main__":
    asyncio.run(run())
