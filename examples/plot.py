from __future__ import annotations

import os
from dotenv import load_dotenv
import sys
from collections import defaultdict, deque
from datetime import datetime, timedelta

sys.path.append(os.path.dirname(os.path.realpath(__file__)) + "/..")
from client.ocelloids import Ocelloids

from dataclasses import dataclass
from typing import Any
from urllib.error import URLError

from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Grid
from textual.message import Message
from textual.reactive import var
from textual.widgets import Footer, Header, Label, Select
from textual_plotext import PlotextPlot

load_dotenv()

new_blocks = {
    "agent": "chainspy",
    "args": {"networks": ["urn:ocn:polkadot:0", "urn:ocn:polkadot:2034"]},
}

DEFAULT_BUCKET = "5m"
TIME_BUCKETS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
}

STATUS_COLORS = {"finalized": "green", "new": "blue", "pruned": "red"}


def get_time_bucket(timestamp: float, bucket_size: int) -> str:
    dt = datetime.fromtimestamp(timestamp)
    rounded = dt - timedelta(seconds=int(dt.timestamp()) % bucket_size)
    return rounded.strftime("%Y-%m-%d %H:%M")


class Blocks(PlotextPlot):
    """A widget for plotting live block data."""

    marker: var[str] = var("sd")

    def __init__(self, title: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._title = title
        self._data = defaultdict(lambda: {"new": 0, "finalized": 0, "pruned": 0})
        self._time = deque(maxlen=20)
        self.bucket_size = TIME_BUCKETS[DEFAULT_BUCKET]
        self.watch(self.app, "theme", lambda: self.call_after_refresh(self.replot))

    def on_mount(self) -> None:
        self.plt.date_form("Y-m-d H:M")
        self.plt.title(self._title)
        self.plt.xlabel("Time")
        self.plt.ylabel("Blocks")

    def replot(self) -> None:
        self.plt.clear_data()
        if not self._data:
            return

        # List of status types
        status_types = ["new", "finalized", "pruned"]

        # Prepare data for each status to ensure it's filled with 0 if missing
        status_counts = {status: [] for status in status_types}

        times = list(self._data.keys())

        # Fill the counts for each status
        for status in status_types:
            status_counts[status] = [self._data[t].get(status, 0) for t in times]

        # Now, stack the data using the prepared counts
        if times:
            # Each status gets its own set of counts, which will be stacked
            self.plt.stacked_bar(
                times,
                [status_counts[status] for status in status_types],
                marker=self.marker,
                color=[
                    *STATUS_COLORS.values()
                ],  # Ensure this is defined elsewhere as a color list
                labels=status_types,  # Labels for each status
            )

        self.refresh()

    def update(self, timestamp: float, status: str) -> None:
        time_key = get_time_bucket(timestamp, self.bucket_size)
        self._data[time_key][status] += 1
        self.replot()

    def set_bucket_size(self, size: str) -> None:
        if size == Select.BLANK:
            return

        self.bucket_size = TIME_BUCKETS[size]
        self._data.clear()
        self.replot()


class ExtrinsicCounter(Label):
    """Displays a continuous average of extrinsics per block."""

    def __init__(self, **kwargs) -> None:
        super().__init__("Avg. Extrinsics: 0.0", classes="box", **kwargs)
        self.extrinsic_counts = deque(maxlen=50)  # Keep last 50 blocks

    def update(self, extrinsics: int) -> None:
        self.extrinsic_counts.append(extrinsics)
        avg = sum(self.extrinsic_counts) / len(self.extrinsic_counts)
        super().update(f"Avg. Extrinsics: {avg:.2f}")


class BlocksApp(App[None]):
    """An application for visualizing blockchain blocks in real-time."""

    CSS = """
    Grid {
        grid-size: 2;
        grid-rows: 90% 10%;
    }
    Blocks {
        padding: 1 2;
    }
    ExtrinsicCounter {
        padding: 1 2;
    }
    """

    TITLE = "Ocelloids Chain Spy Agent Console"
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
            yield Blocks(f"Polkadot - Blocks ({DEFAULT_BUCKET})", id="blocks-polkadot")
            yield Blocks(
                f"Hydration - Blocks ({DEFAULT_BUCKET})",
                id="blocks-hydration",
            )
            yield ExtrinsicCounter(id="counter-polkadot")
            yield ExtrinsicCounter(id="counter-hydration")
        yield Footer()

    async def on_mount(self) -> None:
        self.gather_blocks()

    async def on_shutdown(self) -> None:
        """Cleanup resources and close the WebSocket connection."""
        await self._client.close()

    @dataclass
    class BlockData(Message):
        data: dict[str, Any]

    @work(exclusive=True)
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
    def update_plot(self, event: BlockData) -> None:
        """Update the plots and extrinsic counter."""
        data = event.data
        metadata = data["metadata"]
        payload = data["payload"]

        timestamp = metadata["timestamp"] / 1000
        network = metadata["networkId"]
        transactions = len(payload.get("extrinsics", []))
        status = payload["status"]  # new, finalized, pruned

        if network == "urn:ocn:polkadot:0":
            self.query_one("#blocks-polkadot", Blocks).update(timestamp, status)
            self.query_one("#counter-polkadot", ExtrinsicCounter).update(transactions)
        elif network == "urn:ocn:polkadot:2034":
            self.query_one("#blocks-hydration", Blocks).update(timestamp, status)
            self.query_one("#counter-hydration", ExtrinsicCounter).update(transactions)


if __name__ == "__main__":
    BlocksApp().run()
