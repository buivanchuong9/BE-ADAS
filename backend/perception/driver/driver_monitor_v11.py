"""
GIÁM SÁT TÀI XẾ - YOLOv11x + Pose Analysis
===========================================
Phát hiện hành vi nguy hiểm của tài xế:
- Dùng điện thoại
- Uống nước/ăn khi lái
- Buồn ngủ/mệt mỏi (pose analysis)

Tác giả: Lead AI Architect
Ngày: 2026-02-06
"""

import cv2
import numpy as np
import torch
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont
import logging
from collections import deque
import math

logger = logging.getLogger(__name__)


class DriverMonitorV11:
    """
    Hệ thống giám sát tài xế sử dụng Object Detection + Pose Estimation.
    
    Tính năng:
    - Phát hiện điện thoại, ly/chai nước
    - Phân tích tư thế (pose) để phát hiện buồn ngủ
    - Cảnh báo tiếng Việt real-time
    """
    
    # Class IDs COCO cần thiết
    OBJECT_CLASSES = {
        67: 'điện thoại',
        41: 'cốc',
        39: 'chai'
    }
    
    # Ngưỡng khoảng cách (pixels)
    PHONE_DISTANCE_THRESHOLD = 200
    DRINK_DISTANCE_THRESHOLD = 180
    
    # Màu cảnh báo
    WARNING_COLOR = (0, 0, 255)  # Đỏ (BGR)
    SAFE_COLOR = (0, 255, 0)     # Xanh lá
    
    def __init__(
        self,
        object_model_path: str = "backend/models/yolo11x.pt",
        pose_model_path: str = "backend/models/yolo11x-pose.pt",
        device: str = "cuda"
    ):
        """
        Khởi tạo Driver Monitor.
        
        Args:
            object_model_path: Model phát hiện vật thể
            pose_model_path: Model phát hiện pose
            device: "cuda" hoặc "cpu"
        """
        self.device = device
        
        # Kiểm tra CUDA
        if device == "cuda" and not torch.cuda.is_available():
            logger.warning("⚠️ CUDA không khả dụng, chuyển sang CPU")
            self.device = "cpu"
        
        # Tối ưu GPU
        if self.device == "cuda":
            torch.set_float32_matmul_precision('high')
            torch.backends.cudnn.benchmark = True
            logger.info("🚀 GPU Optimization: Enabled")
        
        # Load models
        try:
            from ultralytics import YOLO
            
            # Object detection model
            if not Path(object_model_path).exists():
                raise FileNotFoundError(f"❌ Không tìm thấy: {object_model_path}")
            
            self.object_model = YOLO(object_model_path)
            self.object_model.overrides['conf'] = 0.4
            self.object_model.overrides['verbose'] = False
            
            # Pose estimation model
            if not Path(pose_model_path).exists():
                raise FileNotFoundError(f"❌ Không tìm thấy: {pose_model_path}")
            
            self.pose_model = YOLO(pose_model_path)
            self.pose_model.overrides['conf'] = 0.5
            self.pose_model.overrides['verbose'] = False
            
            logger.info(f"✅ Models loaded trên {self.device.upper()}")
            
        except ImportError:
            raise ImportError("❌ Chưa cài ultralytics")
        
        # Load font
        try:
            font_path = "backend/assets/fonts/Roboto-Bold.ttf"
            self.font_large = ImageFont.truetype(font_path, 32)
            self.font_medium = ImageFont.truetype(font_path, 24)
            logger.info(f"✅ Font tiếng Việt: {font_path}")
        except Exception as e:
            logger.warning(f"⚠️ Không load được font: {e}")
            self.font_large = None
            self.font_medium = None
        
        # Buffer cho temporal smoothing
        self.head_tilt_buffer = deque(maxlen=30)  # 1 giây @ 30fps
        self.phone_buffer = deque(maxlen=15)
        self.drink_buffer = deque(maxlen=15)
    
    def calculate_distance(self, point1: Tuple[float, float], point2: Tuple[float, float]) -> float:
        """
        Tính khoảng cách Euclidean giữa 2 điểm.
        
        WHY: Sử dụng để kiểm tra vật thể có gần mặt/tai không.
        """
        return math.sqrt((point1[0] - point2[0])**2 + (point1[1] - point2[1])**2)
    
    @torch.no_grad()
    def detect_objects(self, frame: np.ndarray) -> List[Dict]:
        """
        Phát hiện điện thoại, cốc, chai.
        
        Args:
            frame: Frame RGB
            
        Returns:
            Danh sách objects phát hiện được
        """
        try:
            results = self.object_model(
                frame,
                device=self.device,
                verbose=False
            )
            
            objects = []
            
            for result in results:
                boxes = result.boxes
                
                if boxes is None or len(boxes) == 0:
                    continue
                
                for box in boxes:
                    cls_id = int(box.cls[0].item())
                    
                    # Filter: Chỉ lấy phone, cup, bottle
                    if cls_id not in self.OBJECT_CLASSES:
                        continue
                    
                    conf = float(box.conf[0].item())
                    xyxy = box.xyxy[0].cpu().numpy()
                    
                    x1, y1, x2, y2 = map(int, xyxy)
                    cx = (x1 + x2) // 2
                    cy = (y1 + y2) // 2
                    
                    objects.append({
                        'class_id': cls_id,
                        'class_name': self.OBJECT_CLASSES[cls_id],
                        'confidence': conf,
                        'bbox': [x1, y1, x2, y2],
                        'center': (cx, cy)
                    })
            
            return objects
            
        except Exception as e:
            logger.error(f"❌ Lỗi detect objects: {e}")
            return []
    
    @torch.no_grad()
    def detect_pose(self, frame: np.ndarray) -> Optional[Dict]:
        """
        Phát hiện pose của tài xế.
        
        Returns:
            Dictionary chứa keypoints hoặc None
        """
        try:
            results = self.pose_model(
                frame,
                device=self.device,
                verbose=False
            )
            
            for result in results:
                if result.keypoints is None:
                    continue
                
                keypoints_data = result.keypoints.data  # [N, 17, 3]
                
                if keypoints_data.shape[0] == 0:
                    continue
                
                # Lấy người đầu tiên (tài xế)
                kpts = keypoints_data[0].cpu().numpy()  # [17, 3]
                
                # Extract keypoints quan trọng
                # WHY: COCO Pose format: [x, y, confidence]
                nose = kpts[0][:2]           # Mũi
                left_eye = kpts[1][:2]       # Mắt trái
                right_eye = kpts[2][:2]      # Mắt phải
                left_ear = kpts[3][:2]       # Tai trái
                right_ear = kpts[4][:2]      # Tai phải
                left_shoulder = kpts[5][:2]  # Vai trái
                right_shoulder = kpts[6][:2] # Vai phải
                
                return {
                    'nose': nose,
                    'left_eye': left_eye,
                    'right_eye': right_eye,
                    'left_ear': left_ear,
                    'right_ear': right_ear,
                    'left_shoulder': left_shoulder,
                    'right_shoulder': right_shoulder,
                    'keypoints': kpts
                }
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Lỗi detect pose: {e}")
            return None
    
    def check_phone_use(
        self,
        objects: List[Dict],
        pose: Optional[Dict]
    ) -> Tuple[bool, Optional[str]]:
        """
        Kiểm tra tài xế có đang dùng điện thoại không.
        
        Logic:
        - Phát hiện điện thoại
        - Tính khoảng cách tới tai/mặt
        - Nếu < ngưỡng -> CẢNH BÁO
        
        Returns:
            (is_using_phone, warning_message)
        """
        if pose is None:
            return False, None
        
        phones = [obj for obj in objects if obj['class_name'] == 'điện thoại']
        
        if not phones:
            self.phone_buffer.append(False)
            return False, None
        
        # Lấy điểm tham chiếu (mũi hoặc tai)
        nose = pose['nose']
        left_ear = pose['left_ear']
        right_ear = pose['right_ear']
        
        # Kiểm tra từng điện thoại
        for phone in phones:
            phone_center = phone['center']
            
            # Tính khoảng cách
            dist_nose = self.calculate_distance(phone_center, nose)
            dist_ear_left = self.calculate_distance(phone_center, left_ear)
            dist_ear_right = self.calculate_distance(phone_center, right_ear)
            
            min_dist = min(dist_nose, dist_ear_left, dist_ear_right)
            
            if min_dist < self.PHONE_DISTANCE_THRESHOLD:
                self.phone_buffer.append(True)
                
                # Kiểm tra temporal consistency (giảm false positive)
                if sum(self.phone_buffer) >= 5:  # 5/15 frames
                    return True, "⚠️ CẢNH BÁO: ĐANG DÙNG ĐIỆN THOẠI KHI LÁI XE!"
        
        self.phone_buffer.append(False)
        return False, None
    
    def check_drinking(
        self,
        objects: List[Dict],
        pose: Optional[Dict]
    ) -> Tuple[bool, Optional[str]]:
        """
        Kiểm tra tài xế có đang uống nước không.
        """
        if pose is None:
            return False, None
        
        drinks = [obj for obj in objects if obj['class_name'] in ['cốc', 'chai']]
        
        if not drinks:
            self.drink_buffer.append(False)
            return False, None
        
        nose = pose['nose']
        
        for drink in drinks:
            drink_center = drink['center']
            dist = self.calculate_distance(drink_center, nose)
            
            if dist < self.DRINK_DISTANCE_THRESHOLD:
                self.drink_buffer.append(True)
                
                if sum(self.drink_buffer) >= 5:
                    return True, f"⚠️ CẢNH BÁO: ĐANG UỐNG NƯỚC KHI LÁI XE!"
        
        self.drink_buffer.append(False)
        return False, None
    
    def check_drowsiness(self, pose: Optional[Dict]) -> Tuple[bool, Optional[str]]:
        """
        Phát hiện buồn ngủ qua góc nghiêng đầu.
        
        Logic:
        - Tính vector vai trái - vai phải
        - Tính góc nghiêng
        - Nếu nghiêng > 25° trong thời gian dài -> CẢNH BÁO
        """
        if pose is None:
            return False, None
        
        left_shoulder = pose['left_shoulder']
        right_shoulder = pose['right_shoulder']
        
        # Tính góc nghiêng
        # WHY: atan2 cho góc chính xác từ vector
        dx = right_shoulder[0] - left_shoulder[0]
        dy = right_shoulder[1] - left_shoulder[1]
        angle = abs(math.degrees(math.atan2(dy, dx)))
        
        # Góc bình thường: 0-10°
        # Nghiêng: > 25°
        is_tilted = angle > 25
        
        self.head_tilt_buffer.append(is_tilted)
        
        # Nếu nghiêng > 50% trong 30 frames (1 giây)
        if sum(self.head_tilt_buffer) >= 15:
            return True, "⚠️ CẢNH BÁO: TÀI XẾ CÓ DẤU HIỆU BUỒN NGỦ!"
        
        return False, None
    
    def draw_warnings(
        self,
        frame: np.ndarray,
        warnings: List[str]
    ) -> np.ndarray:
        """
        Vẽ cảnh báo lên frame (Tiếng Việt).
        """
        if not warnings:
            return frame
        
        # Convert sang PIL
        frame_pil = Image.fromarray(frame)
        draw = ImageDraw.Draw(frame_pil)
        
        h, w = frame.shape[:2]
        
        # Vẽ banner đỏ
        banner_height = 80 * len(warnings)
        draw.rectangle(
            [(0, 0), (w, banner_height)],
            fill=(0, 0, 200, 220)  # Đỏ trong suốt
        )
        
        # Vẽ text
        y_offset = 10
        for warning in warnings:
            if self.font_large:
                draw.text(
                    (20, y_offset),
                    warning,
                    fill=(255, 255, 255),
                    font=self.font_large
                )
                y_offset += 70
            else:
                # Fallback
                frame_cv = np.array(frame_pil)
                cv2.putText(
                    frame_cv,
                    warning,
                    (20, y_offset + 50),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1.2,
                    (255, 255, 255),
                    3
                )
                y_offset += 70
                if y_offset > banner_height:
                    break
                return frame_cv
        
        return np.array(frame_pil)
    
    def process_frame(self, frame: np.ndarray) -> Dict:
        """
        Pipeline xử lý hoàn chỉnh.
        
        Returns:
            Dictionary chứa:
                - annotated_frame: Frame với annotations
                - warnings: Danh sách cảnh báo
                - is_safe: True nếu an toàn
        """
        # Detect objects và pose
        objects = self.detect_objects(frame)
        pose = self.detect_pose(frame)
        
        # Kiểm tra các hành vi nguy hiểm
        warnings = []
        
        using_phone, phone_msg = self.check_phone_use(objects, pose)
        if using_phone and phone_msg:
            warnings.append(phone_msg)
        
        drinking, drink_msg = self.check_drinking(objects, pose)
        if drinking and drink_msg:
            warnings.append(drink_msg)
        
        drowsy, drowsy_msg = self.check_drowsiness(pose)
        if drowsy and drowsy_msg:
            warnings.append(drowsy_msg)
        
        # Vẽ warnings
        annotated_frame = self.draw_warnings(frame, warnings)
        
        return {
            'annotated_frame': annotated_frame,
            'warnings': warnings,
            'is_safe': len(warnings) == 0,
            'using_phone': using_phone,
            'drinking': drinking,
            'drowsy': drowsy
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    try:
        monitor = DriverMonitorV11(device="cuda")
        print("✅ Driver Monitor khởi tạo thành công")
    except Exception as e:
        print(f"❌ Lỗi khởi tạo: {e}")
