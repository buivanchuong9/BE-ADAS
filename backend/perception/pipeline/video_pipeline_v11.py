"""
UNIFIED VIDEO PIPELINE - ADAS V11
==================================
Orchestrates all AI perception modules for comprehensive video analysis.

This is the SINGLE ENTRY POINT for all AI processing.
Backend calls this module ONLY.

Features:
- Dashcam video: Lane detection, object detection, distance, FCW, TSR
- In-cabin video: Driver monitoring
- Frame-by-frame processing
- Event logging
- Annotated video export

Author: Senior ADAS Engineer
Date: 2025-12-21
"""

import cv2
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional
import logging
import json
from datetime import datetime

# Import perception modules
from ..lane.lane_detector_v11 import LaneDetectorV11
from ..object.object_detector_v11 import ObjectDetectorV11
from ..distance.distance_estimator import DistanceEstimator
from ..driver.driver_monitor_v11 import DriverMonitorV11
from ..traffic.traffic_sign_v11 import TrafficSignV11

logger = logging.getLogger(__name__)


class VideoPipelineV11:
    """
    Unified ADAS video processing pipeline.
    Processes ANY driving video (dashcam or in-cabin) with REAL analysis.
    """
    
    def __init__(
        self, 
        device: str = "cpu",
        video_type: str = "dashcam"
    ):
        """
        Initialize video pipeline.
        
        Args:
            device: "cuda" or "cpu" for inference
            video_type: "dashcam" or "in_cabin"
        """
        self.device = device
        self.video_type = video_type
        
        # Initialize modules based on video type
        if video_type == "dashcam":
            logger.info("Initializing dashcam pipeline modules...")
            self.lane_detector = LaneDetectorV11(device=device)
            self.object_detector = ObjectDetectorV11(device=device)
            self.distance_estimator = DistanceEstimator()
            self.traffic_sign_detector = TrafficSignV11(device=device)
            self.driver_monitor = None
        
        elif video_type == "in_cabin":
            logger.info("Initializing in-cabin pipeline modules...")
            self.driver_monitor = DriverMonitorV11(device=device)
            self.lane_detector = None
            self.object_detector = None
            self.distance_estimator = None
            self.traffic_sign_detector = None
        
        else:
            raise ValueError(f"Unknown video_type: {video_type}. Use 'dashcam' or 'in_cabin'")
        
        # Event logging
        self.events = []
        
        logger.info(f"VideoPipelineV11 initialized for {video_type} on {device}")
    
    def detect_video_type(self, frame: np.ndarray) -> str:
        """
        Auto-detect video type from first frame.
        
        Args:
            frame: First frame of video
            
        Returns:
            "dashcam" or "in_cabin"
        """
        # Simple heuristic: check for faces
        # If face detected → likely in-cabin
        # Otherwise → dashcam
        
        if self.driver_monitor is None:
            try:
                temp_monitor = DriverMonitorV11(device=self.device)
                result = temp_monitor.process_frame(frame)
                
                if result['face_detected']:
                    logger.info("Auto-detected: in-cabin video (face found)")
                    return "in_cabin"
            except Exception as e:
                logger.warning(f"Face detection failed: {e}")
        
        logger.info("Auto-detected: dashcam video")
        return "dashcam"
    
    def process_dashcam_frame(
        self, 
        frame: np.ndarray, 
        frame_idx: int,
        timestamp: float
    ) -> Dict:
        """
        Process single dashcam frame.
        
        Args:
            frame: RGB frame
            frame_idx: Frame index
            timestamp: Timestamp in seconds
            
        Returns:
            Dict with annotated frame and analysis results
        """
        annotated = frame.copy()
        
        # 1. Lane Detection
        lane_result = self.lane_detector.process_frame(frame)
        annotated = lane_result['annotated_frame']
        
        # Log lane departure events
        if lane_result['lane_departure']:
            event = {
                "frame": frame_idx,
                "time": round(timestamp, 2),
                "type": "lane_departure",
                "level": "warning",
                "data": {
                    "direction": lane_result['direction'],
                    "offset": lane_result['offset']
                }
            }
            self.events.append(event)
        
        # 2. Object Detection
        object_result = self.object_detector.process_frame(annotated)
        annotated = object_result['annotated_frame']
        
        # 3. Distance Estimation & FCW
        if object_result['closest_vehicle']:
            closest = object_result['closest_vehicle']
            height = frame.shape[0]
            
            dist_result = self.distance_estimator.process_detection(
                closest, 
                height,
                own_speed=20.0  # Default 72 km/h
            )
            
            # Draw distance info
            annotated = self.distance_estimator.draw_distance_info(
                annotated,
                closest['bbox'],
                dist_result['distance_smoothed'],
                dist_result['risk_level'],
                dist_result['ttc']
            )
            
            # Log collision risk events
            if dist_result['risk_level'] in ['DANGER', 'CAUTION']:
                event = {
                    "frame": frame_idx,
                    "time": round(timestamp, 2),
                    "type": "collision_risk",
                    "level": dist_result['risk_level'].lower(),
                    "data": {
                        "distance": dist_result['distance_smoothed'],
                        "ttc": dist_result['ttc'],
                        "vehicle_type": closest['class_name']
                    }
                }
                self.events.append(event)
        
        # 4. Traffic Sign Recognition
        traffic_result = self.traffic_sign_detector.process_frame(annotated)
        annotated = traffic_result['annotated_frame']
        
        # Log critical traffic signs
        if traffic_result['critical_signs']:
            for sign in traffic_result['critical_signs']:
                event = {
                    "frame": frame_idx,
                    "time": round(timestamp, 2),
                    "type": "traffic_sign",
                    "level": "info",
                    "data": {
                        "sign_type": sign['sign_type'],
                        "confidence": sign['confidence']
                    }
                }
                self.events.append(event)
        
        return {
            "annotated_frame": annotated,
            "lane": lane_result,
            "objects": object_result,
            "traffic_signs": traffic_result
        }
    
    def process_incabin_frame(
        self, 
        frame: np.ndarray, 
        frame_idx: int,
        timestamp: float
    ) -> Dict:
        """
        Process single in-cabin frame.
        
        Args:
            frame: RGB frame
            frame_idx: Frame index
            timestamp: Timestamp in seconds
            
        Returns:
            Dict with annotated frame and analysis results
        """
        # Driver Monitoring
        driver_result = self.driver_monitor.process_frame(frame)
        annotated = driver_result['annotated_frame']
        
        # Log drowsiness events
        if driver_result['is_drowsy']:
            event = {
                "frame": frame_idx,
                "time": round(timestamp, 2),
                "type": "driver_drowsy",
                "level": "danger",
                "data": {
                    "reason": driver_result['drowsy_reason'],
                    "ear": driver_result['ear'],
                    "mar": driver_result['mar']
                }
            }
            self.events.append(event)
        
        return {
            "annotated_frame": annotated,
            "driver": driver_result
        }
    
    def process_video(
        self, 
        input_path: str, 
        output_path: str,
        progress_callback: Optional[callable] = None
    ) -> Dict:
        """
        Process complete video file.
        
        Args:
            input_path: Path to input video file
            output_path: Path to save annotated video
            progress_callback: Optional callback(frame_idx, total_frames, events)
            
        Returns:
            Dict containing:
                - success: Boolean
                - output_path: Path to processed video
                - events: List of detected events
                - stats: Processing statistics
        """
        logger.info(f"Processing video: {input_path}")
        logger.info(f"Video type: {self.video_type}")
        
        # Open video
        cap = cv2.VideoCapture(input_path)
        
        if not cap.isOpened():
            logger.error(f"Failed to open video: {input_path}")
            return {
                "success": False,
                "error": "Failed to open video file"
            }
        
        # Get video properties
        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        logger.info(f"Video properties: {width}x{height} @ {fps} fps, {total_frames} frames")
        
        # Create video writer
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
        
        if not out.isOpened():
            logger.error(f"Failed to create output video: {output_path}")
            cap.release()
            return {
                "success": False,
                "error": "Failed to create output video file"
            }
        
        # Reset events
        self.events = []
        
        # Process frames
        frame_idx = 0
        processed_frames = 0
        start_time = datetime.now()
        
        while True:
            ret, frame = cap.read()
            
            if not ret:
                break
            
            # Convert BGR to RGB
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Calculate timestamp
            timestamp = frame_idx / fps
            
            # Process frame based on video type
            if self.video_type == "dashcam":
                result = self.process_dashcam_frame(rgb_frame, frame_idx, timestamp)
            else:  # in_cabin
                result = self.process_incabin_frame(rgb_frame, frame_idx, timestamp)
            
            # Get annotated frame
            annotated = result['annotated_frame']
            
            # Convert RGB back to BGR for video writer
            bgr_frame = cv2.cvtColor(annotated, cv2.COLOR_RGB2BGR)
            
            # Write frame
            out.write(bgr_frame)
            
            frame_idx += 1
            processed_frames += 1
            
            # Progress callback
            if progress_callback and frame_idx % 30 == 0:
                progress_callback(frame_idx, total_frames, len(self.events))
            
            # Log progress
            if frame_idx % 100 == 0:
                logger.info(f"Processed {frame_idx}/{total_frames} frames ({frame_idx/total_frames*100:.1f}%)")
        
        # Release resources
        cap.release()
        out.release()
        
        # Calculate stats
        end_time = datetime.now()
        processing_time = (end_time - start_time).total_seconds()
        
        stats = {
            "total_frames": total_frames,
            "processed_frames": processed_frames,
            "fps": fps,
            "processing_time_seconds": round(processing_time, 2),
            "processing_fps": round(processed_frames / processing_time, 2) if processing_time > 0 else 0,
            "video_duration_seconds": round(total_frames / fps, 2),
            "event_count": len(self.events)
        }
        
        logger.info(f"Processing complete: {processed_frames} frames in {processing_time:.2f}s")
        logger.info(f"Processing speed: {stats['processing_fps']:.2f} fps")
        logger.info(f"Detected {len(self.events)} events")
        
        return {
            "success": True,
            "output_path": output_path,
            "events": self.events,
            "stats": stats
        }


def process_video(
    input_path: str,
    output_path: str,
    video_type: str = "dashcam",
    device: str = "cpu"
) -> Dict:
    """
    Main entry point for video processing.
    Backend calls THIS FUNCTION ONLY.
    
    Args:
        input_path: Path to input video
        output_path: Path to save processed video
        video_type: "dashcam" or "in_cabin"
        device: "cuda" or "cpu"
        
    Returns:
        Dict with processing results
    """
    try:
        # Create pipeline
        pipeline = VideoPipelineV11(device=device, video_type=video_type)
        
        # Process video
        result = pipeline.process_video(input_path, output_path)
        
        return result
        
    except Exception as e:
        logger.error(f"Video processing failed: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


if __name__ == "__main__":
    # Test module
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    print("Video Pipeline V11 initialized successfully")
    print("\nUsage:")
    print("  from perception.pipeline.video_pipeline_v11 import process_video")
    print("  result = process_video('input.mp4', 'output.mp4', video_type='dashcam')")
