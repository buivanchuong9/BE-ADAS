import cv2
import numpy as np
import time
import logging
from .detection.yolo_detector import YoloDetector
from .lane.lane_detector import LaneDetector
from .lane.lane_tracker import LaneTracker
from .lane.ldw_system import LaneDepartureWarning
from .tracking.byte_tracker import ByteTrack
from .collision_warning import CollisionWarningSystem

logger = logging.getLogger(__name__)

class ADASUnifiedPro:
    def __init__(self, model_path="yolo11n.pt"):
        # Initialize sub-modules
        self.lane_detector = LaneDetector()
        self.lane_tracker = LaneTracker()
        self.ldw_system = LaneDepartureWarning()
        self.tracker = ByteTrack(track_thresh=0.4, match_thresh=0.8)
        self.collision_system = CollisionWarningSystem()
        
        # Stats
        self.frame_count = 0
        
    def process_frame(self, frame, model=None):
        """
        Main processing pipeline for ADAS Pro.
        """
        start_time = time.time()
        height, width = frame.shape[:2]
        self.frame_count += 1
        
        # 1. Lane Detection
        raw_lanes = self.lane_detector.detect_lanes(frame)
        smoothed_lanes = self.lane_tracker.smooth_lanes(raw_lanes)
        
        # 2. Lane Departure Warning
        ldw_status = self.ldw_system.check_departure(smoothed_lanes, width)
        
        # 3. Object Detection (if model provided)
        detections_for_tracker = []
        raw_detections = []
        
        if model:
            # Run YOLO inference
            # Using parameters optimized for speed/accuracy
            # model.predict returns a list of Results objects
            results = model.predict(frame, conf=0.25, iou=0.45, verbose=False)[0]
            
            # Parse results for Tracker [x1, y1, x2, y2, score, class_id]
            if len(results.boxes) > 0:
                boxes = results.boxes.xyxy.cpu().numpy()
                scores = results.boxes.conf.cpu().numpy()
                classes = results.boxes.cls.cpu().numpy()
                
                # Stack into (N, 6) array
                detections_for_tracker = np.column_stack((boxes, scores, classes))
                
                # Also prepare raw detections for API response if needed (optional)
                for i, box in enumerate(boxes):
                    raw_detections.append({
                        "bbox": box.tolist(),
                        "conf": float(scores[i]),
                        "cls": results.names[int(classes[i])],
                        "class_id": int(classes[i])
                    })
            else:
                detections_for_tracker = np.empty((0, 6))

        # 4. Object Tracking (ByteTrack)
        tracks = self.tracker.update(detections_for_tracker)
        
        # 5. Collision Warning & BSM
        alerts = self.collision_system.process(tracks, smoothed_lanes)
        
        # Format tracks for output
        output_tracks = []
        for t in tracks:
            output_tracks.append({
                "track_id": t.track_id,
                "bbox": t.tlbr.tolist(),
                "class_id": t.class_id,
                "score": t.score,
                "distance": getattr(t, 'distance', -1),
                "ttc": getattr(t, 'ttc', -1),
                "relative_speed": getattr(t, 'relative_speed', 0)
            })
            
        # Add LDW alert if active
        if ldw_status['is_departing']:
            alerts.append({
                "type": "LDW",
                "level": "WARNING",
                "message": f"Lane Departure: {ldw_status['side']}",
                "side": ldw_status['side']
            })

        process_time = (time.time() - start_time) * 1000
        
        return {
            "lanes": smoothed_lanes,
            "ldw": ldw_status,
            "detections": raw_detections, # Raw YOLO output
            "tracks": output_tracks,      # Tracked objects with ID and Distance
            "alerts": alerts,
            "stats": {
                "process_time_ms": round(process_time, 2),
                "fps": round(1000/process_time, 1) if process_time > 0 else 0,
                "frame_id": self.frame_count
            }
        }
