from __future__ import annotations

import os
from dotenv import load_dotenv
import sys

sys.path.append(os.path.dirname(os.path.realpath(__file__)) + "/..")
from client.ocelloids import Ocelloids

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.error import URLError

from textual import on, work
from textual.color import Color
from textual.app import App, ComposeResult
from textual.containers import Grid
from textual.message import Message
from textual.reactive import var
from textual.widgets import Footer, Header
from textual_plotext import PlotextPlot

load_dotenv()

new_blocks = {"agent": "chainspy", "args": {"networks": ["urn:ocn:polkadot:0"]}}


class Blocks(PlotextPlot):
    """A widget for plotting live block data."""

    marker: var[str] = var("braille")

    def __init__(self, title: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._title = title
        self._data: list[int] = []  # Stores transaction counts
        self._time: list[str] = []  # Stores timestamps
        self.watch(self.app, "theme", lambda: self.call_after_refresh(self.replot))

    def on_mount(self) -> None:
        self.plt.date_form("Y-m-d H:M:S")
        self.plt.title(self._title)
        self.plt.xlabel("Time")
        self.plt.ylabel("Transactions")

    def replot(self) -> None:
        self.plt.clear_data()
        self.plt.bar(
            self._time,
            self._data,
            marker=self.marker,
            width=0.75,
            fill=True,
            color="green",
        )
        self.refresh()

    def update(self, timestamp: str, transaction_count: int) -> None:
        """Update the plot with new block data."""
        self._time.append(timestamp)
        self._data.append(transaction_count)
        if len(self._time) > 20:  # Keep the last 20 blocks for readability
            self._time.pop(0)
            self._data.pop(0)
        self.replot()

    def _watch_marker(self) -> None:
        self.replot()


class BlocksApp(App[None]):
    """An application for visualizing blockchain blocks in real-time."""

    CSS = """
    Grid {
        grid-size: 1;
    }
    """

    TITLE = "Chain Spy Console"
    BINDINGS = [
        ("d", "app.toggle_dark", "Toggle light/dark mode"),
        ("q", "app.quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._client = Ocelloids(
            apikey=os.getenv("OC_API_KEY"),
            http_url=os.getenv("OC_HTTP_URL"),
            ws_url=os.getenv("OC_WS_URL"),
        )

    def compose(self) -> ComposeResult:
        yield Header()
        with Grid():
            yield Blocks("Polkadot - Extrinsics per Block", id="blocks")
        yield Footer()

    async def on_mount(self) -> None:
        self.gather_blocks()

    async def on_shutdown(self) -> None:
        """Cleanup resources and close the WebSocket connection."""
        await self._client.close()

    @dataclass
    class BlockData(Message):
        data: dict[str, Any]

    @work(exclusive=True, group="gather-blocks")
    async def gather_blocks(self) -> None:
        """Subscribe to block data updates."""

        def on_message(m):
            self.post_message(self.BlockData(m))

        try:
            await self._client.subscribe(new_blocks, on_message)

        except URLError as error:
            self.notify(
                str(error),
                title="Error loading block data",
                severity="error",
                timeout=6,
            )

    @on(BlockData)
    @work(exclusive=True, thread=True)
    def update_plot(self, event: BlockData) -> None:
        """Update the plot with new block data."""
        data = event.data
        metadata = data["metadata"]
        payload = data["payload"]

        timestamp = datetime.fromtimestamp(metadata["timestamp"] / 1000).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        transactions = len(payload.get("extrinsics", []))

        self.query_one("#blocks", Blocks).update(timestamp, transactions)


if __name__ == "__main__":
    BlocksApp().run()
