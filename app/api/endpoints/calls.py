import json
import asyncio
import logging

import websockets
from fastapi import (APIRouter, HTTPException, WebSocket, status)
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
    # Build ws_url from configured server domain
    ws_url = f"wss://{settings.SERVER_DOMAIN}/api/v1/calls/media-stream"
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
async def media_stream(websocket: WebSocket):
    await websocket.accept()
    logger.info("User WebSocket Connected")

    try:
        client = DevNagriClient(
            ws_url=settings.DEVNAGRI_WS_URL,
            call_sid="unique_call_id",
            stream_sid="unique_stream_id",
            from_number="caller_number",
            to_number="dialed_number",
            websocket=websocket
        )
        await client.connect()

    except websockets.exceptions.InvalidStatusCode as e:
        logger.error(f"DevNagri connection failed with status {e.status_code}: {e}")
        if e.status_code == 403:
            logger.error("Invalid API key or permissions issue.")

    except Exception as e:
        logger.error(f"Top-level error in media-stream: {type(e).__name__}: {e}")

    finally:
        if websocket.client_state != WebSocketState.DISCONNECTED:
            await websocket.close()
        logger.info("User WebSocket connection closed")