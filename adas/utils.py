"""
ADAS Utilities - Helper Functions
Các hàm tiện ích cho ADAS
"""

import cv2
import numpy as np
from typing import Tuple, Optional
import json
from pathlib import Path


def resize_frame(
    frame: np.ndarray,
    target_size: Tuple[int, int] = (1280, 720)
) -> np.ndarray:
    """
    Resize frame while maintaining aspect ratio
    
    Args:
        frame: Input frame
        target_size: Target (width, height)
        
    Returns:
        Resized frame
    """
    h, w = frame.shape[:2]
    target_w, target_h = target_size
    
    # Calculate aspect ratio
    aspect = w / h
    target_aspect = target_w / target_h
    
    if aspect > target_aspect:
        # Width is limiting factor
        new_w = target_w
        new_h = int(target_w / aspect)
    else:
        # Height is limiting factor
        new_h = target_h
        new_w = int(target_h * aspect)
    
    resized = cv2.resize(frame, (new_w, new_h))
    
    # Pad to target size if needed
    if new_w != target_w or new_h != target_h:
        canvas = np.zeros((target_h, target_w, 3), dtype=np.uint8)
        y_offset = (target_h - new_h) // 2
        x_offset = (target_w - new_w) // 2
        canvas[y_offset:y_offset+new_h, x_offset:x_offset+new_w] = resized
        return canvas
    
    return resized


def draw_text_with_background(
    frame: np.ndarray,
    text: str,
    position: Tuple[int, int],
    font_scale: float = 0.6,
    font_thickness: int = 2,
    text_color: Tuple[int, int, int] = (255, 255, 255),
    bg_color: Tuple[int, int, int] = (0, 0, 0),
    padding: int = 5
) -> np.ndarray:
    """
    Draw text with background rectangle
    
    Args:
        frame: Input frame
        text: Text to draw
        position: (x, y) position
        font_scale: Font scale
        font_thickness: Font thickness
        text_color: Text color (BGR)
        bg_color: Background color (BGR)
        padding: Padding around text
        
    Returns:
        Frame with text drawn
    """
    x, y = position
    
    # Get text size
    (text_w, text_h), baseline = cv2.getTextSize(
        text,
        cv2.FONT_HERSHEY_SIMPLEX,
        font_scale,
        font_thickness
    )
    
    # Draw background rectangle
    cv2.rectangle(
        frame,
        (x - padding, y - text_h - padding),
        (x + text_w + padding, y + baseline + padding),
        bg_color,
        -1
    )
    
    # Draw text
    cv2.putText(
        frame,
        text,
        (x, y),
        cv2.FONT_HERSHEY_SIMPLEX,
        font_scale,
        text_color,
        font_thickness
    )
    
    return frame


def calculate_iou(
    box1: Tuple[int, int, int, int],
    box2: Tuple[int, int, int, int]
) -> float:
    """
    Calculate Intersection over Union (IoU) between two boxes
    
    Args:
        box1: (x1, y1, x2, y2)
        box2: (x1, y1, x2, y2)
        
    Returns:
        IoU value [0, 1]
    """
    x1_1, y1_1, x2_1, y2_1 = box1
    x1_2, y1_2, x2_2, y2_2 = box2
    
    # Calculate intersection
    x1_i = max(x1_1, x1_2)
    y1_i = max(y1_1, y1_2)
    x2_i = min(x2_1, x2_2)
    y2_i = min(y2_1, y2_2)
    
    if x2_i < x1_i or y2_i < y1_i:
        return 0.0
    
    intersection = (x2_i - x1_i) * (y2_i - y1_i)
    
    # Calculate union
    area1 = (x2_1 - x1_1) * (y2_1 - y1_1)
    area2 = (x2_2 - x1_2) * (y2_2 - y1_2)
    union = area1 + area2 - intersection
    
    if union == 0:
        return 0.0
    
    return intersection / union


def load_camera_calibration(
    calibration_file: Path
) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    """
    Load camera calibration from JSON file
    
    Args:
        calibration_file: Path to calibration JSON
        
    Returns:
        Tuple of (camera_matrix, dist_coeffs) or None
    """
    if not calibration_file.exists():
        return None
    
    try:
        with open(calibration_file, 'r') as f:
            data = json.load(f)
        
        camera_matrix = np.array(data['camera_matrix'], dtype=np.float32)
        dist_coeffs = np.array(data['distortion_coeffs'], dtype=np.float32)
        
        return camera_matrix, dist_coeffs
    
    except Exception as e:
        print(f"Failed to load calibration: {e}")
        return None


def save_camera_calibration(
    calibration_file: Path,
    camera_matrix: np.ndarray,
    dist_coeffs: np.ndarray,
    focal_length: Optional[float] = None
):
    """
    Save camera calibration to JSON file
    
    Args:
        calibration_file: Path to save calibration
        camera_matrix: Camera matrix
        dist_coeffs: Distortion coefficients
        focal_length: Focal length in pixels
    """
    data = {
        'camera_matrix': camera_matrix.tolist(),
        'distortion_coeffs': dist_coeffs.tolist(),
    }
    
    if focal_length:
        data['focal_length'] = focal_length
    
    with open(calibration_file, 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"Calibration saved to {calibration_file}")


def create_heatmap(
    frame: np.ndarray,
    detections: list,
    colormap: int = cv2.COLORMAP_JET
) -> np.ndarray:
    """
    Create detection heatmap overlay
    
    Args:
        frame: Input frame
        detections: List of detections with 'bbox' key
        colormap: OpenCV colormap
        
    Returns:
        Heatmap overlay
    """
    h, w = frame.shape[:2]
    heatmap = np.zeros((h, w), dtype=np.float32)
    
    for det in detections:
        x1, y1, x2, y2 = det['bbox']
        conf = det.get('confidence', 1.0)
        
        # Add to heatmap
        heatmap[y1:y2, x1:x2] += conf
    
    # Normalize
    if heatmap.max() > 0:
        heatmap = (heatmap / heatmap.max() * 255).astype(np.uint8)
    else:
        heatmap = heatmap.astype(np.uint8)
    
    # Apply colormap
    heatmap_color = cv2.applyColorMap(heatmap, colormap)
    
    # Blend with original
    output = cv2.addWeighted(frame, 0.7, heatmap_color, 0.3, 0)
    
    return output


def calculate_fps(
    frame_times: list,
    window_size: int = 30
) -> float:
    """
    Calculate FPS from frame timestamps
    
    Args:
        frame_times: List of frame timestamps
        window_size: Moving average window size
        
    Returns:
        Average FPS
    """
    if len(frame_times) < 2:
        return 0.0
    
    recent_times = frame_times[-window_size:]
    
    if len(recent_times) < 2:
        return 0.0
    
    time_diff = recent_times[-1] - recent_times[0]
    
    if time_diff == 0:
        return 0.0
    
    fps = (len(recent_times) - 1) / time_diff
    return fps


def check_gpu_available() -> bool:
    """
    Check if GPU is available for inference
    
    Returns:
        True if GPU available
    """
    try:
        import torch
        return torch.cuda.is_available() or torch.backends.mps.is_available()
    except:
        return False


def get_optimal_device() -> str:
    """
    Get optimal device for inference
    
    Returns:
        Device string ('cuda', 'mps', or 'cpu')
    """
    try:
        import torch
        
        if torch.cuda.is_available():
            return 'cuda'
        elif torch.backends.mps.is_available():
            return 'mps'
        else:
            return 'cpu'
    except:
        return 'cpu'
