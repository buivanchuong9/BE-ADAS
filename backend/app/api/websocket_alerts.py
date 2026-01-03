"""
WEBSOCKET ALERT STREAMING API
==============================
Phase 6: Real-time alert streaming via WebSocket.

PURPOSE:
Stream ADAS alerts to connected clients in real-time for:
- Dashboard visualization
- Mobile app notifications
- Real-time driver alerts

FEATURES:
- WebSocket connection at wss://adas-api.aiotlab.edu.vn:52000/ws/alerts
- Alert priority queue
- Connection management
- Broadcast to multiple clients
- Automatic reconnection support

PROTOCOL:
Client connects → Receives alert stream → Handles alerts

Message Format:
{
    "alert_type": "FCW",
    "severity": "CRITICAL",
    "message": "Forward Collision Warning!",
    "message_vi": "Cảnh báo va chạm phía trước!",
    "risk_score": 0.95,
    "timestamp": "2025-12-26T10:30:45.123Z",
    "metadata": {...}
}

Author: Senior ADAS Engineer
Date: 2025-12-26 (Phase 6)
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from typing import List, Dict, Any, Set, Optional
import logging
import json
import asyncio
from datetime import datetime

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["WebSocket"])


class ConnectionManager:
    """
    Manages WebSocket connections for alert streaming.
    """
    
    def __init__(self):
        # Active WebSocket connections
        self.active_connections: Set[WebSocket] = set()
        
        # Alert queue for buffering
        self.alert_queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        
        # Broadcasting task
        self.broadcast_task: Optional[asyncio.Task] = None
        
        logger.info("ConnectionManager initialized")
    
    async def connect(self, websocket: WebSocket):
        """Accept and register new WebSocket connection."""
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"Client connected. Total connections: {len(self.active_connections)}")
        
        # Start broadcast task if not running
        if self.broadcast_task is None or self.broadcast_task.done():
            self.broadcast_task = asyncio.create_task(self._broadcast_loop())
    
    def disconnect(self, websocket: WebSocket):
        """Unregister WebSocket connection."""
        self.active_connections.discard(websocket)
        logger.info(f"Client disconnected. Total connections: {len(self.active_connections)}")
    
    async def send_alert(self, alert: Dict[str, Any], websocket: WebSocket):
        """Send alert to specific client."""
        try:
            await websocket.send_json(alert)
        except Exception as e:
            logger.error(f"Error sending alert to client: {e}")
            self.disconnect(websocket)
    
    async def broadcast_alert(self, alert: Dict[str, Any]):
        """
        Broadcast alert to all connected clients.
        
        Args:
            alert: Alert dictionary from RiskEngine
        """
        if not self.active_connections:
            return
        
        # Add to queue for broadcast
        try:
            await self.alert_queue.put(alert)
        except asyncio.QueueFull:
            logger.warning("Alert queue full, dropping oldest alert")
            # Remove oldest and add new
            try:
                self.alert_queue.get_nowait()
                await self.alert_queue.put(alert)
            except Exception:
                # Ignore queue errors during alert buffering
                pass
    
    async def _broadcast_loop(self):
        """Background task to broadcast alerts from queue."""
        logger.info("Alert broadcast loop started")
        
        while True:
            try:
                # Wait for alert
                alert = await self.alert_queue.get()
                
                # Broadcast to all connections
                disconnected = set()
                for connection in self.active_connections:
                    try:
                        await connection.send_json(alert)
                    except Exception as e:
                        logger.error(f"Failed to send alert: {e}")
                        disconnected.add(connection)
                
                # Remove disconnected clients
                for conn in disconnected:
                    self.disconnect(conn)
                
                self.alert_queue.task_done()
                
            except asyncio.CancelledError:
                logger.info("Broadcast loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in broadcast loop: {e}")
                await asyncio.sleep(1)  # Prevent tight loop on error
    
    async def send_heartbeat(self, websocket: WebSocket):
        """Send heartbeat to keep connection alive."""
        try:
            await websocket.send_json({
                "type": "heartbeat",
                "timestamp": datetime.utcnow().isoformat()
            })
        except Exception:
            # Ignore heartbeat send errors (connection may be closed)
            pass
    
    def get_stats(self) -> Dict[str, Any]:
        """Get connection statistics."""
        return {
            "active_connections": len(self.active_connections),
            "queued_alerts": self.alert_queue.qsize(),
            "max_queue_size": self.alert_queue.maxsize
        }


# Global connection manager
manager = ConnectionManager()


@router.websocket("/alerts")
async def websocket_alerts_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time alert streaming.
    
    URL: wss://adas-api.aiotlab.edu.vn:52000/ws/alerts
    
    Client receives:
    - Real-time ADAS alerts (FCW, LDW, DDW, PCW)
    - Heartbeat messages every 30s
    - Connection status updates
    
    Example JavaScript client:
    ```javascript
    const ws = new WebSocket('wss://adas-api.aiotlab.edu.vn:52000/ws/alerts');
    
    ws.onmessage = (event) => {
        const alert = JSON.parse(event.data);
        if (alert.type === 'heartbeat') return;
        
        console.log(`[${alert.severity}] ${alert.message_vi}`);
        // Handle alert (show notification, play sound, etc.)
    };
    
    ws.onerror = (error) => console.error('WebSocket error:', error);
    ws.onclose = () => console.log('Connection closed, reconnecting...');
    ```
    """
    await manager.connect(websocket)
    
    try:
        # Send welcome message
        await websocket.send_json({
            "type": "connection",
            "status": "connected",
            "message": "Connected to ADAS alert stream",
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Keep connection alive with heartbeats
        while True:
            try:
                # Wait for client message (ping) or timeout
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                
                # Echo client message
                await websocket.send_json({
                    "type": "echo",
                    "data": data,
                    "timestamp": datetime.utcnow().isoformat()
                })
                
            except asyncio.TimeoutError:
                # Send heartbeat if no message received
                await manager.send_heartbeat(websocket)
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info("Client disconnected normally")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


@router.get("/alerts/stats")
async def get_websocket_stats():
    """
    Get WebSocket connection statistics.
    
    Returns:
        Connection stats including active connections and queue size
    """
    return manager.get_stats()


# Helper function for other modules to broadcast alerts
async def broadcast_alert_to_clients(alert_dict: Dict[str, Any]):
    """
    Helper function to broadcast alerts from other modules.
    
    Args:
        alert_dict: Alert dictionary (from RiskAlert.to_dict())
    """
    await manager.broadcast_alert(alert_dict)


if __name__ == "__main__":
    print("WebSocket Alert Streaming Module")
    print("=" * 50)
    print("Endpoint: wss://adas-api.aiotlab.edu.vn:52000/ws/alerts")
    print("Stats: GET /ws/alerts/stats")
    print()
    print("Test with JavaScript:")
    print("const ws = new WebSocket('wss://adas-api.aiotlab.edu.vn:52000/ws/alerts');")
    print("ws.onmessage = (e) => console.log(JSON.parse(e.data));")
