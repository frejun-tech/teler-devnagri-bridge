import asyncio
import json
import logging
import websockets

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from collections import deque

logger = logging.getLogger(__name__)
router = APIRouter()


class DevNagriClient:
    def __init__(self, ws_url: str, call_sid: str, stream_sid: str,
                 from_number: str, to_number: str, websocket: WebSocket):
        self.ws_url = ws_url
        self.call_sid = call_sid
        self.stream_sid = stream_sid
        self.from_number = from_number
        self.to_number = to_number
        self.websocket = websocket  
        self.devnagri_ws = None
        self.reconnect_delay = 5
        # buffer ~25 chunks ≈ 500ms
        self.audio_buffer = deque(maxlen=25)

    async def connect(self):
        while True:
            try:
                logger.info("Connecting to DevNagri WS...")
                async with websockets.connect(self.ws_url) as ws:
                    self.devnagri_ws = ws
                    await self.on_open()

                    # Run both directions concurrently
                    await asyncio.gather(
                        self.forward_devnagri_to_teler(),
                        self.forward_teler_to_devnagri()
                    )

            except websockets.exceptions.ConnectionClosed:
                logger.warning("DevNagri WebSocket closed. Reconnecting...")
                await asyncio.sleep(self.reconnect_delay)

            except websockets.exceptions.InvalidStatusCode as e:
                logger.error(f"DevNagri connection failed ({e.status_code}): {e}")
                if e.status_code == 403:
                    logger.error("Authentication failed. Check DevNagri credentials.")
                    break  # Don’t retry on auth failures
                await asyncio.sleep(self.reconnect_delay)

            except Exception as e:
                logger.error(f"DevNagri WS error: {e}. Reconnecting in {self.reconnect_delay}s...")
                await asyncio.sleep(self.reconnect_delay)

    async def on_open(self):
        # Send connected + start events
        await self.devnagri_ws.send(json.dumps({"event": "connected"}))

        start_event = {
            "event": "start",
            "start": {
                "call_sid": self.call_sid,
                "stream_sid": self.stream_sid,
                "from": self.from_number,
                "to": self.to_number,
                "media_format": {
                    "encoding": "base64",
                    "sample_rate": 8000
                }
            }
        }
        await self.devnagri_ws.send(json.dumps(start_event))
        logger.info("Sent connected and start events to DevNagri")

    # DevNagri -> Teler
    async def forward_devnagri_to_teler(self):
        async for message in self.devnagri_ws:
            try:
                data = json.loads(message)
                event_type = data.get("event")

                if event_type == "media":
                    audio_b64 = data["media"]["payload"]
                    self.audio_buffer.append(audio_b64)

                    # forward immediately
                    await self.websocket.send_json({
                        "type": "audio",
                        "audio_b64": audio_b64
                    })
                    logger.debug(
                        f"Forwarded audio chunk ({len(audio_b64)} bytes), "
                        f"buffer size={len(self.audio_buffer)}"
                    )

                elif event_type == "clear":
                    self.audio_buffer.clear()
                    await self.websocket.send_json({"type": "clear"})
                    logger.info("Clear event: audio buffer flushed")

                else:
                    logger.warning(f"Unhandled DevNagri event: {event_type}")

            except Exception as e:
                logger.error(f"Error processing DevNagri message: {e}")

    # Teler -> DevNagri
    async def forward_teler_to_devnagri(self):
        while True:
            try:
                msg = await self.websocket.receive_text()
                data = json.loads(msg)
                message_type = data.get("type")
                
                if message_type == "audio":
                    audio_b64 = data.get("audio_b64")
                    if not audio_b64:
                        continue

                    await self.devnagri_ws.send(json.dumps({
                        "event": "media",
                        "stream_sid": self.stream_sid,
                        "media": {"payload": audio_b64}
                    }))
                    logger.debug(f"Sent audio chunk from user to DevNagri ({len(audio_b64)} bytes)")

                else:
                    logger.debug(f"Ignored message type: {message_type}")

            except WebSocketDisconnect:
                logger.warning("User WebSocket disconnected")
                break
            except Exception as e:
                logger.error(f"Error forwarding user audio to DevNagri: {e}")
                break
