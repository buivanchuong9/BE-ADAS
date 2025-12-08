"""
YOLOv11 Detector - Latest YOLO model with improved accuracy
Nâng cấp từ YOLOv8 lên YOLOv11

YOLOv11 Improvements:
- Faster inference speed (10-15% faster than v8)
- Better accuracy (2-3% mAP improvement)
- Improved small object detection
- Better handling of occlusions
- Enhanced tracking capabilities
"""

import cv2
import numpy as np
from ultralytics import YOLO
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
import time


class YOLOv11Detector:
    """
    YOLOv11 Object Detector
    
    Features:
    - Multi-class detection (80 COCO classes)
    - Real-time inference (30+ FPS on GPU)
    - Confidence and IoU thresholding
    - Class filtering
    - Batch processing support
    
    Models:
    - yolo11n: Nano (fastest, 3.2M params)
    - yolo11s: Small (9.4M params)
    - yolo11m: Medium (20.1M params)
    - yolo11l: Large (25.3M params)
    - yolo11x: Extra large (best accuracy, 56.9M params)
    """
    
    def __init__(
        self,
        model_path: str = "yolo11n.pt",
        conf_threshold: float = 0.35,
        iou_threshold: float = 0.45,
        device: str = "auto",
        half: bool = False,
        classes: Optional[List[int]] = None,
        verbose: bool = False
    ):
        """
        Initialize YOLOv11 detector
        
        Args:
            model_path: Path to YOLOv11 weights (.pt file)
            conf_threshold: Confidence threshold (0.0-1.0)
            iou_threshold: IoU threshold for NMS (0.0-1.0)
            device: Device to use ('cpu', 'cuda', 'mps', 'auto')
            half: Use FP16 precision for faster inference
            classes: List of class IDs to detect (None = all classes)
            verbose: Print verbose output
        """
        self.model_path = Path(model_path)
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold
        self.device = device
        self.half = half
        self.classes = classes
        self.verbose = verbose
        
        # Load model
        print(f"🚀 Loading YOLOv11 model: {model_path}")
        self.model = YOLO(str(self.model_path))
        
        # Set device
        if device == "auto":
            import torch
            if torch.cuda.is_available():
                self.device = "cuda"
            elif torch.backends.mps.is_available():
                self.device = "mps"
            else:
                self.device = "cpu"
        
        print(f"✅ YOLOv11 loaded on device: {self.device}")
        
        # Warmup
        self._warmup()
        
        # Stats
        self.total_detections = 0
        self.total_inference_time = 0.0
        self.frame_count = 0
    
    def _warmup(self):
        """Warmup model with dummy input"""
        print("🔥 Warming up YOLOv11...")
        dummy = np.zeros((640, 640, 3), dtype=np.uint8)
        _ = self.model.predict(
            dummy,
            conf=self.conf_threshold,
            iou=self.iou_threshold,
            device=self.device,
            half=self.half,
            verbose=False
        )
        print("✅ Warmup complete")
    
    def detect(
        self,
        frame: np.ndarray,
        draw: bool = False,
        return_annotated: bool = False
    ) -> Tuple[List[Dict[str, Any]], Optional[np.ndarray]]:
        """
        Detect objects in frame
        
        Args:
            frame: Input frame (BGR)
            draw: Draw bounding boxes on frame
            return_annotated: Return annotated frame
            
        Returns:
            (detections, annotated_frame)
            
        Detection format:
        {
            'class_id': int,
            'class_name': str,
            'confidence': float,
            'bbox': [x1, y1, x2, y2],
            'center': [cx, cy],
            'area': float
        }
        """
        start_time = time.time()
        
        # Run inference
        results = self.model.predict(
            frame,
            conf=self.conf_threshold,
            iou=self.iou_threshold,
            classes=self.classes,
            device=self.device,
            half=self.half,
            verbose=self.verbose
        )
        
        # Parse results
        detections = []
        annotated_frame = frame.copy() if draw or return_annotated else None
        
        if len(results) > 0:
            result = results[0]
            boxes = result.boxes
            
            for box in boxes:
                # Extract box data
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                conf = float(box.conf[0].cpu().numpy())
                class_id = int(box.cls[0].cpu().numpy())
                class_name = self.model.names[class_id]
                
                # Calculate center and area
                cx = (x1 + x2) / 2
                cy = (y1 + y2) / 2
                area = (x2 - x1) * (y2 - y1)
                
                detection = {
                    'class_id': class_id,
                    'class_name': class_name,
                    'confidence': conf,
                    'bbox': [float(x1), float(y1), float(x2), float(y2)],
                    'center': [float(cx), float(cy)],
                    'area': float(area)
                }
                detections.append(detection)
                
                # Draw on frame
                if draw or return_annotated:
                    self._draw_box(annotated_frame, detection)
        
        # Update stats
        inference_time = (time.time() - start_time) * 1000
        self.total_inference_time += inference_time
        self.frame_count += 1
        self.total_detections += len(detections)
        
        if self.verbose:
            print(f"Frame {self.frame_count}: {len(detections)} detections in {inference_time:.2f}ms")
        
        return detections, annotated_frame
    
    def _draw_box(self, frame: np.ndarray, detection: Dict[str, Any]):
        """Draw bounding box and label on frame"""
        x1, y1, x2, y2 = [int(v) for v in detection['bbox']]
        class_name = detection['class_name']
        conf = detection['confidence']
        
        # Color based on class
        color = self._get_color(detection['class_id'])
        
        # Draw box
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        
        # Draw label
        label = f"{class_name} {conf:.2f}"
        label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        
        # Background for text
        cv2.rectangle(
            frame,
            (x1, y1 - label_size[1] - 10),
            (x1 + label_size[0], y1),
            color,
            -1
        )
        
        # Text
        cv2.putText(
            frame,
            label,
            (x1, y1 - 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 255, 255),
            2
        )
    
    def _get_color(self, class_id: int) -> Tuple[int, int, int]:
        """Get color for class ID"""
        # Predefined colors for common ADAS classes
        colors = {
            0: (0, 255, 0),      # person - green
            1: (255, 0, 0),      # bicycle - blue
            2: (0, 0, 255),      # car - red
            3: (255, 255, 0),    # motorcycle - cyan
            5: (255, 0, 255),    # bus - magenta
            7: (0, 255, 255),    # truck - yellow
            9: (128, 0, 128),    # traffic light - purple
            11: (255, 128, 0),   # stop sign - orange
        }
        
        return colors.get(class_id, (0, 255, 0))
    
    def detect_batch(
        self,
        frames: List[np.ndarray],
        batch_size: int = 8
    ) -> List[List[Dict[str, Any]]]:
        """
        Detect objects in batch of frames
        
        Args:
            frames: List of input frames
            batch_size: Batch size for inference
            
        Returns:
            List of detections for each frame
        """
        all_detections = []
        
        for i in range(0, len(frames), batch_size):
            batch = frames[i:i+batch_size]
            
            # Run inference on batch
            results = self.model.predict(
                batch,
                conf=self.conf_threshold,
                iou=self.iou_threshold,
                classes=self.classes,
                device=self.device,
                half=self.half,
                verbose=self.verbose
            )
            
            # Parse results for each frame
            for result in results:
                detections = []
                boxes = result.boxes
                
                for box in boxes:
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    conf = float(box.conf[0].cpu().numpy())
                    class_id = int(box.cls[0].cpu().numpy())
                    class_name = self.model.names[class_id]
                    
                    cx = (x1 + x2) / 2
                    cy = (y1 + y2) / 2
                    area = (x2 - x1) * (y2 - y1)
                    
                    detection = {
                        'class_id': class_id,
                        'class_name': class_name,
                        'confidence': conf,
                        'bbox': [float(x1), float(y1), float(x2), float(y2)],
                        'center': [float(cx), float(cy)],
                        'area': float(area)
                    }
                    detections.append(detection)
                
                all_detections.append(detections)
        
        return all_detections
    
    def get_stats(self) -> Dict[str, Any]:
        """Get detector statistics"""
        avg_inference_time = self.total_inference_time / self.frame_count if self.frame_count > 0 else 0
        avg_fps = 1000 / avg_inference_time if avg_inference_time > 0 else 0
        avg_detections = self.total_detections / self.frame_count if self.frame_count > 0 else 0
        
        return {
            'model': str(self.model_path),
            'device': self.device,
            'total_frames': self.frame_count,
            'total_detections': self.total_detections,
            'avg_inference_time_ms': round(avg_inference_time, 2),
            'avg_fps': round(avg_fps, 1),
            'avg_detections_per_frame': round(avg_detections, 2)
        }
    
    def reset_stats(self):
        """Reset statistics"""
        self.total_detections = 0
        self.total_inference_time = 0.0
        self.frame_count = 0


