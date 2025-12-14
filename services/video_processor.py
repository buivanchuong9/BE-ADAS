# Video Processor - Frame-by-frame ADAS analysis
# All metrics computed from REAL inference results

import cv2
import numpy as np
import logging
import json
from typing import Dict, List, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from models import VideoDataset, ADASEvent, Detection
from services.adas_pipeline import ADASPipeline

logger = logging.getLogger("adas-backend")


class VideoProcessor:
    """
    Process uploaded videos with ADAS features.
    Feature flags control which modules are executed.
    """
    
    def __init__(
        self,
        enable_fcw: bool = True,
        enable_ldw: bool = True,
        enable_tsr: bool = True,
        enable_pedestrian: bool = True,
        confidence_threshold: float = 0.5
    ):
        self.enable_fcw = enable_fcw
        self.enable_ldw = enable_ldw
        self.enable_tsr = enable_tsr
        self.enable_pedestrian = enable_pedestrian
        self.confidence_threshold = confidence_threshold
        
        # Initialize ADAS pipeline
        self.pipeline = ADASPipeline(
            enable_fcw=enable_fcw,
            enable_ldw=enable_ldw,
            enable_tsr=enable_tsr,
            enable_pedestrian=enable_pedestrian,
            confidence_threshold=confidence_threshold
        )
    
    def process_video(self, video_path: str, video_id: str, db: Session) -> Dict[str, Any]:
        """
        Process video frame by frame.
        Returns real metrics from inference.
        """

        logger.info(f"Processing video: {video_id}")
        
        # Open video
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError("Failed to open video file")
        
        # Get video properties
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        duration = total_frames / fps if fps > 0 else 0
        
        logger.info(f"Video properties: {total_frames} frames, {fps} FPS, {width}x{height}")
        
        # Save video metadata to database
        video_record = VideoDataset(
            filename=video_id,
            original_filename=video_path,
            file_path=video_path,
            fps=fps,
            total_frames=total_frames,
            width=width,
            height=height,
            duration=duration,
            status="processing"
        )
        db.add(video_record)
        db.commit()
        
        # Process frames
        events = []
        events_by_type = {}
        processed_frames = 0
        frame_number = 0
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            frame_number += 1
            timestamp = frame_number / fps if fps > 0 else 0
            
            # Process frame through ADAS pipeline
            frame_events = self.pipeline.process_frame(frame, frame_number, timestamp)
            
            # Store events
            for event in frame_events:
                events.append(event)
                event_type = event["event_type"]
                events_by_type[event_type] = events_by_type.get(event_type, 0) + 1
                
                # Save to database
                db_event = ADASEvent(
                    session_id=None,  # No session for offline processing
                    event_type=event_type,
                    severity=event["severity"],
                    message=event["message"],
                    data=json.dumps(event.get("data", {})),
                    timestamp=datetime.now()
                )
                db.add(db_event)
            
            processed_frames += 1
            
            # Log progress every 100 frames
            if processed_frames % 100 == 0:
                logger.info(f"Processed {processed_frames}/{total_frames} frames")
        
        cap.release()
        
        # Update video status
        video_record.status = "completed"
        video_record.processed_at = datetime.now()
        db.commit()
        
        logger.info(f"Video processing complete: {processed_frames} frames, {len(events)} events")
        
        return {
            "total_frames": total_frames,
            "processed_frames": processed_frames,
            "total_events": len(events),
            "events_by_type": events_by_type,
            "fps": fps,
            "events": events
        }
