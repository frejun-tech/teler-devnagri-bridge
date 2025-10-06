import json
import logging
import uuid

import websockets
from fastapi import (APIRouter, HTTPException, WebSocket, WebSocketDisconnect, status)
from fastapi.responses import JSONResponse
from fastapi.websockets import WebSocketState
from pydantic import BaseModel

from app.core.config import settings
from app.utils.devnagri_client import DevNagriClient
from app.utils.teler_client import TelerClient

logger = logging.getLogger(__name__)
router = APIRouter()

class CallFlowRequest(BaseModel):
    call_id: str
    account_id: str
    from_number: str
    to_number: str

class CallRequest(BaseModel):
    from_number: str
    to_number: str

# FastAPI Endpoints 

@router.get("/")
async def root():
    return {"message": "Welcome to the Teler-Devnagri bridge"}

@router.post("/flow", status_code=status.HTTP_200_OK, include_in_schema=False)
async def stream_flow(payload: CallFlowRequest):
    """
    Return stream flow as JSON Response containing websocket url to connect
    """
    ws_url = f"wss://{settings.SERVER_DOMAIN}/api/v1/calls/media-stream?call_id={payload.call_id}"
    stream_flow = {
        "action": "stream",
        "ws_url": ws_url,
        "chunk_size": 320,
        "sample_rate": "8k",  
        "record": True
    }
    return JSONResponse(stream_flow)

@router.post("/initiate-call", status_code=status.HTTP_200_OK)
async def initiate_call(call_request: CallRequest):
    """
    Initiate a call using Teler SDK.
    """
    try:
        if not settings.DEVNAGRI_API_KEY:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="DEVNAGRI_API_KEY not configured"
            )
        teler_client = TelerClient(api_key=settings.TELER_API_KEY)
        call = await teler_client.create_call(
            from_number=call_request.from_number,
            to_number=call_request.to_number,
            flow_url=f"https://{settings.SERVER_DOMAIN}/api/v1/calls/flow",
            status_callback_url=f"https://{settings.SERVER_DOMAIN}/api/v1/webhooks/receiver",
            record=True,
        )
        logger.info(f"Call created: {call}")
        return JSONResponse(content={"success": True, "call_id": call.id})
    except Exception as e:
        logger.error(f"Failed to create call: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Call creation failed."
        )

@router.websocket("/media-stream")
async def media_stream(websocket: WebSocket, call_id: str = None):
    # call_id recieved from query params
    await websocket.accept()
    logger.info(f"User WebSocket Connected for call_id: {call_id}")

    client = None
    try:
        # Import here to avoid circular imports
        from app.api.endpoints.webhooks import get_call_data
        
        call_data = {}
        if call_id:
            call_data = get_call_data(call_id)
            logger.info(f"Retrieved call data: {call_data}")
        
        actual_call_id = call_data.get("call_id") or call_id or "unknown_call_id"
        from_number = call_data.get("from") or "unknown_from"
        to_number = call_data.get("to") or "unknown_to"
        
        # Use stream_id from webhook if available, otherwise generate one
        stream_id = call_data.get("stream_id")
        if not stream_id:
            stream_id = f"stream_{uuid.uuid4().hex[:8]}"
            logger.warning(f"No stream_id from webhook, generated: {stream_id}")
        
        client = DevNagriClient(
            ws_url=settings.DEVNAGRI_WS_URL,
            call_id=actual_call_id,
            stream_id=stream_id,
            from_number=from_number,
            to_number=to_number,
            websocket=websocket
        )
        await client.connect()

    except websockets.exceptions.InvalidStatusCode as e:
        logger.error(f"DevNagri connection failed with status {e.status_code}: {e}")
        if e.status_code == 403:
            logger.error("Invalid API key or permissions issue.")

    except WebSocketDisconnect:
        logger.info("User WebSocket disconnected by client")

    except Exception as e:
        logger.error(f"Top-level error in media-stream: {type(e).__name__}: {e}")

    finally:
        # Send STOP event Teler --> DevNagri
        if client and client.devnagri_ws:
            try:
                stop_event = {
                    "event": "stop",
                    "stream_sid": client.stream_id
                }
                await client.devnagri_ws.send(json.dumps(stop_event))
                logger.info("Sent STOP event to DevNagri")
            except Exception as e:
                logger.error(f"Failed to send STOP event to DevNagri: {e}")

        if websocket.client_state != WebSocketState.DISCONNECTED:
            await websocket.close()
        logger.info("User WebSocket connection closed")