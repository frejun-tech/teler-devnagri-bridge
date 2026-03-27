import logging
from typing import Dict, Any
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter()

# Store call data
call_data_store: Dict[str, Dict[str, Any]] = {}

@router.post("/receiver", status_code=status.HTTP_200_OK, include_in_schema=False)
async def webhook_receiver(data: dict):
    """
    Handle webhook payload from Teler.
    """
    logger.info(f"--------Webhook Payload-------- {data}")
    
    event_type = data.get("event")
    
    if event_type == "call.initiated":
        call_data = data.get("data", {})
        call_id = call_data.get("call_id")
        from_number_prefix = call_data.get("from", "")
        to_number_prefix = call_data.get("to", "")
        
        from_number = from_number_prefix
        to_number = to_number_prefix
        
        if from_number_prefix:
            from_number = from_number_prefix.replace('+', '')
            
        if to_number_prefix:
            to_number = to_number_prefix.replace('+', '')
        
        if call_id:
            call_data_store[call_id] = {
                "call_id": call_id,
                "from": from_number,
                "to": to_number,
                "account_id": data.get("account_id", ""),
                "call_app_id": data.get("call_app_id", ""),
                "stream_id": None 
            }
            logger.info(f"Stored call data for call_id: {call_id}")
        else:
            logger.warning("No call_id found in call.initiated webhook")
    
    elif event_type == "stream.initiated":
        # Update call data with stream_id
        call_data = data.get("data", {})
        call_id = call_data.get("call_id")
        stream_id = call_data.get("stream_id")
        
        if call_id and call_id in call_data_store:
            if stream_id:
                call_data_store[call_id]["stream_id"] = stream_id
                logger.debug(f"Updated call data with stream_id: {stream_id} for call_id: {call_id}")
            else:
                logger.warning(f"No stream_id found in stream.initiated webhook for call_id: {call_id}")
        else:
            logger.warning(f"No existing call data found for call_id: {call_id}")
    
    elif event_type == "call.completed":
        # Clean up call data when call ends
        call_data = data.get("data", {})
        call_id = call_data.get("call_id")
        if call_id and call_id in call_data_store:
            del call_data_store[call_id]
            logger.info(f"Cleaned up call data for call_id: {call_id}")
    
    
    return JSONResponse(content="Webhook received.")

def get_call_data(call_id: str) -> Dict[str, Any]:
    """
    Retrieve call data for a given call_id.
    """
    return call_data_store.get(call_id, {})