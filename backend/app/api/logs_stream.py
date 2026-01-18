"""
LIVE LOG STREAMING API - WebSocket
===================================
Stream backend logs in real-time to mobile app.

Endpoint: ws://server/ws/logs
Usage: Connect from SwiftUI app to receive live log updates
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import List
import asyncio
import logging
from pathlib import Path
from datetime import datetime

router = APIRouter()
logger = logging.getLogger(__name__)

# Active WebSocket connections
active_connections: List[WebSocket] = []


class LogStreamer:
    """Stream log file changes to WebSocket clients."""
    
    def __init__(self, log_file_path: str = "/var/log/adas/backend.log"):
        self.log_file_path = Path(log_file_path)
        self.last_position = 0
        
    async def tail_log_file(self):
        """Tail log file and yield new lines."""
        try:
            # If file doesn't exist, wait for it
            while not self.log_file_path.exists():
                await asyncio.sleep(1)
            
            # Open file and seek to end (or last position)
            with open(self.log_file_path, 'r') as f:
                # Seek to last position or end
                if self.last_position > 0:
                    f.seek(self.last_position)
                else:
                    f.seek(0, 2)  # Seek to end
                
                while True:
                    line = f.readline()
                    if line:
                        self.last_position = f.tell()
                        yield line.strip()
                    else:
                        # No new data, wait a bit
                        await asyncio.sleep(0.5)
                        
        except Exception as e:
            logger.error(f"Error tailing log file: {e}")
            yield f"[ERROR] Failed to read log file: {e}"


log_streamer = LogStreamer()


@router.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    """
    WebSocket endpoint for live log streaming.
    
    Usage from SwiftUI:
    ```swift
    let url = URL(string: "ws://server:52000/ws/logs")!
    let webSocket = URLSession.shared.webSocketTask(with: url)
    webSocket.resume()
    ```
    """
    await websocket.accept()
    active_connections.append(websocket)
    
    logger.info(f"📱 Mobile app connected to log stream (Total: {len(active_connections)})")
    
    try:
        # Send welcome message
        await websocket.send_text(
            f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🚀 Connected to ADAS Backend Logs\n"
        )
        
        # Stream logs
        async for log_line in log_streamer.tail_log_file():
            try:
                await websocket.send_text(log_line)
            except Exception as e:
                logger.error(f"Error sending log to client: {e}")
                break
                
    except WebSocketDisconnect:
        logger.info("📱 Mobile app disconnected from log stream")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        if websocket in active_connections:
            active_connections.remove(websocket)
        logger.info(f"📱 Active log connections: {len(active_connections)}")


@router.get("/api/logs/recent")
async def get_recent_logs(lines: int = 100):
    """
    Get recent log lines (HTTP endpoint).
    
    Args:
        lines: Number of recent lines to return (default: 100)
        
    Returns:
        List of recent log lines
    """
    try:
        log_file = Path("/var/log/adas/backend.log")
        
        if not log_file.exists():
            return {
                "success": False,
                "error": "Log file not found",
                "logs": []
            }
        
        # Read last N lines efficiently
        with open(log_file, 'r') as f:
            # Read all lines
            all_lines = f.readlines()
            
            # Get last N lines
            recent_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
            
        return {
            "success": True,
            "total_lines": len(all_lines),
            "returned_lines": len(recent_lines),
            "logs": [line.strip() for line in recent_lines]
        }
        
    except Exception as e:
        logger.error(f"Error reading logs: {e}")
        return {
            "success": False,
            "error": str(e),
            "logs": []
        }


@router.get("/api/logs/stats")
async def get_log_stats():
    """Get log file statistics."""
    try:
        log_file = Path("/var/log/adas/backend.log")
        
        if not log_file.exists():
            return {
                "success": False,
                "error": "Log file not found"
            }
        
        stat = log_file.stat()
        
        return {
            "success": True,
            "file_path": str(log_file),
            "file_size_mb": round(stat.st_size / (1024 * 1024), 2),
            "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "active_connections": len(active_connections)
        }
        
    except Exception as e:
        logger.error(f"Error getting log stats: {e}")
        return {
            "success": False,
            "error": str(e)
        }
