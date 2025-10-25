from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from services.stream_service import stream_manager
from models.session import session_manager
import json

router = APIRouter()

@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for real-time updates"""
    
    # Verify session exists
    session = session_manager.get_session(session_id)
    if not session:
        await websocket.close(code=4004, reason="Session not found")
        return
    
    # Connect
    await stream_manager.connect(session_id, websocket)
    
    try:
        # Send initial connection confirmation
        await websocket.send_json({
            "type": "connected",
            "sessionId": session_id,
            "status": session.status
        })
        
        # Keep connection alive and listen for messages
        while True:
            data = await websocket.receive_text()
            
            # Parse client message
            try:
                message = json.loads(data)
                
                # Handle ping/pong for keep-alive
                if message.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                
            except Exception as e:
                print(f"Error processing message: {e}")
    
    except WebSocketDisconnect:
        await stream_manager.disconnect(session_id, websocket)
    except Exception as e:
        print(f"WebSocket error: {e}")
        await stream_manager.disconnect(session_id, websocket)
