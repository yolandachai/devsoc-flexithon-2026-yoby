"""
server.py

Local WebSocket server that broadcasts pipeline events (sound label +
attributed direction + confidence) to the frontend.

Format of each event is a JSON object like this:

{
  "label": "Footsteps",
  "confidence": 0.62,
  "direction": {
    "available": true,
    "mode": "stereo",            // "stereo" | "multichannel" | "none"
    "pan": -0.71,                // present only when mode == "stereo"
    "azimuth_deg": null,         // present only when mode == "multichannel"
    "label": "left"
  },
  "timestamp":                   // time.time() when the event was produced
}

"""

import asyncio
import json
import queue
import threading
import time
from typing import Optional, Set

import websockets

from direction import DirectionEstimate

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 8765


def _direction_to_wire(direction: DirectionEstimate) -> dict:
    # Convert a DirectionEstimate to a JSON-serializable dict for the wire format.
    return {
        "available": direction.available,
        "mode": direction.mode,
        "pan": direction.pan,
        "azimuth_deg": direction.azimuth_deg,
        "label": direction.label,
    }


def build_event(label: str, confidence: float, direction: DirectionEstimate) -> dict:
    # Build a JSON-serializable dict representing a single event to send to overlay clients.
    return {
        "label": label,
        "confidence": confidence,
        "direction": _direction_to_wire(direction),
        "timestamp": time.time(),
    }


class SubtitleServer:
    ## WebSocket server that runs in a background thread and broadcasts events to all connected clients.

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
        self.host = host
        self.port = port
        self._queue: "queue.Queue[dict]" = queue.Queue()
        self._clients: Set = set()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event: Optional[asyncio.Event] = None  # created on the loop thread, in _run_loop

    def start(self) -> None:
        # Start the background thread and its asyncio event loop. The server will listen for
        # WebSocket connections and broadcast events from the queue to all connected clients.
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        while self._loop is None:
            time.sleep(0.01)

    def publish(self, event: dict) -> None:
        # Put an event into the thread-safe queue to be broadcast to all connected clients.
        self._queue.put(event)

    def stop(self) -> None:
        # Stop the background thread and its asyncio event loop. This will close all client connections.
        if self._loop is None:
            return
        self._loop.call_soon_threadsafe(self._stop_event.set)
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def _run_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._stop_event = asyncio.Event()
        try:
            self._loop.run_until_complete(self._serve())
        finally:
            self._loop.close()

    async def _serve(self) -> None:
        async with websockets.serve(self._handle_client, self.host, self.port):
            print(f"[server] WebSocket server listening on ws://{self.host}:{self.port}")
            await self._pump_queue()

    async def _handle_client(self, websocket) -> None:
        self._clients.add(websocket)
        try:
           # Keep the connection open until the client disconnects. Abrupt
           # disconnects (e.g. closing the browser tab) surface as
           # ConnectionClosedError rather than a clean close frame -- that's
           # expected, not an error worth logging.
            async for _ in websocket:
                pass
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self._clients.discard(websocket)

    async def _pump_queue(self) -> None:
        # Continuously read events from the queue and broadcast them to all connected clients.
        while not self._stop_event.is_set():
            try:
                event = self._queue.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.01)
                continue

            if not self._clients:
                continue

            payload = json.dumps(event)
            stale = []
            for client in list(self._clients):
                try:
                    await client.send(payload)
                except websockets.exceptions.ConnectionClosed:
                    stale.append(client)
            for client in stale:
                self._clients.discard(client)
                