# COCO class names for YOLOv11
COCO_CLASSES = [
    'person', 'bicycle', 'car', 'motorcycle', 'airplane', 'bus', 'train', 'truck',
    'boat', 'traffic light', 'fire hydrant', 'stop sign', 'parking meter', 'bench',
    'bird', 'cat', 'dog', 'horse', 'sheep', 'cow', 'elephant', 'bear', 'zebra',
    'giraffe', 'backpack', 'umbrella', 'handbag', 'tie', 'suitcase', 'frisbee',
    'skis', 'snowboard', 'sports ball', 'kite', 'baseball bat', 'baseball glove',
    'skateboard', 'surfboard', 'tennis racket', 'bottle', 'wine glass', 'cup',
    'fork', 'knife', 'spoon', 'bowl', 'banana', 'apple', 'sandwich', 'orange',
    'broccoli', 'carrot', 'hot dog', 'pizza', 'donut', 'cake', 'chair', 'couch',
    'potted plant', 'bed', 'dining table', 'toilet', 'tv', 'laptop', 'mouse',
    'remote', 'keyboard', 'cell phone', 'microwave', 'oven', 'toaster', 'sink',
    'refrigerator', 'book', 'clock', 'vase', 'scissors', 'teddy bear', 'hair drier',
    'toothbrush'
]


if __name__ == "__main__":
    # Test YOLOv11 detector
    print("Testing YOLOv11 detector...")
    
    detector = YOLOv11Detector(
        model_path="yolo11n.pt",
        conf_threshold=0.35,
        iou_threshold=0.45,
        device="auto",
        verbose=True
    )
    
    # Create test image
    test_frame = np.random.randint(0, 255, (640, 640, 3), dtype=np.uint8)
    
    # Detect
    detections, annotated = detector.detect(test_frame, draw=True, return_annotated=True)
    
    print(f"\n✅ Detected {len(detections)} objects")
    print(f"📊 Stats: {detector.get_stats()}")
