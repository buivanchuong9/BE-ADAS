"""
PHÁT HIỆN LÀN ĐƯỜNG - YOLOv11x Segmentation (Tesla Style)
==========================================================
Segmentation vùng có thể lái xe (drivable area) với hiệu ứng Tesla.
Tối ưu hóa GPU - Zero CPU bottleneck.

Tác giả: Lead AI Architect
Ngày: 2026-02-06
"""

import cv2
import numpy as np
import torch
from pathlib import Path
from typing import Optional, Dict
from PIL import Image, ImageDraw, ImageFont
import logging

logger = logging.getLogger(__name__)


class LaneDetectorV11:
    """
    Bộ phát hiện làn đường Tesla-style sử dụng Segmentation.
    
    Tính năng:
    - Segmentation mask trên GPU
    - Overlay màu Neon mượt mà
    - Không dùng CV cổ điển (Canny/Hough)
    - Hiển thị tiếng Việt
    """
    
    # Màu sắc Tesla-style (BGR)
    DRIVABLE_COLOR = (255, 255, 0)  # Cyan Neon
    ALTERNATIVE_COLOR = (0, 255, 100)  # Green Neon
    
    def __init__(
        self,
        model_path: str = "backend/models/yolo11x-seg.pt",
        device: str = "cuda",
        conf_threshold: float = 0.4,
        use_cyan: bool = True
    ):
        """
        Khởi tạo Lane Detector.
        
        Args:
            model_path: Đường dẫn tới yolo11x-seg.pt
            device: "cuda" hoặc "cpu"
            conf_threshold: Ngưỡng confidence
            use_cyan: True = Cyan, False = Green
        """
        self.device = device
        self.conf_threshold = conf_threshold
        self.overlay_color = self.DRIVABLE_COLOR if use_cyan else self.ALTERNATIVE_COLOR
        self.alpha = 0.4  # Độ trong suốt
        
        # Kiểm tra CUDA
        if device == "cuda" and not torch.cuda.is_available():
            logger.warning("⚠️ CUDA không khả dụng, chuyển sang CPU")
            self.device = "cpu"
        
        # Tối ưu GPU
        if self.device == "cuda":
            torch.set_float32_matmul_precision('high')
            torch.backends.cudnn.benchmark = True
            logger.info("🚀 GPU Optimization: Enabled")
        
        # Kiểm tra model
        model_file = Path(model_path)
        if not model_file.exists():
            raise FileNotFoundError(
                f"❌ Model không tồn tại: {model_path}\n"
                f"Vui lòng tải từ: https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11x-seg.pt"
            )
        
        # Load model
        try:
            from ultralytics import YOLO
            self.model = YOLO(str(model_file))
            
            # Optimization flags
            self.model.overrides['conf'] = conf_threshold
            self.model.overrides['iou'] = 0.45
            self.model.overrides['verbose'] = False
            
            logger.info(f"✅ YOLOv11x-Seg đã load trên {self.device.upper()}")
            
        except ImportError:
            raise ImportError("❌ Chưa cài ultralytics. Chạy: pip install ultralytics")
        
        # Load font tiếng Việt
        try:
            font_path = "backend/assets/fonts/Roboto-Bold.ttf"
            self.font = ImageFont.truetype(font_path, 24)
            logger.info(f"✅ Font tiếng Việt: {font_path}")
        except Exception as e:
            logger.warning(f"⚠️ Không load được font: {e}")
            self.font = None
    
    @torch.no_grad()
    def detect_drivable_area(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """
        Phát hiện vùng có thể lái (drivable area).
        
        WHY: Sử dụng segmentation mask thay vì Hough Lines vì:
        - Chính xác hơn trên đường cong
        - Không cần tune parameters thủ công
        - GPU-accelerated (fast)
        
        Args:
            frame: Frame RGB (H x W x 3)
            
        Returns:
            Binary mask (H x W) - numpy array hoặc None
        """
        try:
            # Inference
            results = self.model(
                frame,
                conf=self.conf_threshold,
                device=self.device,
                verbose=False
            )
            
            for result in results:
                # Kiểm tra có masks không
                if result.masks is None:
                    logger.debug("Không phát hiện mask")
                    return None
                
                # Lấy masks data (GPU Tensor)
                masks_data = result.masks.data  # Shape: [N, H, W]
                
                if masks_data.shape[0] == 0:
                    return None
                
                # Merge tất cả masks thành 1 (vùng drivable tổng hợp)
                # WHY: Vì road có thể gồm nhiều segment
                merged_mask = torch.any(masks_data > 0.5, dim=0)  # [H, W]
                
                # Convert về numpy (chỉ khi cần)
                mask_np = merged_mask.cpu().numpy().astype(np.uint8) * 255
                
                return mask_np
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Lỗi detect drivable area: {e}")
            return None
    
    def create_overlay(
        self,
        frame: np.ndarray,
        mask: Optional[np.ndarray]
    ) -> np.ndarray:
        """
        Tạo overlay Tesla-style trên frame.
        
        WHY: Sử dụng cv2.addWeighted thay vì vòng lặp pixel vì:
        - Vectorized operation (nhanh gấp 100x)
        - Sử dụng SIMD instructions
        - Smooth blending
        
        Args:
            frame: Frame gốc RGB
            mask: Binary mask (255 = drivable, 0 = không)
            
        Returns:
            Frame với overlay màu
        """
        if mask is None:
            return frame
        
        try:
            # Resize mask về kích thước frame (nếu khác nhau)
            h_frame, w_frame = frame.shape[:2]
            h_mask, w_mask = mask.shape[:2]
            
            if h_frame != h_mask or w_frame != w_mask:
                mask = cv2.resize(mask, (w_frame, h_frame), interpolation=cv2.INTER_NEAREST)
            
            # Tạo colored mask
            colored_mask = np.zeros((h_frame, w_frame, 3), dtype=np.uint8)
            
            # Áp dụng màu cho vùng drivable
            colored_mask[mask > 0] = self.overlay_color
            
            # Blend với frame gốc (alpha blending)
            # WHY: cv2.addWeighted dùng hardware acceleration
            overlay = cv2.addWeighted(
                frame,
                1.0,
                colored_mask,
                self.alpha,
                0
            )
            
            return overlay
            
        except Exception as e:
            logger.error(f"❌ Lỗi tạo overlay: {e}")
            return frame
    
    def draw_info(
        self,
        frame: np.ndarray,
        has_lane: bool
    ) -> np.ndarray:
        """
        Vẽ thông tin trạng thái lên frame (Tiếng Việt).
        
        Args:
            frame: Frame đã overlay
            has_lane: True nếu phát hiện được lane
            
        Returns:
            Frame với info text
        """
        # Convert sang PIL
        frame_pil = Image.fromarray(frame)
        draw = ImageDraw.Draw(frame_pil)
        
        # Text status
        if has_lane:
            status = "✓ PHÁT HIỆN LÀN ĐƯỜNG"
            color = (0, 255, 0)  # Xanh lá
        else:
            status = "✗ KHÔNG PHÁT HIỆN LÀN ĐƯỜNG"
            color = (255, 0, 0)  # Đỏ
        
        # Vẽ text
        if self.font:
            # Vẽ background
            bbox = draw.textbbox((20, 20), status, font=self.font)
            draw.rectangle(
                [(bbox[0] - 10, bbox[1] - 5), (bbox[2] + 10, bbox[3] + 5)],
                fill=(0, 0, 0, 180)
            )
            draw.text((20, 20), status, fill=color, font=self.font)
        else:
            # Fallback
            frame_cv = np.array(frame_pil)
            cv2.putText(
                frame_cv,
                status,
                (20, 50),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.0,
                color,
                2
            )
            return frame_cv
        
        return np.array(frame_pil)
    
    def process_frame(self, frame: np.ndarray) -> Dict:
        """
        Pipeline xử lý hoàn chỉnh.
        
        Args:
            frame: Frame RGB
            
        Returns:
            Dictionary chứa:
                - annotated_frame: Frame với overlay Tesla-style
                - mask: Binary mask của vùng drivable
                - has_lane: True nếu phát hiện được
        """
        # Detect drivable area
        mask = self.detect_drivable_area(frame)
        
        # Tạo overlay
        if mask is not None:
            overlay_frame = self.create_overlay(frame, mask)
            has_lane = True
        else:
            overlay_frame = frame.copy()
            has_lane = False
        
        # Vẽ thông tin
        annotated_frame = self.draw_info(overlay_frame, has_lane)
        
        return {
            'annotated_frame': annotated_frame,
            'mask': mask,
            'has_lane': has_lane
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    try:
        detector = LaneDetectorV11(device="cuda")
        print("✅ Lane Detector khởi tạo thành công")
    except Exception as e:
        print(f"❌ Lỗi khởi tạo: {e}")
