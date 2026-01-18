"""
YOLO SEGMENTATION LANE DETECTION - Vietnamese Roads
====================================================
PRODUCTION-GRADE lane detection using YOLOv8 Segmentation.

Core Technology:
- YOLOv8 Segmentation model (trained on Vietnamese roads)
- Drivable area segmentation with mask extraction
- Contour-based lane boundary detection
- ROI cropping to avoid dashboard interference

Features:
- Replaces traditional Canny Edge + Hough Transform
- Handles faded, broken, and curved Vietnamese lane markings
- Real-time segmentation with high accuracy
- Kalman Filter for temporal smoothing
- Lane offset calculation and departure warnings
- ROI cropping (bottom 70% to exclude dashboard)

Model: weights/best.pt (YOLOv8 Segmentation - Vietnamese trained)
Author: Senior ADAS Engineer
Date: 2026-01-18 (YOLO Segmentation Refactor)
"""

import cv2
import numpy as np
from typing import Optional, Tuple, List, Dict
from pathlib import Path
import logging

from .kalman_filter import LaneKalmanFilter

logger = logging.getLogger(__name__)


class LaneDetectorYOLOSeg:
    """
    Production-grade YOLO Segmentation-based lane detector.
    
    Replaces traditional computer vision with deep learning segmentation.
    Optimized for Vietnamese road conditions with ROI cropping.
    """
    
    def __init__(self, model_path: Optional[str] = None, device: str = "cpu"):
        """
        Initialize YOLO Segmentation lane detector.
        
        Args:
            model_path: Path to YOLOv8 Segmentation model (.pt file)
            device: "cuda" or "cpu" for inference
        """
        self.device = device
        self.model = None
        
        # ROI Configuration (crop bottom 70% to avoid dashboard)
        self.roi_crop_top_ratio = 0.30  # Crop top 30%, keep bottom 70%
        
        # Kalman Filters for smooth lane tracking
        self.kalman_left = LaneKalmanFilter(process_variance=0.005, measurement_variance=0.05)
        self.kalman_right = LaneKalmanFilter(process_variance=0.005, measurement_variance=0.05)
        
        # Lane confidence tracking
        self.left_confidence = 0.0
        self.right_confidence = 0.0
        
        # Lane IDs
        self.left_lane_id = "LEFT_LANE_YOLO_SEG_001"
        self.right_lane_id = "RIGHT_LANE_YOLO_SEG_001"
        
        # Thresholds
        self.departure_threshold = 0.30  # 30% offset from center triggers warning
        self.min_confidence = 0.25  # Minimum confidence to use detection
        self.min_contour_area = 1000  # Minimum contour area (pixels)
        
        # Load YOLO Segmentation model
        self._load_model(model_path)
        
        logger.info(f"✅ YOLO Segmentation Lane Detector initialized on {device}")
    
    def _load_model(self, model_path: Optional[str] = None):
        """Load YOLOv8 Segmentation model with auto-detection."""
        try:
            from ultralytics import YOLO
            
            # Auto-detect model if not specified
            if model_path is None:
                # Priority order for Vietnamese lane segmentation models
                model_candidates = [
                    Path(__file__).parent.parent.parent / "models" / "lane_vip_v1.pt",
                    Path(__file__).parent.parent.parent / "models" / "lane_best.pt",
                    Path("weights/best.pt"),  # User's trained model
                    Path("models/lane_vip_v1.pt"),
                    Path("backend/models/lane_vip_v1.pt"),
                ]
                
                for candidate in model_candidates:
                    if candidate.exists():
                        model_path = str(candidate)
                        logger.info(f"🎯 Auto-detected YOLO Segmentation model: {model_path}")
                        break
                
                if model_path is None:
                    raise FileNotFoundError(
                        "❌ No YOLO Segmentation model found!\n"
                        "Please place your trained model at:\n"
                        "  - weights/best.pt\n"
                        "  - backend/models/lane_best.pt\n"
                        "  - backend/models/lane_vip_v1.pt"
                    )
            
            # Load model
            self.model = YOLO(model_path)
            self.model.to(self.device)
            
            logger.info(f"✅ YOLO Segmentation model loaded: {model_path}")
            
        except ImportError:
            logger.error("❌ ultralytics not installed! Run: pip install ultralytics")
            raise
        except Exception as e:
            logger.error(f"❌ Failed to load YOLO Segmentation model: {e}")
            raise
    
    def _apply_roi_crop(self, frame: np.ndarray) -> Tuple[np.ndarray, int]:
        """
        Apply ROI cropping to exclude dashboard (top 30%).
        
        Args:
            frame: Original frame
            
        Returns:
            Tuple of (cropped_frame, crop_offset_y)
        """
        height, width = frame.shape[:2]
        
        # Calculate crop offset (skip top 30%)
        crop_offset_y = int(height * self.roi_crop_top_ratio)
        
        # Crop frame (keep bottom 70%)
        cropped_frame = frame[crop_offset_y:, :, :]
        
        return cropped_frame, crop_offset_y
    
    def _extract_drivable_area_mask(self, results) -> Optional[np.ndarray]:
        """
        Extract drivable area mask from YOLO Segmentation results.
        
        Args:
            results: YOLO inference results
            
        Returns:
            Binary mask of drivable area (or None if no detection)
        """
        if not results or len(results) == 0:
            return None
        
        result = results[0]
        
        # Check if segmentation masks are available
        if not hasattr(result, 'masks') or result.masks is None:
            logger.warning("⚠️ No segmentation masks found in YOLO results")
            return None
        
        # Get masks
        masks = result.masks.data.cpu().numpy()
        
        if len(masks) == 0:
            return None
        
        # Combine all masks (assume all are drivable area)
        # If you have multiple classes, filter by class ID here
        combined_mask = np.zeros_like(masks[0], dtype=np.float32)
        
        for mask in masks:
            combined_mask = np.maximum(combined_mask, mask)
        
        # Convert to binary mask
        binary_mask = (combined_mask > 0.5).astype(np.uint8) * 255
        
        return binary_mask
    
    def _find_lane_contours(
        self, 
        mask: np.ndarray, 
        frame_width: int
    ) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """
        Find left and right lane boundaries from drivable area mask.
        
        Args:
            mask: Binary mask of drivable area
            frame_width: Width of frame
            
        Returns:
            Tuple of (left_contour_points, right_contour_points)
        """
        # Find contours
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if len(contours) == 0:
            return None, None
        
        # Get largest contour (main drivable area)
        largest_contour = max(contours, key=cv2.contourArea)
        
        # Filter by minimum area
        if cv2.contourArea(largest_contour) < self.min_contour_area:
            logger.debug(f"Contour area too small: {cv2.contourArea(largest_contour)}")
            return None, None
        
        # Reshape contour points
        contour_points = largest_contour.reshape(-1, 2)
        
        # Split into left and right based on x-coordinate
        mid_x = frame_width // 2
        
        left_points = contour_points[contour_points[:, 0] < mid_x]
        right_points = contour_points[contour_points[:, 0] >= mid_x]
        
        # Filter points: keep only those on the edges
        # For left lane: keep leftmost points at each y-level
        # For right lane: keep rightmost points at each y-level
        
        left_boundary = self._extract_boundary_points(left_points, side='left')
        right_boundary = self._extract_boundary_points(right_points, side='right')
        
        return left_boundary, right_boundary
    
    def _extract_boundary_points(
        self, 
        points: np.ndarray, 
        side: str = 'left'
    ) -> Optional[np.ndarray]:
        """
        Extract boundary points (leftmost or rightmost) at each y-level.
        
        Args:
            points: Array of (x, y) points
            side: 'left' or 'right'
            
        Returns:
            Boundary points array
        """
        if points is None or len(points) < 3:
            return None
        
        # Group points by y-coordinate
        y_levels = {}
        for x, y in points:
            if y not in y_levels:
                y_levels[y] = []
            y_levels[y].append(x)
        
        # Extract boundary points
        boundary_points = []
        for y, x_values in y_levels.items():
            if side == 'left':
                # Leftmost point
                boundary_x = min(x_values)
            else:
                # Rightmost point
                boundary_x = max(x_values)
            
            boundary_points.append([boundary_x, y])
        
        if len(boundary_points) < 3:
            return None
        
        return np.array(boundary_points)
    
    def _fit_polynomial(
        self, 
        points: np.ndarray, 
        degree: int = 2
    ) -> Tuple[Optional[np.ndarray], float]:
        """
        Fit polynomial curve to lane boundary points.
        
        Args:
            points: Array of (x, y) points
            degree: Polynomial degree (2 for curved lanes)
            
        Returns:
            Tuple of (coefficients, confidence)
            coefficients: Polynomial coefficients [a, b, c] for x = ay^2 + by + c
            confidence: Fit quality [0-1]
        """
        if points is None or len(points) < 3:
            return None, 0.0
        
        try:
            # Fit polynomial: x = f(y)
            y = points[:, 1]
            x = points[:, 0]
            
            # Polyfit
            coeffs = np.polyfit(y, x, degree)
            
            # Calculate fit quality (residual error)
            x_pred = np.polyval(coeffs, y)
            residuals = np.abs(x - x_pred)
            mean_residual = np.mean(residuals)
            
            # Confidence based on fit quality
            # Lower residual = higher confidence
            confidence = max(0.0, 1.0 - (mean_residual / 50.0))
            
            # Boost confidence based on number of points
            num_points = len(points)
            points_confidence = min(num_points / 100.0, 1.0)
            
            # Combined confidence
            final_confidence = 0.6 * confidence + 0.4 * points_confidence
            
            return coeffs, final_confidence
            
        except Exception as e:
            logger.debug(f"Polynomial fitting failed: {e}")
            return None, 0.0
    
    def _draw_lane_overlay(
        self, 
        frame: np.ndarray, 
        left_fit: Optional[np.ndarray], 
        right_fit: Optional[np.ndarray],
        crop_offset_y: int = 0
    ) -> np.ndarray:
        """
        Draw curved lane overlay on frame.
        
        Args:
            frame: Original frame (full size)
            left_fit: Left lane polynomial coefficients
            right_fit: Right lane polynomial coefficients
            crop_offset_y: Y-offset from ROI cropping
            
        Returns:
            Frame with lane overlay
        """
        overlay = frame.copy()
        height, width = frame.shape[:2]
        
        # Generate y coordinates (in cropped frame space)
        cropped_height = height - crop_offset_y
        y_coords_cropped = np.linspace(0, cropped_height - 1, num=100)
        
        # Convert to full frame space
        y_coords_full = y_coords_cropped + crop_offset_y
        
        left_points = []
        right_points = []
        
        # Generate left lane points
        if left_fit is not None:
            x_coords = np.polyval(left_fit, y_coords_cropped)
            x_coords = np.clip(x_coords, 0, width - 1)
            left_points = np.column_stack((x_coords, y_coords_full)).astype(np.int32)
            
            # Draw left lane line (bright cyan)
            for i in range(len(left_points) - 1):
                cv2.line(overlay, tuple(left_points[i]), tuple(left_points[i+1]), (255, 255, 0), 8)
        
        # Generate right lane points
        if right_fit is not None:
            x_coords = np.polyval(right_fit, y_coords_cropped)
            x_coords = np.clip(x_coords, 0, width - 1)
            right_points = np.column_stack((x_coords, y_coords_full)).astype(np.int32)
            
            # Draw right lane line (bright cyan)
            for i in range(len(right_points) - 1):
                cv2.line(overlay, tuple(right_points[i]), tuple(right_points[i+1]), (255, 255, 0), 8)
        
        # Fill lane area (semi-transparent cyan)
        if len(left_points) > 0 and len(right_points) > 0:
            lane_polygon = np.concatenate([left_points, right_points[::-1]])
            
            mask = np.zeros_like(frame)
            cv2.fillPoly(mask, [lane_polygon], (255, 255, 0))
            
            overlay = cv2.addWeighted(frame, 0.7, mask, 0.3, 0)
        
        return overlay
    
    def _compute_lane_offset(
        self, 
        left_fit: Optional[np.ndarray], 
        right_fit: Optional[np.ndarray],
        frame_width: int,
        cropped_height: int
    ) -> Tuple[float, str]:
        """
        Compute vehicle offset from lane center.
        
        Args:
            left_fit: Left lane polynomial
            right_fit: Right lane polynomial
            frame_width: Frame width
            cropped_height: Height of cropped frame
            
        Returns:
            Tuple of (offset_ratio, direction)
            offset_ratio: -1.0 to 1.0 (negative = left, positive = right)
            direction: "LEFT", "RIGHT", or "CENTER"
        """
        if left_fit is None or right_fit is None:
            return 0.0, "UNKNOWN"
        
        # Evaluate at bottom of cropped frame
        y_eval = cropped_height - 1
        
        left_x = np.polyval(left_fit, y_eval)
        right_x = np.polyval(right_fit, y_eval)
        
        # Lane center
        lane_center = (left_x + right_x) / 2
        
        # Vehicle center (assume camera is centered)
        vehicle_center = frame_width / 2
        
        # Offset ratio
        lane_width = right_x - left_x
        if lane_width > 0:
            offset = vehicle_center - lane_center
            offset_ratio = offset / lane_width
        else:
            offset_ratio = 0.0
        
        # Determine direction
        if abs(offset_ratio) < self.departure_threshold:
            direction = "CENTER"
        elif offset_ratio < 0:
            direction = "LEFT"
        else:
            direction = "RIGHT"
        
        return offset_ratio, direction
    
    def process_frame(self, frame: np.ndarray) -> Dict:
        """
        Process single frame for YOLO Segmentation-based lane detection.
        
        Pipeline:
        1. Apply ROI crop (exclude top 30% dashboard)
        2. Run YOLO Segmentation inference
        3. Extract drivable area mask
        4. Find lane boundary contours
        5. Fit polynomial curves
        6. Apply Kalman Filter smoothing
        7. Calculate lane offset and departure warning
        8. Draw lane overlay
        
        Args:
            frame: RGB frame from video
            
        Returns:
            Dict containing lane detection results
        """
        if self.model is None:
            logger.error("❌ YOLO Segmentation model not loaded!")
            return self._empty_result(frame)
        
        height, width = frame.shape[:2]
        
        # Step 1: Apply ROI crop (avoid dashboard)
        cropped_frame, crop_offset_y = self._apply_roi_crop(frame)
        cropped_height, cropped_width = cropped_frame.shape[:2]
        
        # Step 2: Run YOLO Segmentation inference
        try:
            results = self.model.predict(
                cropped_frame, 
                verbose=False, 
                conf=0.25,
                device=self.device
            )
        except Exception as e:
            logger.error(f"❌ YOLO inference failed: {e}")
            return self._empty_result(frame)
        
        # Step 3: Extract drivable area mask
        mask = self._extract_drivable_area_mask(results)
        
        if mask is None:
            logger.debug("No drivable area detected")
            return self._empty_result(frame)
        
        # Resize mask to cropped frame size
        mask_resized = cv2.resize(mask, (cropped_width, cropped_height))
        
        # Step 4: Find lane boundary contours
        left_points, right_points = self._find_lane_contours(mask_resized, cropped_width)
        
        # Step 5: Fit polynomial curves
        left_fit_raw, left_conf = self._fit_polynomial(left_points)
        right_fit_raw, right_conf = self._fit_polynomial(right_points)
        
        # Step 6: Apply Kalman Filter smoothing
        left_fit = self.kalman_left.update(left_fit_raw, left_conf)
        right_fit = self.kalman_right.update(right_fit_raw, right_conf)
        
        # Update confidence tracking
        self.left_confidence = left_conf
        self.right_confidence = right_conf
        
        # Step 7: Calculate lane offset
        offset, direction = self._compute_lane_offset(
            left_fit, right_fit, width, cropped_height
        )
        
        # Lane departure warning
        lane_departure = (
            abs(offset) > self.departure_threshold and 
            min(self.left_confidence, self.right_confidence) >= 0.5
        )
        
        # Step 8: Draw lane overlay
        if self.left_confidence >= self.min_confidence or self.right_confidence >= self.min_confidence:
            annotated_frame = self._draw_lane_overlay(frame, left_fit, right_fit, crop_offset_y)
        else:
            annotated_frame = frame.copy()
        
        # Add warning text
        if lane_departure:
            self._draw_warning(annotated_frame, direction)
        
        # Add model indicator
        self._draw_model_info(annotated_frame, height)
        
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
            "model_type": "YOLO_SEGMENTATION"
        }
    
    def _draw_warning(self, frame: np.ndarray, direction: str):
        """Draw lane departure warning on frame."""
        if "LEFT" in direction.upper():
            warning_text = "⚠️ LANE DEPARTURE: LEFT"
            warning_color = (0, 165, 255)  # Orange
        else:
            warning_text = "⚠️ LANE DEPARTURE: RIGHT"
            warning_color = (0, 165, 255)  # Orange
        
        # Draw warning background
        text_size = cv2.getTextSize(warning_text, cv2.FONT_HERSHEY_SIMPLEX, 1.0, 2)[0]
        cv2.rectangle(frame, (40, 50), (60 + text_size[0], 90), (0, 0, 0), -1)
        
        # Draw warning text
        cv2.putText(
            frame, warning_text, (50, 80), 
            cv2.FONT_HERSHEY_SIMPLEX, 1.0, warning_color, 2, cv2.LINE_AA
        )
    
    def _draw_model_info(self, frame: np.ndarray, height: int):
        """Draw model information on frame."""
        cv2.putText(
            frame,
            "YOLO Segmentation (VN Roads)",
            (10, height - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 255, 0),
            2,
            cv2.LINE_AA
        )
    
    def _empty_result(self, frame: np.ndarray) -> Dict:
        """Return empty result when detection fails."""
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
            "model_type": "YOLO_SEGMENTATION"
        }


if __name__ == "__main__":
    # Test module
    logging.basicConfig(level=logging.INFO)
    
    # Test with sample frame
    detector = LaneDetectorYOLOSeg(device="cpu")
    print("✅ YOLO Segmentation Lane Detector initialized successfully")
    
    # Create dummy frame
    test_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    result = detector.process_frame(test_frame)
    print(f"✅ Test inference completed: {result['model_type']}")
