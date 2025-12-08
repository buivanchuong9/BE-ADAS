"""
Depth Estimator
Wrapper cho MiDaS depth estimation
"""
import torch
import cv2
import numpy as np
from typing import Optional
import warnings

warnings.filterwarnings('ignore')


class DepthEstimator:
    """
    MiDaS Depth Estimation
    Ước tính khoảng cách từ camera
    """
    
    def __init__(self, model_type: str = "DPT_Small"):
        """
        Args:
            model_type: "DPT_Large", "DPT_Hybrid", "MiDaS_small"
        """
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        
        try:
            # Load MiDaS model từ torch hub
            self.model = torch.hub.load(
                "intel-isl/MiDaS",
                model_type,
                pretrained=True
            )
            self.model.to(self.device)
            self.model.eval()
            
            # Load transforms
            midas_transforms = torch.hub.load("intel-isl/MiDaS", "transforms")
            
            if model_type == "DPT_Large" or model_type == "DPT_Hybrid":
                self.transform = midas_transforms.dpt_transform
            else:
                self.transform = midas_transforms.small_transform
            
            print(f"MiDaS Depth Estimator initialized on {self.device}")
            print(f"Model type: {model_type}")
            
        except Exception as e:
            print(f"Error loading MiDaS: {e}")
            print("Using simple depth estimation as fallback")
            self.model = None
            self.transform = None
    
    def estimate(self, frame: np.ndarray) -> np.ndarray:
        """
        Ước tính depth map
        
        Args:
            frame: OpenCV image (BGR)
        
        Returns:
            depth_map: numpy array (H, W) với giá trị depth (meters)
        """
        if self.model is None:
            return self._simple_depth_estimation(frame)
        
        try:
            # Convert BGR to RGB
            img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Transform
            input_batch = self.transform(img_rgb).to(self.device)
            
            # Predict
            with torch.no_grad():
                prediction = self.model(input_batch)
                
                # Resize to original size
                prediction = torch.nn.functional.interpolate(
                    prediction.unsqueeze(1),
                    size=frame.shape[:2],
                    mode="bicubic",
                    align_corners=False,
                ).squeeze()
            
            depth_map = prediction.cpu().numpy()
            
            # Normalize và convert to meters (approximate)
            # MiDaS output là inverse depth, cần convert
            depth_map = self._inverse_depth_to_meters(depth_map)
            
            return depth_map
            
        except Exception as e:
            print(f"Error in depth estimation: {e}")
            return self._simple_depth_estimation(frame)
    
    def _inverse_depth_to_meters(self, depth_map: np.ndarray) -> np.ndarray:
        """
        Convert MiDaS inverse depth to meters
        
        Công thức gần đúng:
        - depth_map từ MiDaS là inverse depth (1/d)
        - Cần calibration với camera thực tế
        """
        # Normalize về [0, 1]
        depth_normalized = (depth_map - depth_map.min()) / (depth_map.max() - depth_map.min() + 1e-8)
        
        # Convert to meters (approximate)
        # Giả sử: 0 = 100m, 1 = 1m
        MAX_DISTANCE = 100.0  # meters
        MIN_DISTANCE = 1.0    # meters
        
        # Inverse: depth cao (gần) = giá trị cao
        depth_meters = MIN_DISTANCE + (1 - depth_normalized) * (MAX_DISTANCE - MIN_DISTANCE)
        
        return depth_meters
    
    def _simple_depth_estimation(self, frame: np.ndarray) -> np.ndarray:
        """
        Simple depth estimation (fallback)
        Dựa vào vị trí trong frame (y coordinate)
        """
        h, w = frame.shape[:2]
        
        # Simple assumption: càng xuống dưới frame = càng gần
        y_coords = np.arange(h).reshape(-1, 1)
        y_normalized = y_coords / h
        
        # Depth map: 1-100 meters
        depth_map = 100.0 - (y_normalized * 99.0)
        depth_map = np.repeat(depth_map, w, axis=1)
        
        return depth_map
    
    def estimate_and_visualize(self, frame: np.ndarray) -> tuple:
        """
        Estimate depth và tạo visualization
        
        Returns:
            (depth_colored, depth_map)
        """
        depth_map = self.estimate(frame)
        
        # Normalize về [0, 255] để visualize
        depth_normalized = (depth_map - depth_map.min()) / (depth_map.max() - depth_map.min() + 1e-8)
        depth_normalized = (depth_normalized * 255).astype(np.uint8)
        
        # Apply colormap
        depth_colored = cv2.applyColorMap(depth_normalized, cv2.COLORMAP_MAGMA)
        
        return depth_colored, depth_map
