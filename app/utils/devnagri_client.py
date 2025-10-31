import asyncio
import json
import base64
import logging
import websockets
from fastapi import WebSocket

logger = logging.getLogger(__name__)

class DevNagriClient:
    def __init__(self, ws_url: str, call_id: str, stream_id: str, from_number: str, to_number: str, websocket: WebSocket):
        self.ws_url = ws_url
        self.call_id = call_id
        self.stream_id = stream_id
        self.from_number = from_number
        self.to_number = to_number
        self.websocket = websocket  
        self.devnagri_ws = None
        self.reconnect_delay = 5
        self.audio_buffer = []  

    async def connect(self):
        while True:  
            try:
                logger.info(f"Connecting to DevNagri WS with stream_id={self.stream_id}...")
                async with websockets.connect(self.ws_url) as ws:
                    self.devnagri_ws = ws
                    await self.on_open()

                    tasks = [
                        asyncio.create_task(self.devnagri_to_teler()),
                        asyncio.create_task(self.teler_to_devnagri())
                    ]

                    done, pending = await asyncio.wait(
                        tasks, return_when=asyncio.FIRST_EXCEPTION
                    )

                    for task in pending:
                        task.cancel()

                    for task in done:
                        if task.exception():
                            raise task.exception()

            except websockets.exceptions.ConnectionClosed as e:
                logger.warning(f"DevNagri WS disconnected, reconnecting in {self.reconnect_delay}s: {e}")
                await asyncio.sleep(self.reconnect_delay)  
            except Exception as e:
                logger.error(f"Streaming session stopped due to error: {e}")
                break 


    async def on_open(self):
        # Send CONNECTED event
        await self.devnagri_ws.send(json.dumps({"event": "connected"}))

        # Send START event with current call_id and stream_id, Teler --> Devnagri
        start_event = {
            "event": "start",
            "start": {
                "call_sid": self.call_id,
                "stream_sid": self.stream_id,
                "from": self.from_number,
                "to": self.to_number,
                "media_format": {
                    "encoding": "base64",
                    "sample_rate": 8000,
                    "bit_rate": "128kbps"
                }
            }
        }
        await self.devnagri_ws.send(json.dumps(start_event))
        logger.info(f"Sent connected and start events to DevNagri (call_id={self.call_id}, stream_id={self.stream_id})")

    # Teler -> DevNagri
    async def teler_to_devnagri(self):
        while True:
            try:
                msg = await self.websocket.receive_text()
                data = json.loads(msg)
                message_type = data.get("type")

                if message_type == "audio":
                    audio_b64 = data.get("data", {}).get("audio_b64")
                    
                    # MEDIA event Teler --> Devnagri
                    await self.devnagri_ws.send(json.dumps({
                        "event": "media",
                        "stream_sid": self.stream_id,
                        "media": {"payload": audio_b64}
                    }))
                    logger.debug(f"Sent audio chunk {len(audio_b64)}) to DevNagri with stream_sid={self.stream_id}")

                else:
                    logger.debug(f"Teler message type: {message_type}")

            except Exception as e:
                logger.error(f"Error forwarding user audio to DevNagri: {e}")
                break


    # DevNagri -> Teler
    async def devnagri_to_teler(self):
        chunk_id = 0
        async for message in self.devnagri_ws:
            try:
                data = json.loads(message)
                event_type = data.get("event")

                # MEDIA event, Devnagri --> Teler
                if event_type == "media":
                    audio_b64 = data.get("media", {}).get("payload")
                    if not audio_b64:
                        continue
                    
                    chunk = base64.b64decode(audio_b64)
                    self.audio_buffer.append(chunk)

                    if len(self.audio_buffer) >= 60:
                        combined = b"".join(self.audio_buffer)
                        self.audio_buffer.clear()
                        combined_b64 = base64.b64encode(combined).decode("utf-8")
                        
                        await self.websocket.send_json({
                            "type": "audio",
                            "audio_b64": combined_b64,
                            "chunk_id": chunk_id
                        })
                        logger.debug(f"Sent buffered audio chunk ({len(combined_b64)} bytes) to Teler")

                        chunk_id += 1

                        # send MARK, Teler --> Devnagri
                        mark_event = {
                            "event": "mark",
                            "stream_sid": self.stream_id,
                            "mark": {"name": "responsePart"}
                        }
                        await self.devnagri_ws.send(json.dumps(mark_event))
                        logger.debug(f"Sent MARK event to DevNagri")

                elif event_type == "clear": 
                    # Clear buffer immediately (barge-in), Devnagri --> Teler CLEAR event
                    self.audio_buffer.clear()
                    await self.websocket.send_json({"type": "clear"})
                    logger.debug("Clear event received from DevNagri — buffer flushed")

                else:
                    logger.warning(f"DevNagri event: {event_type}")

            except Exception as e:
                logger.error(f"Error processing DevNagri message: {e}")

