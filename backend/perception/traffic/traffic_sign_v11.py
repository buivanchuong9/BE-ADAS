"""
NHẬN DIỆN BIỂN BÁO GIAO THÔNG - GTSRB (Châu Âu)
================================================
Phát hiện và phân loại biển báo giao thông.
Fallback về COCO nếu không có model GTSRB.

Tác giả: Lead AI Architect
Ngày: 2026-02-06
"""

import cv2
import numpy as np
import torch
from pathlib import Path
from typing import List, Dict, Optional
from PIL import Image, ImageDraw, ImageFont
import logging

logger = logging.getLogger(__name__)


class TrafficSignV11:
    """
    Bộ nhận diện biển báo giao thông.
    
    Tính năng:
    - Sử dụng GTSRB model nếu có
    - Fallback về COCO pretrained
    - Hiển thị tiếng Việt
    """
    
    # GTSRB Classes (43 classes - Đức)
    GTSRB_CLASSES = {
        0: "Tốc độ 20 km/h",
        1: "Tốc độ 30 km/h",
        2: "Tốc độ 50 km/h",
        3: "Tốc độ 60 km/h",
        4: "Tốc độ 70 km/h",
        5: "Tốc độ 80 km/h",
        6: "Hết giới hạn 80 km/h",
        7: "Tốc độ 100 km/h",
        8: "Tốc độ 120 km/h",
        9: "Cấm vượt",
        10: "Cấm vượt (xe tải)",
        11: "Giao lộ",
        12: "Đường ưu tiên",
        13: "Nhường đường",
        14: "Dừng lại",
        15: "Cấm xe",
        16: "Cấm xe tải",
        17: "Cấm vào",
        18: "Nguy hiểm",
        # ... có thể thêm 43 classes đầy đủ
    }
    
    # COCO fallback
    COCO_SIGN_CLASSES = {
        11: 'Biển báo Dừng',
        9: 'Đèn giao thông'
    }
    
    def __init__(
        self,
        model_path: str = "backend/models/traffic_sign_gtsrb.pt",
        device: str = "cuda",
        conf_threshold: float = 0.5
    ):
        """
        Khởi tạo Traffic Sign Detector.
        
        Args:
            model_path: Đường dẫn model GTSRB (hoặc COCO fallback)
            device: "cuda" hoặc "cpu"
            conf_threshold: Ngưỡng confidence
        """
        self.device = device
        self.conf_threshold = conf_threshold
        self.use_gtsrb = False
        
        # Kiểm tra CUDA
        if device == "cuda" and not torch.cuda.is_available():
            logger.warning("⚠️ CUDA không khả dụng, chuyển sang CPU")
            self.device = "cpu"
        
        # Tối ưu GPU
        if self.device == "cuda":
            torch.set_float32_matmul_precision('high')
            torch.backends.cudnn.benchmark = True
            logger.info("🚀 GPU Optimization: Enabled")
        
        # Load model
        try:
            from ultralytics import YOLO
            
            # Kiểm tra GTSRB model
            if Path(model_path).exists():
                logger.info(f"✅ Tìm thấy GTSRB model: {model_path}")
                self.model = YOLO(model_path)
                self.use_gtsrb = True
                self.class_names = self.GTSRB_CLASSES
                logger.info("📋 Sử dụng GTSRB (43 classes)")
            else:
                logger.warning(f"⚠️ Không tìm thấy GTSRB model: {model_path}")
                logger.warning("📋 Fallback về COCO pretrained (giới hạn)")
                
                # Fallback: Load COCO model
                self.model = YOLO("yolo11x.pt")  # Auto download nếu chưa có
                self.use_gtsrb = False
                self.class_names = self.COCO_SIGN_CLASSES
            
            # Optimization
            self.model.overrides['conf'] = conf_threshold
            self.model.overrides['iou'] = 0.45
            self.model.overrides['verbose'] = False
            
            logger.info(f"✅ Model loaded trên {self.device.upper()}")
            
        except ImportError:
            raise ImportError("❌ Chưa cài ultralytics")
        
        # Load font
        try:
            font_path = "backend/assets/fonts/Roboto-Bold.ttf"
            self.font = ImageFont.truetype(font_path, 20)
            logger.info(f"✅ Font tiếng Việt: {font_path}")
        except Exception as e:
            logger.warning(f"⚠️ Không load được font: {e}")
            self.font = None
    
    @torch.no_grad()
    def detect(self, frame: np.ndarray) -> List[Dict]:
        """
        Phát hiện biển báo trong frame.
        
        Args:
            frame: Frame RGB
            
        Returns:
            Danh sách biển báo phát hiện được
        """
        try:
            results = self.model(
                frame,
                conf=self.conf_threshold,
                device=self.device,
                verbose=False
            )
            
            signs = []
            
            for result in results:
                boxes = result.boxes
                
                if boxes is None or len(boxes) == 0:
                    continue
                
                for box in boxes:
                    cls_id = int(box.cls[0].item())
                    
                    # Filter dựa vào model type
                    if self.use_gtsrb:
                        # GTSRB: Lấy tất cả
                        if cls_id not in self.class_names:
                            continue
                        sign_name = self.class_names[cls_id]
                    else:
                        # COCO: Chỉ lấy stop sign & traffic light
                        if cls_id not in self.COCO_SIGN_CLASSES:
                            continue
                        sign_name = self.COCO_SIGN_CLASSES[cls_id]
                    
                    conf = float(box.conf[0].item())
                    xyxy = box.xyxy[0].cpu().numpy()
                    
                    x1, y1, x2, y2 = map(int, xyxy)
                    
                    signs.append({
                        'class_id': cls_id,
                        'sign_name': sign_name,
                        'confidence': conf,
                        'bbox': [x1, y1, x2, y2]
                    })
            
            return signs
            
        except Exception as e:
            logger.error(f"❌ Lỗi detect: {e}")
            return []
    
    def get_speed_limit(self, sign_name: str) -> Optional[int]:
        """
        Trích xuất giới hạn tốc độ từ tên biển báo.
        
        Returns:
            Speed limit (km/h) hoặc None
        """
        if "Tốc độ" in sign_name:
            try:
                # Extract số từ string
                import re
                match = re.search(r'\d+', sign_name)
                if match:
                    return int(match.group())
            except:
                pass
        return None
    
    def draw_signs(
        self,
        frame: np.ndarray,
        signs: List[Dict]
    ) -> np.ndarray:
        """
        Vẽ biển báo lên frame (Tiếng Việt).
        
        Args:
            frame: Frame RGB
            signs: Danh sách biển báo
            
        Returns:
            Frame đã vẽ
        """
        if not signs:
            return frame
        
        # Convert sang PIL
        frame_pil = Image.fromarray(frame)
        draw = ImageDraw.Draw(frame_pil)
        
        for sign in signs:
            x1, y1, x2, y2 = sign['bbox']
            sign_name = sign['sign_name']
            conf = sign['confidence']
            
            # Màu sắc
            # Đỏ cho biển cấm/dừng
            if any(word in sign_name for word in ["Cấm", "Dừng", "Nguy hiểm"]):
                color = (255, 0, 0)  # Đỏ
            # Xanh cho biển tốc độ
            elif "Tốc độ" in sign_name:
                color = (0, 0, 255)  # Xanh dương
            else:
                color = (255, 165, 0)  # Cam
            
            # Vẽ bbox
            draw.rectangle([x1, y1, x2, y2], outline=color, width=3)
            
            # Label
            label = f"{sign_name}: {conf:.0%}"
            
            # Vẽ text
            if self.font:
                bbox_text = draw.textbbox((x1, y1 - 30), label, font=self.font)
                draw.rectangle(bbox_text, fill=color)
                draw.text((x1 + 5, y1 - 28), label, fill=(255, 255, 255), font=self.font)
            else:
                # Fallback
                frame_cv = np.array(frame_pil)
                cv2.rectangle(frame_cv, (x1, y1 - 30), (x1 + 300, y1), color, -1)
                cv2.putText(frame_cv, label, (x1 + 5, y1 - 10),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
                return frame_cv
        
        return np.array(frame_pil)
    
    def process_frame(self, frame: np.ndarray) -> Dict:
        """
        Pipeline xử lý hoàn chỉnh.
        
        Returns:
            Dictionary chứa:
                - annotated_frame: Frame đã vẽ
                - signs: Danh sách biển báo
                - speed_limits: Danh sách giới hạn tốc độ
        """
        # Detect
        signs = self.detect(frame)
        
        # Vẽ
        annotated_frame = self.draw_signs(frame, signs)
        
        # Trích xuất speed limits
        speed_limits = []
        for sign in signs:
            limit = self.get_speed_limit(sign['sign_name'])
            if limit:
                speed_limits.append(limit)
        
        return {
            'annotated_frame': annotated_frame,
            'signs': signs,
            'speed_limits': speed_limits,
            'total_signs': len(signs)
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    try:
        detector = TrafficSignV11(device="cuda")
        print("✅ Traffic Sign Detector khởi tạo thành công")
    except Exception as e:
        print(f"❌ Lỗi khởi tạo: {e}")
