"""
YOLOP Detector
Wrapper cho YOLOP lane detection
"""
import torch
import cv2
import numpy as np
from typing import Dict, Any, Optional
import warnings

warnings.filterwarnings('ignore')


class YOLOPDetector:
    """
    YOLOP Lane Detection
    Sử dụng pretrained YOLOP model từ GitHub
    """
    
    def __init__(self, model_path: str = None):
        """
        Args:
            model_path: Đường dẫn đến YOLOP weights
        """
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        
        # TODO: Load YOLOP model
        # Tạm thời dùng simple lane detection bằng OpenCV
        print(f"YOLOP Detector initialized on {self.device}")
        print("Warning: Using OpenCV-based lane detection as fallback")
        
        self.model = None
    
    def detect_lane(self, frame: np.ndarray) -> Optional[Dict[str, Any]]:
        """
        Detect lanes trong frame
        
        Args:
            frame: OpenCV image (BGR)
        
        Returns:
            {
                "left_lane": [[x1, y1], [x2, y2], ...],
                "right_lane": [[x1, y1], [x2, y2], ...],
                "lane_departure": bool,
                "lane_confidence": float
            }
        """
        
        # Simple OpenCV-based lane detection
        return self._opencv_lane_detection(frame)
    
    def _opencv_lane_detection(self, frame: np.ndarray) -> Optional[Dict[str, Any]]:
        """
        OpenCV-based lane detection (fallback)
        """
        try:
            h, w = frame.shape[:2]
            
            # Convert to grayscale
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            
            # Apply Gaussian blur
            blur = cv2.GaussianBlur(gray, (5, 5), 0)
            
            # Canny edge detection
            edges = cv2.Canny(blur, 50, 150)
            
            # Region of interest (lower half of frame)
            mask = np.zeros_like(edges)
            roi_vertices = np.array([[
                (0, h),
                (0, h * 0.6),
                (w, h * 0.6),
                (w, h)
            ]], dtype=np.int32)
            cv2.fillPoly(mask, roi_vertices, 255)
            masked_edges = cv2.bitwise_and(edges, mask)
            
            # Hough Line Transform
            lines = cv2.HoughLinesP(
                masked_edges,
                rho=1,
                theta=np.pi/180,
                threshold=50,
                minLineLength=100,
                maxLineGap=50
            )
            
            if lines is None:
                return None
            
            # Phân loại left/right lanes
            left_lines = []
            right_lines = []
            
            for line in lines:
                x1, y1, x2, y2 = line[0]
                
                if x2 - x1 == 0:  # Vertical line
                    continue
                
                slope = (y2 - y1) / (x2 - x1)
                
                # Left lane: negative slope
                if slope < -0.5:
                    left_lines.append([[x1, y1], [x2, y2]])
                # Right lane: positive slope
                elif slope > 0.5:
                    right_lines.append([[x1, y1], [x2, y2]])
            
            # Tính lane departure (xe lệch làn)
            lane_departure = False
            center_x = w / 2
            
            # Nếu chỉ có 1 bên lane → có thể đang lệch
            if len(left_lines) == 0 or len(right_lines) == 0:
                lane_departure = True
            
            confidence = min(len(left_lines), len(right_lines)) / 10.0
            confidence = min(confidence, 1.0)
            
            return {
                "left_lane": left_lines,
                "right_lane": right_lines,
                "lane_departure": lane_departure,
                "lane_confidence": round(confidence, 2)
            }
            
        except Exception as e:
            print(f"Error in lane detection: {e}")
            return None
    
    def detect_and_draw(self, frame: np.ndarray) -> tuple:
        """
        Detect và vẽ lanes
        
        Returns:
            (annotated_frame, lane_info)
        """
        lane_info = self.detect_lane(frame)
        
        if lane_info is None:
            return frame, None
        
        annotated = frame.copy()
        
        # Vẽ left lanes (green)
        for line in lane_info['left_lane']:
            x1, y1 = line[0]
            x2, y2 = line[1]
            cv2.line(annotated, (x1, y1), (x2, y2), (0, 255, 0), 3)
        
        # Vẽ right lanes (blue)
        for line in lane_info['right_lane']:
            x1, y1 = line[0]
            x2, y2 = line[1]
            cv2.line(annotated, (x1, y1), (x2, y2), (255, 0, 0), 3)
        
        # Cảnh báo lane departure
        if lane_info['lane_departure']:
            h, w = frame.shape[:2]
            cv2.putText(
                annotated,
                "LANE DEPARTURE!",
                (w // 2 - 150, 50),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.0,
                (0, 0, 255),
                3
            )
        
        return annotated, lane_info
