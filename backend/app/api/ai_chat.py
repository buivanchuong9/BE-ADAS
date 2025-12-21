"""
AI Chat API endpoints - Phase 4 Low Priority
Handles AI assistant chat functionality
"""
from fastapi import APIRouter, HTTPException
from typing import Optional
from datetime import datetime
import uuid

from ..models import storage, AIChatRequest

router = APIRouter(prefix="/api/ai-chat", tags=["ai-chat"])


@router.post("")
async def chat_with_ai(request: AIChatRequest):
    """
    Chat with AI assistant
    
    Request body:
    - message: User message
    - session_id: Optional session ID for conversation context
    - context: Optional additional context
    
    Returns:
    - response: AI assistant response
    - session_id: Session ID for continuing conversation
    """
    # Generate or use existing session ID
    session_id = request.session_id or str(uuid.uuid4())
    
    # Generate dummy AI response based on message keywords
    message_lower = request.message.lower()
    
    # Simple keyword-based responses (dummy AI)
    if any(word in message_lower for word in ["hello", "hi", "hey"]):
        response = "Hello! I'm your ADAS assistant. How can I help you today?"
    elif any(word in message_lower for word in ["help", "what can you do"]):
        response = """I can help you with:
- Analyzing dashcam videos for safety events
- Monitoring driver fatigue and distraction
- Providing safety statistics and insights
- Answering questions about ADAS features
- Managing video datasets and detections

What would you like to know?"""
    elif any(word in message_lower for word in ["fatigue", "tired", "drowsy"]):
        response = """Driver fatigue detection uses facial landmarks to monitor:
- Eye Aspect Ratio (EAR) - detects eye closure
- Mouth Aspect Ratio (MAR) - detects yawning
- Head pose angles - detects head nodding

The system triggers alerts when fatigue indicators exceed thresholds. Recommendations include taking breaks every 2 hours."""
    elif any(word in message_lower for word in ["collision", "crash", "accident"]):
        response = """Forward Collision Warning (FCW) uses:
- Object detection (YOLOv11) to identify vehicles ahead
- Distance estimation for calculating Time-to-Collision (TTC)
- Speed differential analysis
- Lane position tracking

Critical alerts trigger when TTC < 2 seconds or following distance < safe threshold."""
    elif any(word in message_lower for word in ["lane", "departure", "ldw"]):
        response = """Lane Departure Warning detects when your vehicle drifts from the lane without signaling. It uses curved lane detection with polynomial fitting to track lane boundaries and calculates vehicle offset from lane center."""
    elif any(word in message_lower for word in ["model", "yolo", "ai"]):
        response = """Available AI models:
- YOLOv11n: Lightweight detection (6.2MB, 89% accuracy, 15ms)
- YOLOv11s: Balanced detection (12.5MB, 92% accuracy, 25ms)
- YOLOv11m: High accuracy (25.8MB, 94% accuracy, 40ms)
- MediaPipe Face: Driver monitoring (8.5MB, 96% accuracy)
- Depth Anything: Distance estimation (335MB, 91% accuracy)"""
    elif any(word in message_lower for word in ["statistic", "stats", "dashboard"]):
        response = f"""Current system statistics:
- Total videos processed: {len(storage.videos)}
- Total detections: {len(storage.detections)}
- Active events: {len([e for e in storage.events.values() if not e.acknowledged])}
- Trips completed: {len([t for t in storage.trips.values() if t.status.value == 'completed'])}

Would you like more detailed analytics?"""
    else:
        response = f"I understand you're asking about: '{request.message}'. Let me help you with that. Could you provide more specific details about what you'd like to know?"
    
    # Store in chat history
    timestamp = datetime.now().isoformat()
    
    # Add user message
    storage.chat_history.append({
        "id": len(storage.chat_history) + 1,
        "session_id": session_id,
        "role": "user",
        "content": request.message,
        "timestamp": timestamp
    })
    
    # Add assistant response
    storage.chat_history.append({
        "id": len(storage.chat_history) + 1,
        "session_id": session_id,
        "role": "assistant",
        "content": response,
        "timestamp": timestamp
    })
    
    # Keep only last 500 messages
    if len(storage.chat_history) > 500:
        storage.chat_history = storage.chat_history[-500:]
    
    return {
        "success": True,
        "message": request.message,
        "response": response,
        "timestamp": timestamp,
        "session_id": session_id
    }


@router.get("/history")
async def get_chat_history(
    session_id: Optional[str] = None,
    limit: int = 50
):
    """
    Get chat history
    
    Query Params:
    - session_id: Optional session ID to filter by
    - limit: Maximum number of messages to return (default: 50)
    """
    messages = storage.chat_history.copy()
    
    # Filter by session if provided
    if session_id:
        messages = [m for m in messages if m.get("session_id") == session_id]
    
    # Sort by timestamp (most recent last for conversation flow)
    messages.sort(key=lambda x: x.get("timestamp", ""))
    
    # Limit results
    messages = messages[-limit:] if len(messages) > limit else messages
    
    return {
        "success": True,
        "messages": messages
    }


@router.delete("/session/{id}")
async def delete_chat_session(id: str):
    """
    Delete a chat session
    
    Path Params:
    - id: Session ID to delete
    """
    # Remove all messages from this session
    initial_count = len(storage.chat_history)
    storage.chat_history = [
        m for m in storage.chat_history 
        if m.get("session_id") != id
    ]
    deleted_count = initial_count - len(storage.chat_history)
    
    if deleted_count == 0:
        raise HTTPException(status_code=404, detail=f"Session '{id}' not found")
    
    return {
        "success": True,
        "message": f"Deleted {deleted_count} messages from session '{id}'"
    }
