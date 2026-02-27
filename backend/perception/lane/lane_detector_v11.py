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
    - Overlay màu Neon mượt mà linh hoạt theo hình dạng đường
    - Smooth gradient edges (không bị răng cưa)
    - Hiển thị tiếng Việt
    """
    
    # Màu sắc Tesla-style (BGR)
    DRIVABLE_COLOR = (255, 255, 0)  # Cyan Neon
    ALTERNATIVE_COLOR = (0, 255, 0)  # Bright Green Neon - Xanh lá nổi bật
    
    def __init__(
        self,
        model_path: str = "backend/models/yolo11x-seg.pt",
        device: str = "cuda",
        conf_threshold: float = 0.1,
        use_cyan: bool = True
    ):
        self.device = device
        self.conf_threshold = conf_threshold
        self.overlay_color = self.DRIVABLE_COLOR if use_cyan else self.ALTERNATIVE_COLOR
        self.alpha = 0.7  # Độ trong suốt cao để lane nổi bật như Tesla
        
        # Kiểm tra CUDA
        if device == "cuda" and not torch.cuda.is_available():
            logger.warning("⚠️ CUDA không khả dụng, chuyển sang CPU")
            self.device = "cpu"
        
        if self.device == "cuda":
            torch.set_float32_matmul_precision('high')
            torch.backends.cudnn.benchmark = True
            logger.info("🚀 GPU Optimization: Enabled")
        
        model_file = Path(model_path)
        if not model_file.exists():
            raise FileNotFoundError(f"❌ Model không tồn tại: {model_path}")
        
        try:
            from ultralytics import YOLO
            self.model = YOLO(str(model_file))
            self.model.overrides['conf'] = conf_threshold
            self.model.overrides['iou'] = 0.45
            self.model.overrides['verbose'] = False
            logger.info(f"✅ YOLOv11x-Seg đã load trên {self.device.upper()}")
        except ImportError:
            raise ImportError("❌ Chưa cài ultralytics. Chạy: pip install ultralytics")
        
        try:
            font_path = "backend/assets/fonts/Roboto-Bold.ttf"
            self.font = ImageFont.truetype(font_path, 24)
        except Exception:
            self.font = None
    
    @torch.no_grad()
    def detect_drivable_area(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """
        Phát hiện vùng có thể lái (drivable area).
        Returns: Binary mask (H x W) numpy array hoặc None
        """
        try:
            results = self.model(
                frame,
                conf=self.conf_threshold,
                device=self.device,
                verbose=False
            )
            
            for result in results:
                if result.masks is None:
                    return None
                
                masks_data = result.masks.data  # Shape: [N, H, W]
                
                if masks_data.shape[0] == 0:
                    return None
                
                # Merge tất cả masks thành 1
                merged_mask = torch.any(masks_data > 0.3, dim=0)
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
        Tạo Tesla-style overlay mượt mà, linh hoạt theo hình dạng đường thật.
        
        - Smooth gradient edges (mượt mà, không răng cưa)
        - Perspective gradient (mạnh ở dưới - gần xe, nhạt ở trên - xa xe)
        - Morphological smoothing (liền mạch theo đường cong)
        - Advanced per-pixel alpha blending
        """
        if mask is None:
            return frame
        
        try:
            h_frame, w_frame = frame.shape[:2]
            h_mask, w_mask = mask.shape[:2]
            
            # Resize mask nếu cần
            if h_frame != h_mask or w_frame != w_mask:
                mask = cv2.resize(mask, (w_frame, h_frame), interpolation=cv2.INTER_LINEAR)
            
            # BƯỚC 1: Morphological smoothing - liền mạch theo hình đường
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
            mask_smooth = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
            mask_smooth = cv2.morphologyEx(mask_smooth, cv2.MORPH_OPEN, kernel)
            
            # BƯỚC 2: Gaussian blur - tạo soft/glow edges như Tesla
            mask_smooth = cv2.GaussianBlur(mask_smooth, (21, 21), 8)
            
            # BƯỚC 3: Perspective gradient - mạnh ở dưới, nhạt ở xa (transparent vanishing point)
            h, w = mask_smooth.shape[:2]
            gradient_y = np.linspace(1.0, 0.2, h).reshape(-1, 1).astype(np.float32)
            gradient_mask = np.tile(gradient_y, (1, w))
            
            # Kết hợp mask với gradient
            mask_float = mask_smooth.astype(np.float32) / 255.0
            mask_with_gradient = mask_float * gradient_mask
            
            # BƯỚC 4: Per-pixel alpha blending theo hình dạng đường
            frame_float = frame.astype(np.float32)
            blended = frame_float.copy()
            
            # Áp dụng màu với alpha động cho từng pixel
            alpha = mask_with_gradient * self.alpha
            for c in range(3):
                color_val = float(self.overlay_color[c])
                blended[:, :, c] = frame_float[:, :, c] * (1.0 - alpha) + color_val * alpha
            
            return np.clip(blended, 0, 255).astype(np.uint8)
            
        except Exception as e:
            logger.error(f"❌ Lỗi tạo overlay: {e}")
            return frame
    
    def draw_info(self, frame: np.ndarray, has_lane: bool) -> np.ndarray:
        """Vẽ thông tin trạng thái lên frame (Tiếng Việt)."""
        frame_pil = Image.fromarray(frame)
        draw = ImageDraw.Draw(frame_pil)
        
        if has_lane:
            status = "✓ PHÁT HIỆN LÀN ĐƯỜNG"
            color = (0, 255, 0)
        else:
            status = "✗ KHÔNG PHÁT HIỆN LÀN ĐƯỜNG"
            color = (255, 0, 0)
        
        if self.font:
            bbox = draw.textbbox((20, 20), status, font=self.font)
            draw.rectangle(
                [(bbox[0] - 10, bbox[1] - 5), (bbox[2] + 10, bbox[3] + 5)],
                fill=(0, 0, 0, 180)
            )
            draw.text((20, 20), status, fill=color, font=self.font)
        else:
            frame_cv = np.array(frame_pil)
            cv2.putText(frame_cv, status, (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.0, color, 2)
            return frame_cv
        
        return np.array(frame_pil)
    
    def process_frame(self, frame: np.ndarray) -> Dict:
        """
        Pipeline xử lý hoàn chỉnh.
        
        Returns:
            Dict: annotated_frame, mask, has_lane
        """
        mask = self.detect_drivable_area(frame)
        
        if mask is not None:
            overlay_frame = self.create_overlay(frame, mask)
            has_lane = True
        else:
            overlay_frame = frame.copy()
            has_lane = False
        
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
