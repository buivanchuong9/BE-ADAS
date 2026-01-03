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
        self.events = []
        
        # PRODUCTION OPTIMIZATION: Batch size for GPU inference
        # Process 4-8 frames at once for better GPU utilization
        self.batch_size = 6 if device == "cuda" else 1
        
        logger.info(f"VideoPipelineV11 initializing (device={device}, type={video_type}, batch_size={self.batch_size})")
        
        # Log GPU info if using CUDA
        if device == "cuda":
            try:
                import torch
                if torch.cuda.is_available():
                    gpu_name = torch.cuda.get_device_name(0)
                    gpu_memory = torch.cuda.get_device_properties(0).total_memory / (1024**3)
                    logger.info(f"🎮 GPU Detected: {gpu_name} ({gpu_memory:.1f} GB VRAM)")
                    logger.info(f"🚀 GPU acceleration enabled for video processing")
                else:
                    logger.warning("⚠️ CUDA requested but not available, falling back to CPU")
                    self.device = "cpu"
            except ImportError:
                logger.warning("⚠️ PyTorch not installed, falling back to CPU")
                self.device = "cpu"
        
        # Initialize modules based on video type
        if video_type == "dashcam":
            logger.info("Initializing dashcam pipeline modules...")
            try:
                self.lane_detector = LaneDetectorV11(device=self.device)
                logger.info("  ✓ Lane detector initialized")
                
                self.object_detector = ObjectDetectorV11(device=self.device)
                logger.info("  ✓ Object detector initialized")
                
                self.distance_estimator = DistanceEstimator()
                logger.info("  ✓ Distance estimator initialized")
                
                self.traffic_sign_detector = TrafficSignV11(device=self.device)
                logger.info("  ✓ Traffic sign detector initialized")
                
                self.driver_monitor = None
            except Exception as e:
                logger.error(f"Failed to initialize dashcam modules: {e}")
                raise
        
        elif video_type == "in_cabin":
            logger.info("Initializing in-cabin pipeline modules...")
            try:
                self.driver_monitor = DriverMonitorV11(device=self.device)
                logger.info("  ✓ Driver monitor initialized")
                
                self.lane_detector = None
                self.object_detector = None
                self.distance_estimator = None
                self.traffic_sign_detector = None
            except Exception as e:
                logger.error(f"Failed to initialize in-cabin modules: {e}")
                raise
        
        else:
            raise ValueError(f"Unknown video_type: {video_type}. Use 'dashcam' or 'in_cabin'")
        
        # Event logging
        self.events = []
        
        logger.info(f"✅ VideoPipelineV11 ready: {video_type} on {self.device}")
    
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
    
    def _process_frame_batch(
        self,
        frames: List[np.ndarray],
        frame_indices: List[int],
        timestamps: List[float],
        video_writer,
        fps: float,
        total_frames: int,
        progress_callback: Optional[callable],
        start_time: datetime
    ):
        """
        Process a batch of frames (PRODUCTION OPTIMIZATION).
        Uses batch inference for better GPU utilization.
        """
        batch_size = len(frames)
        
        # Process based on video type
        if self.video_type == "dashcam":
            # Batch object detection (GPU optimized)
            if hasattr(self.object_detector, 'detect_batch'):
                batch_detections = self.object_detector.detect_batch(frames)
            else:
                batch_detections = [self.object_detector.detect(f) for f in frames]
            
            # Process each frame with batch detections
            for i, (frame, frame_idx, timestamp) in enumerate(zip(frames, frame_indices, timestamps)):
                detections = batch_detections[i]
                result = self._process_dashcam_frame_with_detections(
                    frame, frame_idx, timestamp, detections
                )
                
                bgr_frame = cv2.cvtColor(result['annotated_frame'], cv2.COLOR_RGB2BGR)
                video_writer.write(bgr_frame)
                
                if frame_idx % 30 == 0:
                    self._log_progress(frame_idx, total_frames, start_time)
                    if progress_callback:
                        progress_callback(frame_idx, total_frames, len(self.events))
        
        else:  # in_cabin
            for frame, frame_idx, timestamp in zip(frames, frame_indices, timestamps):
                result = self.process_incabin_frame(frame, frame_idx, timestamp)
                bgr_frame = cv2.cvtColor(result['annotated_frame'], cv2.COLOR_RGB2BGR)
                video_writer.write(bgr_frame)
                
                if frame_idx % 30 == 0:
                    self._log_progress(frame_idx, total_frames, start_time)
                    if progress_callback:
                        progress_callback(frame_idx, total_frames, len(self.events))
    
    def _process_dashcam_frame_with_detections(
        self,
        frame: np.ndarray,
        frame_idx: int,
        timestamp: float,
        detections: List[Dict]
    ) -> Dict:
        """Process dashcam frame with pre-computed detections."""
        height, width = frame.shape[:2]
        annotated = frame.copy()
        
        # 1. Lane Detection
        lane_result = self.lane_detector.process_frame(annotated)
        annotated = lane_result['annotated_frame']
        
        if lane_result['is_departed']:
            self.events.append({
                "frame": frame_idx,
                "time": round(timestamp, 2),
                "type": "lane_departure",
                "level": "warning",
                "data": {"direction": lane_result['departure_direction'], "offset": lane_result['offset']}
            })
        
        # 2. Object Detection (use pre-computed)
        annotated = self.object_detector.draw_detections(annotated, detections)
        front_vehicles = self.object_detector.filter_front_vehicles(detections, height)
        closest = self.object_detector.get_closest_vehicle(front_vehicles)
        
        # 3. Distance & Collision
        if closest:
            dist_result = self.distance_estimator.estimate_distance(closest, height)
            annotated = self.distance_estimator.draw_distance_info(
                annotated, closest['bbox'], dist_result['distance_smoothed'],
                dist_result['risk_level'], dist_result['ttc']
            )
            
            if dist_result['risk_level'] in ['DANGER', 'CAUTION']:
                self.events.append({
                    "frame": frame_idx, "time": round(timestamp, 2),
                    "type": "collision_risk", "level": dist_result['risk_level'].lower(),
                    "data": {"distance": dist_result['distance_smoothed'], "ttc": dist_result['ttc'], 
                            "vehicle_type": closest['class_name']}
                })
        
        # 4. Traffic Signs
        traffic_result = self.traffic_sign_detector.process_frame(annotated)
        annotated = traffic_result['annotated_frame']
        
        if traffic_result['critical_signs']:
            for sign in traffic_result['critical_signs']:
                self.events.append({
                    "frame": frame_idx, "time": round(timestamp, 2),
                    "type": "traffic_sign", "level": "info",
                    "data": {"sign_type": sign['sign_type'], "confidence": sign['confidence']}
                })
        
        return {
            "annotated_frame": annotated,
            "lane": lane_result,
            "objects": {"detections": detections, "front_vehicles": front_vehicles, "closest_vehicle": closest},
            "traffic_signs": traffic_result
        }
    
    def _log_progress(self, frame_idx: int, total_frames: int, start_time: datetime):
        """Log processing progress."""
        elapsed = (datetime.now() - start_time).total_seconds()
        progress_pct = (frame_idx / total_frames) * 100
        
        if elapsed > 0:
            fps_processing = frame_idx / elapsed
            remaining_frames = total_frames - frame_idx
            eta_seconds = remaining_frames / fps_processing if fps_processing > 0 else 0
            eta_str = f"{int(eta_seconds // 60)}m {int(eta_seconds % 60)}s"
        else:
            fps_processing = 0
            eta_str = "calculating..."
        
        if self.device == "cuda":
            try:
                import torch
                gpu_mem_used = torch.cuda.memory_allocated(0) / (1024**2)
                gpu_mem_cached = torch.cuda.memory_reserved(0) / (1024**2)
                logger.info(
                    f"📊 {frame_idx}/{total_frames} ({progress_pct:.1f}%) | "
                    f"{fps_processing:.1f} fps | ETA: {eta_str} | Events: {len(self.events)} | "
                    f"GPU: {gpu_mem_used:.0f}/{gpu_mem_cached:.0f}MB"
                )
            except:
                logger.info(f"📊 {frame_idx}/{total_frames} ({progress_pct:.1f}%) | {fps_processing:.1f} fps | ETA: {eta_str} | Events: {len(self.events)}")
        else:
            logger.info(f"📊 {frame_idx}/{total_frames} ({progress_pct:.1f}%) | {fps_processing:.1f} fps | ETA: {eta_str} | Events: {len(self.events)}")
    
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
                "error": "Failed to open video file. File may be corrupted or format not supported."
            }
        
        # Get video properties
        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        # Validate video properties
        if fps == 0 or width == 0 or height == 0:
            cap.release()
            logger.error(f"Invalid video properties: fps={fps}, size={width}x{height}")
            return {
                "success": False,
                "error": f"Invalid video properties: fps={fps}, resolution={width}x{height}"
            }
        
        logger.info(f"Video properties: {width}x{height} @ {fps} fps, {total_frames} frames")
        
        # Create video writer
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
        
        if not out.isOpened():
            logger.error(f"Failed to create output video: {output_path}")
            cap.release()
            return {
                "success": False,
                "error": "Failed to create output video file. Check disk space and permissions."
            }
        
        # Reset events
        self.events = []
        
        # Process frames
        frame_idx = 0
        processed_frames = 0
        start_time = datetime.now()
        last_log_time = start_time
        
        # PRODUCTION OPTIMIZATION: Batch frame buffer
        frame_buffer = []
        frame_indices = []
        frame_timestamps = []
        
        logger.info(f"🎬 Starting video processing: {total_frames} frames @ {fps:.1f} fps (batch_size={self.batch_size})")
        
        while True:
            ret, frame = cap.read()
            
            if not ret:
                # Process remaining frames in buffer
                if frame_buffer:
                    self._process_frame_batch(
                        frame_buffer, frame_indices, frame_timestamps, 
                        out, fps, total_frames, progress_callback, start_time
                    )
                break
            
            try:
                # Convert BGR to RGB
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                # Calculate timestamp
                timestamp = frame_idx / fps
                
                # Add to batch buffer
                frame_buffer.append(rgb_frame)
                frame_indices.append(frame_idx)
                frame_timestamps.append(timestamp)
                
                frame_idx += 1
                
                # Process batch when buffer is full
                if len(frame_buffer) >= self.batch_size:
                    self._process_frame_batch(
                        frame_buffer, frame_indices, frame_timestamps,
                        out, fps, total_frames, progress_callback, start_time
                    )
                    processed_frames += len(frame_buffer)
                    
                    # Clear buffer
                    frame_buffer = []
                    frame_indices = []
                    frame_timestamps = []
                
            except Exception as e:
                logger.error(f"❌ Error processing frame {frame_idx}: {e}")
                # Continue with next frame instead of crashing
                frame_idx += 1
                continue
        
        # Release resources
        cap.release()
        out.release()
        
        # Add remaining frames to processed count
        processed_frames = frame_idx
        
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
