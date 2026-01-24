"""
YOLO DETECTION LANE DETECTOR - Vietnamese Roads
================================================
Uses YOLO Detection model (bounding boxes) for lane detection.

This detector works with YOLO Detection models (not Segmentation).
Model: lane_vip_v1.pt (YOLO Detection trained on Vietnamese lanes)

Author: Senior ADAS Engineer
Date: 2026-01-18
"""

import cv2
import numpy as np
from typing import Optional, Tuple, List, Dict
from pathlib import Path
import logging

from .kalman_filter import LaneKalmanFilter

logger = logging.getLogger(__name__)


class LaneDetectorYOLOv2:
    """
    YOLO Detection-based lane detector for Vietnamese roads.
    
    Uses bounding box detections from YOLO to identify lane regions,
    then applies traditional CV methods to extract lane lines.
    """
    
    def __init__(self, model_path: Optional[str] = None, device: str = "cpu"):
        """
        Initialize YOLO Detection lane detector.
        
        Args:
            model_path: Path to YOLO Detection model (.pt file)
            device: "cuda" or "cpu"
        """
        self.device = device
        self.model = None
        
        # Kalman Filters for smoothing
        self.kalman_left = LaneKalmanFilter(process_variance=0.005, measurement_variance=0.05)
        self.kalman_right = LaneKalmanFilter(process_variance=0.005, measurement_variance=0.05)
        
        # Confidence tracking
        self.left_confidence = 0.0
        self.right_confidence = 0.0
        
        # Lane IDs
        self.left_lane_id = "LEFT_LANE_YOLO_DET_001"
        self.right_lane_id = "RIGHT_LANE_YOLO_DET_001"
        
        # Thresholds
        self.departure_threshold = 0.30
        self.min_confidence = 0.25
        
        # Load model
        self._load_model(model_path)
        
        logger.info(f"✅ YOLO Detection Lane Detector initialized on {device}")
    
    def _load_model(self, model_path: Optional[str] = None):
        """Load YOLO Detection model with validation."""
        try:
            from ultralytics import YOLO
            
            if model_path is None:
                # Auto-detect Vietnamese lane model
                candidates = [
                    Path("best_training.pt"),  # Priority 1: User confirmed this is the BEST lane model
                    Path(__file__).parent.parent.parent / "best_training.pt",
                    Path("lane_vip_v1.pt"),    # Priority 2
                    Path(__file__).parent.parent.parent / "models" / "lane_vip_v1.pt",
                    Path("models/lane_vip_v1.pt"),
                    Path("backend/models/lane_vip_v1.pt"),
                ]
                
                for candidate in candidates:
                    if candidate.exists():
                        model_path = str(candidate)
                        logger.info(f"🎯 Found model file: {model_path}")
                        break
                
                if model_path is None:
                    raise FileNotFoundError(
                        "❌ No lane detection model found!\n"
                        "Expected files:\n"
                        "  - best_training.pt (root directory)\n"
                        "  - backend/models/lane_vip_v1.pt\n"
                        "  - backend/models/lane_best.pt"
                    )
            
            # Load model
            logger.info(f"📦 Loading YOLO model from: {model_path}")
            self.model = YOLO(model_path)
            
            # 🛑 CRITICAL VALIDATION: Check if this is a lane detection model
            model_classes = self.model.names
            logger.info(f"📋 Model classes: {model_classes}")
            
            # Expected class for lane detection: 'drivable_area' or 'lane'
            expected_classes = ['drivable_area', 'lane', 'road']
            
            if len(model_classes) == 0:
                raise ValueError(
                    f"❌ Model has no classes! This is not a valid YOLO model.\n"
                    f"File: {model_path}"
                )
            
            # Check if model is for vehicle detection (wrong model!)
            vehicle_classes = ['person', 'car', 'truck', 'bus', 'motorcycle', 'bicycle']
            if any(cls in str(model_classes.values()).lower() for cls in vehicle_classes):
                raise ValueError(
                    f"❌ WRONG MODEL! This is a VEHICLE detection model, not LANE detection!\n"
                    f"Model classes: {model_classes}\n"
                    f"Expected: {expected_classes}\n"
                    f"File: {model_path}\n\n"
                    f"Please use the correct lane detection model (best_training.pt with 'drivable_area' class)"
                )
            
            # Check if model has expected lane classes
            has_lane_class = any(
                expected in str(model_classes.values()).lower() 
                for expected in expected_classes
            )
            
            if not has_lane_class:
                logger.warning(
                    f"⚠️ Model classes don't match expected lane classes.\n"
                    f"Found: {model_classes}\n"
                    f"Expected one of: {expected_classes}\n"
                    f"Proceeding anyway, but results may be incorrect."
                )
            
            self.model.to(self.device)
            
            logger.info(f"✅ YOLO Lane Detection model loaded successfully")
            logger.info(f"   Model: {model_path}")
            logger.info(f"   Classes: {model_classes}")
            logger.info(f"   Device: {self.device}")
            
        except ImportError:
            logger.error("❌ ultralytics not installed! Run: pip install ultralytics")
            raise
        except Exception as e:
            logger.error(f"❌ Failed to load YOLO model: {e}")
            raise
    
    def _extract_lane_regions(self, results, frame_shape: Tuple[int, int]) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """
        Extract lane regions from YOLO detection bounding boxes.
        
        Args:
            results: YOLO detection results
            frame_shape: (height, width)
            
        Returns:
            Tuple of (left_region_mask, right_region_mask)
        """
        height, width = frame_shape
        mid_x = width // 2
        
        left_mask = np.zeros((height, width), dtype=np.uint8)
        right_mask = np.zeros((height, width), dtype=np.uint8)
        
        if not results or len(results) == 0:
            return None, None
        
        result = results[0]
        
        # PRIORITY: Check for segmentation masks (much better than boxes)
        if hasattr(result, 'masks') and result.masks is not None:
            # Process masks
            # masks.xy is a list of points for each mask
            for xy in result.masks.xy:
                if len(xy) == 0: continue
                
                # Convert to integer points
                points = xy.astype(np.int32)
                
                # Calculate centroid
                M = cv2.moments(points)
                if M['m00'] != 0:
                    cx = int(M['m10'] / M['m00'])
                    cy = int(M['m01'] / M['m00'])
                    
                    # Determine side
                    if cx < mid_x:
                        cv2.fillPoly(left_mask, [points], 255)
                    else:
                        cv2.fillPoly(right_mask, [points], 255)
                        
            # Use masks directly if found
            if np.any(left_mask) or np.any(right_mask):
                return left_mask if np.any(left_mask) else None, right_mask if np.any(right_mask) else None

        # FALLBACK: Check for bounding boxes
        if not hasattr(result, 'boxes') or result.boxes is None:
            return None, None
        
        boxes = result.boxes.xyxy.cpu().numpy()
        confidences = result.boxes.conf.cpu().numpy()
        
        if len(boxes) == 0:
            return None, None
        
        # Process each detection
        for box, conf in zip(boxes, confidences):
            if conf < 0.25:  # Skip low confidence
                continue
            
            x1, y1, x2, y2 = map(int, box)
            center_x = (x1 + x2) // 2
            
            # Determine if left or right lane
            if center_x < mid_x:
                # Left lane
                cv2.rectangle(left_mask, (x1, y1), (x2, y2), 255, -1)
            else:
                # Right lane
                cv2.rectangle(right_mask, (x1, y1), (x2, y2), 255, -1)
        
        left_region = left_mask if np.any(left_mask) else None
        right_region = right_mask if np.any(right_mask) else None
        
        return left_region, right_region
    
    def _extract_lane_line_from_region(self, region_mask: np.ndarray, frame: np.ndarray, side: str = 'left') -> Tuple[Optional[np.ndarray], float]:
        """
        Extract lane line from detected region using edge detection.
        
        Args:
            region_mask: Binary mask of lane region
            frame: Original frame
            side: 'left' or 'right'
            
        Returns:
            Tuple of (lane_points, confidence)
        """
        if region_mask is None:
            return None, 0.0
        
        # Apply mask to frame
        masked_frame = cv2.bitwise_and(frame, frame, mask=region_mask)
        
        # Convert to grayscale
        gray = cv2.cvtColor(masked_frame, cv2.COLOR_RGB2GRAY)
        
        # Edge detection
        edges = cv2.Canny(gray, 30, 90)
        
        # Find contours
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if len(contours) == 0:
            return None, 0.0
        
        # Get largest contour
        largest_contour = max(contours, key=cv2.contourArea)
        
        if cv2.contourArea(largest_contour) < 100:
            return None, 0.0
        
        # Extract points
        points = largest_contour.reshape(-1, 2)
        
        # Calculate confidence based on number of points
        confidence = min(len(points) / 50.0, 1.0)
        
        return points, confidence
    
    def _fit_polynomial(self, points: np.ndarray, degree: int = 2) -> Tuple[Optional[np.ndarray], float]:
        """Fit polynomial to lane points."""
        if points is None or len(points) < 3:
            return None, 0.0
        
        try:
            y = points[:, 1]
            x = points[:, 0]
            
            coeffs = np.polyfit(y, x, degree)
            
            # Calculate fit quality
            x_pred = np.polyval(coeffs, y)
            residuals = np.abs(x - x_pred)
            mean_residual = np.mean(residuals)
            
            confidence = max(0.0, 1.0 - (mean_residual / 50.0))
            
            return coeffs, confidence
            
        except Exception as e:
            logger.debug(f"Polynomial fitting failed: {e}")
            return None, 0.0
    
    def _draw_lane(self, frame: np.ndarray, left_fit: Optional[np.ndarray], right_fit: Optional[np.ndarray]) -> np.ndarray:
        """Draw lane overlay on frame."""
        overlay = frame.copy()
        height, width = frame.shape[:2]
        
        y_coords = np.linspace(int(height * 0.6), height, num=100)
        
        left_points = []
        right_points = []
        
        # Left lane
        if left_fit is not None:
            x_coords = np.polyval(left_fit, y_coords)
            x_coords = np.clip(x_coords, 0, width - 1)
            left_points = np.column_stack((x_coords, y_coords)).astype(np.int32)
            
            for i in range(len(left_points) - 1):
                cv2.line(overlay, tuple(left_points[i]), tuple(left_points[i+1]), (0, 255, 0), 8)
        
        # Right lane
        if right_fit is not None:
            x_coords = np.polyval(right_fit, y_coords)
            x_coords = np.clip(x_coords, 0, width - 1)
            right_points = np.column_stack((x_coords, y_coords)).astype(np.int32)
            
            for i in range(len(right_points) - 1):
                cv2.line(overlay, tuple(right_points[i]), tuple(right_points[i+1]), (0, 255, 0), 8)
        
        # Fill lane area
        if len(left_points) > 0 and len(right_points) > 0:
            lane_polygon = np.concatenate([left_points, right_points[::-1]])
            mask = np.zeros_like(frame)
            cv2.fillPoly(mask, [lane_polygon], (0, 255, 0))
            overlay = cv2.addWeighted(frame, 0.7, mask, 0.3, 0)
        
        return overlay
    
    def _compute_lane_offset(self, left_fit: Optional[np.ndarray], right_fit: Optional[np.ndarray], frame_width: int, frame_height: int) -> Tuple[float, str]:
        """Compute vehicle offset from lane center."""
        if left_fit is None or right_fit is None:
            return 0.0, "UNKNOWN"
        
        y_eval = frame_height - 1
        
        left_x = np.polyval(left_fit, y_eval)
        right_x = np.polyval(right_fit, y_eval)
        
        lane_center = (left_x + right_x) / 2
        vehicle_center = frame_width / 2
        
        lane_width = right_x - left_x
        if lane_width > 0:
            offset = vehicle_center - lane_center
            offset_ratio = offset / lane_width
        else:
            offset_ratio = 0.0
        
        if abs(offset_ratio) < self.departure_threshold:
            direction = "CENTER"
        elif offset_ratio < 0:
            direction = "LEFT"
        else:
            direction = "RIGHT"
        
        return offset_ratio, direction
    
    def process_frame(self, frame: np.ndarray) -> Dict:
        """
        Process frame for YOLO Detection-based lane detection.
        
        Args:
            frame: RGB frame
            
        Returns:
            Dict with lane detection results
        """
        if self.model is None:
            return self._empty_result(frame)
        
        height, width = frame.shape[:2]
        
        # Run YOLO detection
        try:
            # Lower confidence for better detection on challenging roads
            results = self.model(frame, verbose=False, conf=0.15)
        except Exception as e:
            logger.error(f"YOLO inference failed: {e}")
            return self._empty_result(frame)
        
        # Extract lane regions from detections
        left_region, right_region = self._extract_lane_regions(results, (height, width))
        
        # Extract lane lines from regions
        left_points, left_conf_raw = self._extract_lane_line_from_region(left_region, frame, 'left')
        right_points, right_conf_raw = self._extract_lane_line_from_region(right_region, frame, 'right')
        
        # Fit polynomials
        left_fit_raw, left_fit_conf = self._fit_polynomial(left_points)
        right_fit_raw, right_fit_conf = self._fit_polynomial(right_points)
        
        # Combine confidences
        left_conf = left_conf_raw * left_fit_conf
        right_conf = right_conf_raw * right_fit_conf
        
        # Apply Kalman Filter
        left_fit = self.kalman_left.update(left_fit_raw, left_conf)
        right_fit = self.kalman_right.update(right_fit_raw, right_conf)
        
        # Update confidence
        self.left_confidence = left_conf
        self.right_confidence = right_conf
        
        annotated_frame = frame.copy()

        # VISUALIZATION: Overlay Masks (The "Premium Green" Look for Single Frame)
        lane_overlay = np.zeros_like(annotated_frame)
        has_seg = False
        
        if left_region is not None:
            lane_overlay[left_region > 0] = [0, 255, 0]
            has_seg = True
        if right_region is not None:
            lane_overlay[right_region > 0] = [0, 255, 0]
            has_seg = True
            
        if has_seg:
            cv2.addWeighted(lane_overlay, 0.4, annotated_frame, 1.0, 0, annotated_frame)
        
        # Draw lanes
        if self.left_confidence >= self.min_confidence or self.right_confidence >= self.min_confidence:
            annotated_frame = self._draw_lane(annotated_frame, left_fit, right_fit)
        else:
            # Keep the overlay if we have it
            pass
        
        # Compute offset
        offset, direction = self._compute_lane_offset(left_fit, right_fit, width, height)
        
        # Lane departure
        lane_departure = (
            abs(offset) > self.departure_threshold and 
            min(self.left_confidence, self.right_confidence) >= 0.5
        )
        
        # Add warning
        if lane_departure:
            self._draw_warning(annotated_frame, direction)
        
        # Add model info
        cv2.putText(
            annotated_frame,
            "YOLO Detection Lane (VN)",
            (10, height - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 0),
            2,
            cv2.LINE_AA
        )
        
        return {
            "annotated_frame": annotated_frame,
            "left_fit": left_fit,
            "right_fit": right_fit,
            "left_confidence": float(self.left_confidence),
            "right_confidence": float(self.right_confidence),
            "left_lane_id": self.left_lane_id,
            "right_lane_id": self.right_lane_id,
            "offset": float(offset),
            "direction": direction,
            "lane_departure": lane_departure,
            "is_departed": lane_departure,
            "model_type": "YOLO_DETECTION"
        }
    
    
    def process_batch(self, frames: List[np.ndarray]) -> List[Dict]:
        """
        Process batch of frames for lane detection (GPU Optimized).
        
        Args:
            frames: List of RGB frames
            
        Returns:
            List of result dicts
        """
        if not frames:
            return []
            
        if self.model is None:
            return [self._empty_result(f) for f in frames]
            
        height, width = frames[0].shape[:2]
        results = []
        
        try:
            # Run YOLO batch inference - LOWER CONFIDENCE for Vietnamese roads (often obscure)
            batch_results = self.model(frames, verbose=False, conf=0.15)
            
            # Post-process each frame (CPU bound, but unavoidable)
            for i, frame in enumerate(frames):
                yolo_result = batch_results[i]
                
                # Extract regions - Wrap yolo_result in list because helper expects a list
                left_region, right_region = self._extract_lane_regions([yolo_result], (height, width))
                
                # Extract lines
                left_points, left_conf_raw = self._extract_lane_line_from_region(left_region, frame, 'left')
                right_points, right_conf_raw = self._extract_lane_line_from_region(right_region, frame, 'right')
                
                # Create result dict (simplified version of process_frame logic)
                # Note: We skip Kalman filter in batch mode for simplicity or implement it if need consistent tracking
                # Here we use basic fit without tracking state update for speed
                
                left_fit, left_conf = self._fit_polynomial(left_points)
                right_fit, right_conf = self._fit_polynomial(right_points)
                
                # Calc confidence
                left_conf *= left_conf_raw
                right_conf *= right_conf_raw
                
                annotated_frame = frame.copy()

                # VISUALIZATION: Draw Segmentation Masks (The "Premium Green" Look)
                # Ensure we have uint8 masks
                lane_overlay = np.zeros_like(annotated_frame)
                has_seg = False
                
                if left_region is not None:
                    lane_overlay[left_region > 0] = [0, 255, 0] # Green for left
                    has_seg = True
                    
                if right_region is not None:
                    lane_overlay[right_region > 0] = [0, 255, 0] # Green for right (or maybe same color)
                    has_seg = True
                    
                if has_seg:
                    # Apply semi-transparent overlay
                    cv2.addWeighted(lane_overlay, 0.4, annotated_frame, 1.0, 0, annotated_frame)
                
                # Draw lanes (Polynomial Lines - Borders)
                if left_conf >= self.min_confidence or right_conf >= self.min_confidence:
                    annotated_frame = self._draw_lane(annotated_frame, left_fit, right_fit)
                else:
                    # If low confidence on fit but we have seg, we still have the overlay
                    pass
                    
                # Offset
                offset, direction = self._compute_lane_offset(left_fit, right_fit, width, height)
                
                # Departure
                is_departed = (abs(offset) > self.departure_threshold and min(left_conf, right_conf) >= 0.5)
                
                if is_departed:
                    self._draw_warning(annotated_frame, direction)
                
                results.append({
                    "annotated_frame": annotated_frame,
                    "is_departed": is_departed,
                    "offset": float(offset),
                    "departure_direction": direction,
                    # Add minimum fields expected by pipeline
                    "left_fit": left_fit,
                    "right_fit": right_fit
                })
                
        except Exception as e:
            logger.error(f"Batch lane detection failed: {e}")
            return [self.process_frame(f) for f in frames] # Fallback
            
        return results

    def _draw_warning(self, frame: np.ndarray, direction: str):
        """Draw lane departure warning."""
        if "LEFT" in direction.upper():
            warning_text = "⚠️ LANE DEPARTURE: LEFT"
        else:
            warning_text = "⚠️ LANE DEPARTURE: RIGHT"
        
        warning_color = (0, 165, 255)
        
        text_size = cv2.getTextSize(warning_text, cv2.FONT_HERSHEY_SIMPLEX, 1.0, 2)[0]
        cv2.rectangle(frame, (40, 50), (60 + text_size[0], 90), (0, 0, 0), -1)
        cv2.putText(frame, warning_text, (50, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.0, warning_color, 2, cv2.LINE_AA)
    
    def _empty_result(self, frame: np.ndarray) -> Dict:
        """Return empty result."""
        return {
            "annotated_frame": frame.copy(),
            "left_fit": None,
            "right_fit": None,
            "left_confidence": 0.0,
            "right_confidence": 0.0,
            "left_lane_id": self.left_lane_id,
            "right_lane_id": self.right_lane_id,
            "offset": 0.0,
            "direction": "UNKNOWN",
            "lane_departure": False,
            "is_departed": False,
            "model_type": "YOLO_DETECTION"
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    detector = LaneDetectorYOLOv2(device="cpu")
    print("✅ YOLO Detection Lane Detector initialized")
