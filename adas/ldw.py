"""
Lane Departure Warning (LDW) Module
Cảnh báo lệch làn đường

Features:
- Detect lane lines using OpenCV + Hough Transform
- Track lane position and vehicle position
- Warn driver if departing from lane
- Visualize lane lines on frame
"""

import cv2
import numpy as np
from typing import Dict, List, Tuple, Optional
from collections import deque

from .config import (
    LDW_ROI_TOP,
    LDW_ROI_BOTTOM,
    HOUGH_RHO,
    HOUGH_THETA,
    HOUGH_THRESHOLD,
    HOUGH_MIN_LINE_LEN,
    HOUGH_MAX_LINE_GAP,
    LANE_MIN_SLOPE,
    LANE_MAX_SLOPE,
    LANE_WIDTH_MIN,
    LANE_WIDTH_MAX,
    DEPARTURE_THRESHOLD,
    DEPARTURE_MEMORY,
    ALERT_NONE,
    ALERT_WARNING,
    ALERT_DANGER,
    COLOR_GREEN,
    COLOR_YELLOW,
    COLOR_RED,
    COLOR_CYAN,
    COLOR_WHITE,
)


class LaneDepartureWarning:
    """
    Lane Departure Warning System
    
    Detects lane markings using computer vision and warns
    if vehicle is departing from the lane.
    """
    
    def __init__(
        self,
        roi_top: float = LDW_ROI_TOP,
        roi_bottom: float = LDW_ROI_BOTTOM,
    ):
        """
        Initialize LDW system
        
        Args:
            roi_top: Top of region of interest (ratio of image height)
            roi_bottom: Bottom of region of interest (ratio of image height)
        """
        self.roi_top = roi_top
        self.roi_bottom = roi_bottom
        
        # Lane tracking
        self.left_lane_history = deque(maxlen=10)
        self.right_lane_history = deque(maxlen=10)
        self.departure_counter = 0
        
        # Statistics
        self.frame_count = 0
        self.lanes_detected_count = 0
        self.left_departure_count = 0
        self.right_departure_count = 0
        
        print("✅ LDW initialized")
    
    def detect_lanes(
        self,
        frame: np.ndarray
    ) -> Dict:
        """
        Detect lane lines in frame
        
        Args:
            frame: Input image (BGR)
            
        Returns:
            Dict with left_lane, right_lane, center_offset, alert_level
        """
        self.frame_count += 1
        
        # Get frame dimensions
        height, width = frame.shape[:2]
        
        # Define ROI
        roi_y_top = int(height * self.roi_top)
        roi_y_bottom = int(height * self.roi_bottom)
        
        # Create ROI mask
        roi = frame[roi_y_top:roi_y_bottom, :]
        
        # Preprocess: Convert to grayscale
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        
        # Apply Gaussian blur to reduce noise
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        
        # Edge detection using Canny
        edges = cv2.Canny(blurred, 50, 150)
        
        # Detect lines using Hough Transform
        lines = cv2.HoughLinesP(
            edges,
            rho=HOUGH_RHO,
            theta=HOUGH_THETA,
            threshold=HOUGH_THRESHOLD,
            minLineLength=HOUGH_MIN_LINE_LEN,
            maxLineGap=HOUGH_MAX_LINE_GAP
        )
        
        # Separate left and right lanes
        left_lines = []
        right_lines = []
        
        if lines is not None:
            for line in lines:
                x1, y1, x2, y2 = line[0]
                
                # Adjust y coordinates to full frame
                y1 += roi_y_top
                y2 += roi_y_top
                
                # Calculate slope
                if x2 - x1 == 0:
                    continue
                slope = (y2 - y1) / (x2 - x1)
                
                # Filter by slope
                if abs(slope) < LANE_MIN_SLOPE or abs(slope) > LANE_MAX_SLOPE:
                    continue
                
                # Separate left (negative slope) and right (positive slope)
                if slope < 0:
                    left_lines.append((x1, y1, x2, y2, slope))
                else:
                    right_lines.append((x1, y1, x2, y2, slope))
        
        # Average and extrapolate lane lines
        left_lane = self._average_lane(left_lines, height, roi_y_top, roi_y_bottom)
        right_lane = self._average_lane(right_lines, height, roi_y_top, roi_y_bottom)
        
        # Update lane history for smoothing
        if left_lane is not None:
            self.left_lane_history.append(left_lane)
        if right_lane is not None:
            self.right_lane_history.append(right_lane)
        
        # Get smoothed lanes
        left_lane_smooth = self._get_smooth_lane(self.left_lane_history)
        right_lane_smooth = self._get_smooth_lane(self.right_lane_history)
        
        # Calculate lane center and vehicle offset
        center_offset = None
        lane_width = None
        
        if left_lane_smooth and right_lane_smooth:
            self.lanes_detected_count += 1
            
            # Calculate lane center at bottom of frame
            left_x = left_lane_smooth[2]  # x2 of left lane
            right_x = right_lane_smooth[2]  # x2 of right lane
            
            lane_center = (left_x + right_x) / 2
            vehicle_center = width / 2
            center_offset = vehicle_center - lane_center
            lane_width = abs(right_x - left_x)
        
        # Determine alert level
        alert_level = self._get_alert_level(center_offset, width, lane_width)
        
        # Update statistics
        if alert_level == ALERT_WARNING or alert_level == ALERT_DANGER:
            if center_offset < 0:
                self.left_departure_count += 1
            else:
                self.right_departure_count += 1
        
        return {
            'left_lane': left_lane_smooth,
            'right_lane': right_lane_smooth,
            'center_offset': center_offset,
            'lane_width': lane_width,
            'alert_level': alert_level,
            'departure_direction': 'left' if center_offset and center_offset < 0 else 'right',
        }
    
    def _average_lane(
        self,
        lines: List[Tuple],
        frame_height: int,
        roi_top: int,
        roi_bottom: int
    ) -> Optional[Tuple[int, int, int, int]]:
        """
        Average multiple line segments into a single lane line
        
        Args:
            lines: List of (x1, y1, x2, y2, slope)
            frame_height: Height of frame
            roi_top: Top y-coordinate of ROI
            roi_bottom: Bottom y-coordinate of ROI
            
        Returns:
            (x1, y1, x2, y2) of averaged lane or None
        """
        if not lines:
            return None
        
        # Average slope and intercept
        slopes = [line[4] for line in lines]
        avg_slope = np.mean(slopes)
        
        # Calculate average intercept (b in y = mx + b)
        intercepts = []
        for x1, y1, x2, y2, slope in lines:
            intercept = y1 - slope * x1
            intercepts.append(intercept)
        avg_intercept = np.mean(intercepts)
        
        # Extrapolate line to ROI boundaries
        y1 = roi_top
        y2 = roi_bottom
        
        if avg_slope != 0:
            x1 = int((y1 - avg_intercept) / avg_slope)
            x2 = int((y2 - avg_intercept) / avg_slope)
        else:
            return None
        
        return (x1, y1, x2, y2)
    
    def _get_smooth_lane(
        self,
        lane_history: deque
    ) -> Optional[Tuple[int, int, int, int]]:
        """
        Get smoothed lane from history
        
        Args:
            lane_history: Deque of recent lane detections
            
        Returns:
            Smoothed lane coordinates or None
        """
        if not lane_history:
            return None
        
        # Average recent detections
        x1_avg = int(np.mean([lane[0] for lane in lane_history]))
        y1_avg = int(np.mean([lane[1] for lane in lane_history]))
        x2_avg = int(np.mean([lane[2] for lane in lane_history]))
        y2_avg = int(np.mean([lane[3] for lane in lane_history]))
        
        return (x1_avg, y1_avg, x2_avg, y2_avg)
    
    def _get_alert_level(
        self,
        center_offset: Optional[float],
        frame_width: int,
        lane_width: Optional[float]
    ) -> int:
        """
        Determine alert level based on lane departure
        
        Args:
            center_offset: Offset from lane center (pixels)
            frame_width: Width of frame
            lane_width: Width of detected lane
            
        Returns:
            Alert level (ALERT_NONE, ALERT_WARNING, ALERT_DANGER)
        """
        if center_offset is None or lane_width is None:
            self.departure_counter = 0
            return ALERT_NONE
        
        # Check if lane width is reasonable
        if lane_width < LANE_WIDTH_MIN or lane_width > LANE_WIDTH_MAX:
            self.departure_counter = 0
            return ALERT_NONE
        
        # Calculate departure ratio
        departure_ratio = abs(center_offset) / frame_width
        
        # Check if departing
        if departure_ratio > DEPARTURE_THRESHOLD:
            self.departure_counter += 1
        else:
            self.departure_counter = max(0, self.departure_counter - 1)
        
        # Trigger alert if consistent departure
        if self.departure_counter >= DEPARTURE_MEMORY:
            return ALERT_DANGER
        elif self.departure_counter >= DEPARTURE_MEMORY // 2:
            return ALERT_WARNING
        
        return ALERT_NONE
    
    def draw_lanes(
        self,
        frame: np.ndarray,
        lane_data: Dict
    ) -> np.ndarray:
        """
        Draw detected lanes on frame
        
        Args:
            frame: Input image
            lane_data: Lane detection data from detect_lanes()
            
        Returns:
            Annotated frame
        """
        output = frame.copy()
        overlay = frame.copy()
        
        left_lane = lane_data.get('left_lane')
        right_lane = lane_data.get('right_lane')
        alert_level = lane_data.get('alert_level', ALERT_NONE)
        
        # Draw lane lines
        if left_lane:
            x1, y1, x2, y2 = left_lane
            cv2.line(overlay, (x1, y1), (x2, y2), COLOR_CYAN, 8)
        
        if right_lane:
            x1, y1, x2, y2 = right_lane
            cv2.line(overlay, (x1, y1), (x2, y2), COLOR_CYAN, 8)
        
        # Fill lane area if both lanes detected
        if left_lane and right_lane:
            pts = np.array([
                [left_lane[0], left_lane[1]],
                [left_lane[2], left_lane[3]],
                [right_lane[2], right_lane[3]],
                [right_lane[0], right_lane[1]],
            ], dtype=np.int32)
            
            # Color based on alert level
            if alert_level == ALERT_DANGER:
                fill_color = COLOR_RED
            elif alert_level == ALERT_WARNING:
                fill_color = COLOR_YELLOW
            else:
                fill_color = COLOR_GREEN
            
            cv2.fillPoly(overlay, [pts], fill_color)
        
        # Blend overlay with original frame
        output = cv2.addWeighted(output, 0.7, overlay, 0.3, 0)
        
        # Draw departure warning
        if alert_level == ALERT_DANGER:
            direction = lane_data.get('departure_direction', 'unknown')
            warning_text = f"⚠ LANE DEPARTURE ({direction.upper()}) ⚠"
            text_size, _ = cv2.getTextSize(warning_text, cv2.FONT_HERSHEY_DUPLEX, 1.0, 3)
            text_x = (frame.shape[1] - text_size[0]) // 2
            text_y = frame.shape[0] - 60
            
            cv2.putText(
                output,
                warning_text,
                (text_x, text_y),
                cv2.FONT_HERSHEY_DUPLEX,
                1.0,
                COLOR_RED,
                3
            )
        
        return output
    
    def get_stats(self) -> Dict:
        """Get LDW statistics"""
        return {
            'frames_processed': self.frame_count,
            'lanes_detected': self.lanes_detected_count,
            'detection_rate': self.lanes_detected_count / max(self.frame_count, 1),
            'left_departures': self.left_departure_count,
            'right_departures': self.right_departure_count,
        }
    
    def reset(self):
        """Reset LDW state"""
        self.left_lane_history.clear()
        self.right_lane_history.clear()
        self.departure_counter = 0
