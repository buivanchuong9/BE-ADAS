"""
ADAS VIDEO PIPELINE - Tích hợp Đa Module
=========================================
Pipeline xử lý video real-time với 4 AI models:
- Object Detection (Xe cộ, Người)
- Lane Segmentation (Tesla-style)
- Driver Monitoring (Cảnh báo nguy hiểm)
- Traffic Sign Recognition (Biển báo)
"""

import cv2
import numpy as np
import torch
import time
from pathlib import Path
from typing import Optional, Dict, List
from threading import Thread, Event
from queue import Queue, Empty, Full
import logging
from PIL import Image, ImageDraw, ImageFont

# Import các modules đã refactor
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.perception.object.object_detector_v11 import ObjectDetectorV11
from backend.perception.lane.lane_detector_ufld import UFLDLaneDetector
from backend.perception.lane.lane_detector_v4 import LaneDetectorV4
from backend.perception.driver.driver_monitor_v11 import DriverMonitorV11
from backend.perception.traffic.traffic_sign_v11 import TrafficSignV11

logger = logging.getLogger(__name__)


class ADASPipeline:
    """
    Pipeline ADAS hoàn chỉnh với Multi-Threading.
    
    Architecture:
    - Thread 1 (Reader): Đọc video/camera → Queue
    - Thread 2 (Processor): Inference 4 models → Overlay
    - Thread 3 (Writer): Ghi video + hiển thị
    
    Visual Layers (Bottom → Top):
    1. Lane Segmentation (Background)
    2. Object Bboxes + Traffic Signs (Middle)
    3. Driver Warnings + HUD (Top)
    """
    
    def __init__(
        self,
        device: str = "cuda",
        input_resolution: tuple = (1280, 720),
        enable_display: bool = True,
        save_output: bool = True,
        output_path: str = "output_demo_tesla_style.mp4",
        realtime_mode: bool = False  # True: Master Clock Simulation
    ):
        """
        Khởi tạo ADAS Pipeline.
        
        Args:
            device: "cuda" hoặc "cpu"
            input_resolution: (width, height) cho resize
            enable_display: Hiển thị video real-time
            save_output: Lưu video output
            output_path: Đường dẫn output video
        """
        self.device = device
        self.input_resolution = input_resolution
        self.enable_display = enable_display
        self.save_output = save_output
        self.output_path = output_path
        self.realtime_mode = realtime_mode
        
        # Threading components
        # Realtime=True -> Buffer nhỏ (2) để giảm latency. Fast=True -> Buffer to (30).
        q_size = 2 if realtime_mode else 30
        self.frame_queue = Queue(maxsize=q_size)
        self.result_queue = Queue(maxsize=q_size)
        self.stop_event = Event()
        
        # FPS tracking
        self.fps = 0.0
        self.frame_count = 0
        self.source_fps = 30.0  # FPS gốc của video nguồn
        self.start_time = None
        
        # Video writer
        self.video_writer = None
        
        logger.info("=" * 60)
        logger.info("🚀 KHỞI TẠO ADAS PIPELINE")
        logger.info("=" * 60)
        
        # Warmup GPU
        if device == "cuda" and torch.cuda.is_available():
            torch.cuda.init()
            torch.set_float32_matmul_precision('high')
            torch.backends.cudnn.benchmark = True
            logger.info(f"✅ GPU: {torch.cuda.get_device_name(0)}")
            logger.info(f"   VRAM: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")
        
        # Load models
        logger.info("\n📦 ĐANG TẢI MODELS...")
        
        try:
            # 1. Object Detection
            logger.info("   [1/4] Object Detection...")
            self.object_detector = ObjectDetectorV11(
                device=device,
                conf_threshold=0.5
            )
            
            # 2. Lane Detection — UFLD v2 (Ultra Fast Lane Detection)
            logger.info("   [2/4] Lane Detection (UFLD)...")
            self.lane_detector = UFLDLaneDetector(
                device=device,
            )
            
            # 3. Driver Monitor
            logger.info("   [3/4] Driver Monitoring...")
            self.driver_monitor = DriverMonitorV11(
                device=device
            )
            
            # 4. Traffic Signs
            logger.info("   [4/4] Traffic Sign Recognition...")
            self.traffic_detector = TrafficSignV11(
                device=device,
                conf_threshold=0.5
            )
            
            logger.info("\n✅ TẤT CẢ MODELS ĐÃ LOAD THÀNH CÔNG!")
            
        except Exception as e:
            logger.error(f"❌ Lỗi load models: {e}")
            raise
        
        # Load font cho HUD
        try:
            font_path = "backend/assets/fonts/Roboto-Bold.ttf"
            self.font_hud = ImageFont.truetype(font_path, 18)
            self.font_fps = ImageFont.truetype(font_path, 24)
        except:
            self.font_hud = None
            self.font_fps = None
        
        logger.info("=" * 60)
    
    def process_frame(self, frame: np.ndarray) -> Dict:
        """
        Xử lý 1 frame với pipeline ADAS hoàn chỉnh - Tối ưu GPU.
        
        Pipeline Sequence (tối ưu performance):
        1. Lane Detection (background layer)
        2. Object Detection + Distance Estimation 
        3. Traffic Signs Recognition
        4. Driver Monitoring
        5. Risk Assessment & Vietnam Warnings
        
        Args:
            frame: Frame RGB/BGR input
            
        Returns:
            Dictionary với kết quả đầy đủ + annotated frame
        """
        try:
            # Chuẩn hóa input frame
            if frame.shape[1] != self.input_resolution[0]:
                frame = cv2.resize(frame, self.input_resolution)
            
            h, w = frame.shape[:2]
            results = {'frame_shape': (h, w), 'warnings': []}
            
            # ===================================
            # LAYER 1: LANE SEGMENTATION (Background)
            # ===================================
            try:
                lane_result = self.lane_detector.process_frame(frame)
                results['lane'] = lane_result
                overlay_frame = lane_result.get('annotated_frame', frame).copy()
                
                # Đánh giá lane departure risk
                if not lane_result.get('has_lane', False):
                    results['warnings'].append({
                        'type': 'lane_departure',
                        'message': 'CẢNH BÁO: Không phát hiện làn đường!',
                        'severity': 'high'
                    })
            except Exception as e:
                logger.warning(f"Lỗi phát hiện làn đường: {e}")
                results['lane'] = {'error': str(e), 'has_lane': False}
                overlay_frame = frame.copy()
            
            # ===================================  
            # LAYER 2: OBJECT DETECTION + DISTANCE
            # ===================================
            try:
                object_result = self.object_detector.process_frame(overlay_frame)
                detections = object_result.get('detections', [])
                
                # Tính distance cho từng object
                objects_with_distance = []
                for obj in detections:
                    try:
                        # Distance estimation
                        bbox = obj.get('bbox')
                        if bbox:
                            from backend.perception.distance.distance_estimator import DistanceEstimator
                            estimator = DistanceEstimator()
                            
                            distance = estimator.estimate_distance_bbox(
                                bbox=bbox,
                                vehicle_type=obj.get('class_name', 'car'),
                                frame_height=h
                            )
                            
                            # TTC calculation (giả sử velocity = 0 nếu không có tracking)
                            velocity = obj.get('velocity', 0)  # m/s
                            ttc = distance / max(velocity, 0.1) if velocity > 0 else float('inf')
                            
                            # Risk assessment
                            risk_level = self._assess_collision_risk(distance, ttc, obj.get('class_name', ''))
                            
                            obj_enhanced = {
                                **obj,
                                'distance_m': distance,
                                'ttc_s': ttc,
                                'risk_level': risk_level
                            }
                            
                            # Tạo warning nếu nguy hiểm
                            if risk_level in ['DANGER', 'CRITICAL']:
                                class_vn = self._translate_class_name(obj.get('class_name', ''))
                                warning_msg = f"NGUY HIỂM! {class_vn} ở {distance:.1f}m"
                                if ttc < 3.0:
                                    warning_msg += f" (TTC: {ttc:.1f}s)"
                                
                                results['warnings'].append({
                                    'type': 'collision_risk',
                                    'message': warning_msg,
                                    'severity': 'critical' if risk_level == 'CRITICAL' else 'high',
                                    'object_id': obj.get('track_id', 0),
                                    'distance': distance,
                                    'ttc': ttc
                                })
                            
                            objects_with_distance.append(obj_enhanced)
                    
                    except Exception as dist_error:
                        logger.debug(f"Lỗi tính distance cho object: {dist_error}")
                        objects_with_distance.append(obj)
                
                results['objects'] = {
                    'detections': objects_with_distance,
                    'total_count': len(objects_with_distance),
                    'stats': object_result.get('stats', {}),
                    'annotated_frame': object_result.get('annotated_frame', overlay_frame)
                }
                overlay_frame = results['objects']['annotated_frame'].copy()
                        
            except Exception as e:
                logger.warning(f"Lỗi nhận diện vật thể: {e}")
                results['objects'] = {'error': str(e), 'detections': [], 'total_count': 0}
                
            # ===================================
            # LAYER 3: TRAFFIC SIGNS (Middle)
            # ===================================
            try:
                traffic_result = self.traffic_detector.process_frame(overlay_frame)
                results['traffic'] = traffic_result
                overlay_frame = traffic_result.get('annotated_frame', overlay_frame).copy()
                
                # Cảnh báo biển báo quan trọng
                signs = traffic_result.get('detections', [])
                for sign in signs:
                    sign_type = sign.get('class_name', '')
                    if sign_type in ['stop_sign', 'yield_sign', 'speed_limit']:
                        results['warnings'].append({
                            'type': 'traffic_sign',
                            'message': f"Phát hiện: {self._translate_sign(sign_type)}",
                            'severity': 'medium'
                        })
                        
            except Exception as e:
                logger.warning(f"Lỗi nhận diện biển báo: {e}")
                results['traffic'] = {'error': str(e)}
            
            # ===================================
            # LAYER 4: DRIVER MONITORING (Top)
            # ===================================
            try:
                driver_result = self.driver_monitor.process_frame(overlay_frame)
                results['driver'] = driver_result
                overlay_frame = driver_result.get('annotated_frame', overlay_frame).copy()
                
                # Driver state warnings
                driver_state = driver_result.get('state', 'normal')
                if driver_state != 'normal':
                    state_vn = self._translate_driver_state(driver_state)
                    results['warnings'].append({
                        'type': 'driver_state',
                        'message': f"CẢNH BÁO TÀI XẾ: {state_vn}",
                        'severity': 'high' if driver_state in ['drowsy', 'distracted'] else 'medium'
                    })
                        
            except Exception as e:
                logger.warning(f"Lỗi giám sát tài xế: {e}")
                results['driver'] = {'error': str(e), 'state': 'unknown'}
            
            # ===================================
            # FINAL: VIETNAM HUD & ANNOTATIONS  
            # ===================================
            final_frame = self.draw_vietnamese_hud(overlay_frame, results)
            results['annotated_frame'] = final_frame
            results['success'] = True
            
            return results
            
        except Exception as e:
            logger.error(f"❌ Lỗi nghiêm trọng trong process_frame: {e}")
            return {
                'annotated_frame': frame,
                'error': str(e), 
                'success': False,
                'warnings': [{'type': 'system_error', 'message': f'Lỗi hệ thống: {str(e)}', 'severity': 'critical'}]
            }
    
    def draw_hud(self, frame: np.ndarray, results: Dict) -> np.ndarray:
        """
        Vẽ HUD (Head-Up Display) lên frame - Tiếng Việt.
        
        HUD Info:
        - FPS (góc trên trái)
        - Thống kê detections (góc trên phải)
        - Warnings nếu có (center top)
        
        Args:
            frame: Frame đã overlay
            results: Kết quả từ process_frame
            
        Returns:
            Frame với HUD
        """
        h, w = frame.shape[:2]
        
        # Convert sang PIL
        frame_pil = Image.fromarray(frame)
        draw = ImageDraw.Draw(frame_pil)
        
        # ===================================
        # FPS Counter (Góc trên trái)
        # ===================================
        fps_text = f"FPS: {self.fps:.1f}"
        if self.font_fps:
            # Background
            bbox = draw.textbbox((10, 10), fps_text, font=self.font_fps)
            draw.rectangle(
                [(bbox[0] - 5, bbox[1] - 5), (bbox[2] + 5, bbox[3] + 5)],
                fill=(0, 0, 0, 180)
            )
            # Text
            draw.text((10, 10), fps_text, fill=(0, 255, 0), font=self.font_fps)
        
        # ===================================
        # Stats Panel (Góc trên phải)
        # ===================================
        if 'objects' in results and self.font_hud:
            stats = results['objects'].get('stats', {})
            
            stats_lines = [
                f"Xe cơ giới: {stats.get('xe_cơ_giới', 0)}",
                f"Xe máy: {stats.get('xe_máy', 0)}",
                f"Người: {stats.get('người', 0)}",
            ]
            
            # Lane status
            if 'lane' in results:
                lane_status = "✓ Có" if results['lane'].get('has_lane', False) else "✗ Không"
                stats_lines.append(f"Làn đường: {lane_status}")
            
            # Traffic signs
            if 'traffic' in results:
                sign_count = results['traffic'].get('total_signs', 0)
                stats_lines.append(f"Biển báo: {sign_count}")
            
            # Vẽ panel
            y_offset = 10
            for line in stats_lines:
                bbox = draw.textbbox((w - 200, y_offset), line, font=self.font_hud)
                draw.rectangle(
                    [(bbox[0] - 5, bbox[1] - 2), (bbox[2] + 5, bbox[3] + 2)],
                    fill=(0, 0, 0, 180)
                )
                draw.text((w - 200, y_offset), line, fill=(255, 255, 255), font=self.font_hud)
                y_offset += 25
        
        return np.array(frame_pil)
    
    def reader_thread(self, video_source):
        """
        Thread 1: Đọc video/camera và đẩy vào queue.
        
        Args:
            video_source: Đường dẫn video hoặc camera ID
        """
        logger.info(f"🎬 Reader Thread: Bắt đầu đọc từ {video_source}")
        
        cap = cv2.VideoCapture(video_source)
        
        if not cap.isOpened():
            logger.error(f"❌ Không thể mở video: {video_source}")
            self.stop_event.set()
            return
        
        # Lấy thông tin video (Float FPS để tính clock chuẩn)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        self.source_fps = fps  # Lưu FPS gốc để Writer dùng
        frame_interval = 1.0 / fps
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        mode_str = "REALTIME SIMULATION" if self.realtime_mode else "MAX SPEED"
        logger.info(f"   Video: {fps:.2f} FPS | Mode: {mode_str}")
        
        frame_idx = 0
        next_frame_time = time.time()
        
        while not self.stop_event.is_set():
            # 1. Master Clock Pacing (Chỉ chạy khi Realtime Mode)
            if self.realtime_mode:
                now = time.time()
                delay = next_frame_time - now
                if delay > 0:
                    time.sleep(delay)
                next_frame_time = time.time() + frame_interval

            # 2. Read Frame
            ret, frame = cap.read()
            
            if not ret:
                logger.info("📹 Video đã hết")
                break
            
            # Convert BGR → RGB
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Đẩy vào queue (BLOCKING MODE)
            self.frame_queue.put(frame_rgb, block=True)
            frame_idx += 1
        
        cap.release()
        logger.info("✅ Reader Thread: Hoàn thành")
    
    def processor_thread(self):
        """
        Thread 2: Lấy frame từ queue, chạy inference, đẩy kết quả.
        """
        logger.info("🔬 Processor Thread: Bắt đầu xử lý")
        
        while not self.stop_event.is_set():
            try:
                # Lấy frame từ queue
                frame = self.frame_queue.get(timeout=1.0)
                
                # Process với 4 models
                results = self.process_frame(frame)
                
                # Vẽ HUD
                final_frame = self.draw_hud(results['frame'], results)
                
                # Đẩy vào result queue
                self.result_queue.put(final_frame, timeout=1.0)
                
            except Empty:
                # Không có frame, tiếp tục chờ
                continue
            except Full:
                logger.warning("⚠️ Result queue đầy")
            except Exception as e:
                logger.error(f"❌ Lỗi processor: {e}")
        
        logger.info("✅ Processor Thread: Hoàn thành")
    
    def writer_thread(self):
        """
        Thread 3: Hiển thị và/hoặc ghi video.
        """
        logger.info("💾 Writer Thread: Bắt đầu ghi/hiển thị")
        
        self.start_time = time.time()
        
        while not self.stop_event.is_set():
            try:
                # Lấy frame đã xử lý
                frame = self.result_queue.get(timeout=1.0)
                
                # Convert RGB → BGR cho OpenCV
                frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                
                # Update FPS
                self.frame_count += 1
                elapsed = time.time() - self.start_time
                if elapsed > 0:
                    self.fps = self.frame_count / elapsed
                
                # Ghi video
                if self.save_output:
                    if self.video_writer is None:
                        h, w = frame_bgr.shape[:2]
                        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                        self.video_writer = cv2.VideoWriter(
                            self.output_path,
                            fourcc,
                            self.source_fps,  # Sử dụng FPS gốc của video
                            (w, h)
                        )
                        logger.info(f"📹 Đang ghi video: {self.output_path}")
                    
                    self.video_writer.write(frame_bgr)
                
                # Hiển thị
                if self.enable_display:
                    cv2.imshow('ADAS Demo - Tesla Style', frame_bgr)
                    
                    # ESC để thoát
                    if cv2.waitKey(1) & 0xFF == 27:
                        logger.info("⏹️  Người dùng dừng video")
                        self.stop_event.set()
                        break
                
            except Empty:
                continue
            except Exception as e:
                logger.error(f"❌ Lỗi writer: {e}")
        
        # Cleanup
        if self.video_writer:
            self.video_writer.release()
            logger.info(f"✅ Video đã lưu: {self.output_path}")
        
        if self.enable_display:
            cv2.destroyAllWindows()
        
        logger.info("✅ Writer Thread: Hoàn thành")
    
    def _assess_collision_risk(self, distance: float, ttc: float, obj_type: str) -> str:
        """
        Đánh giá mức độ rủi ro va chạm cho giao thông Việt Nam.
        
        Args:
            distance: Khoảng cách (m)
            ttc: Time to collision (s)  
            obj_type: Loại vật thể
            
        Returns:
            Risk level: SAFE, CAUTION, DANGER, CRITICAL
        """
        # Thresholds khác nhau cho các loại xe ở VN
        if obj_type in ['motorcycle', 'bicycle', 'person']:
            # Xe máy, xe đạp, người đi bộ - khoảng cách gần hơn
            critical_dist = 2.0
            danger_dist = 5.0  
            caution_dist = 10.0
        else:
            # Ô tô, xe tải, xe buýt
            critical_dist = 3.0
            danger_dist = 8.0
            caution_dist = 15.0
        
        # Risk assessment theo distance
        if distance <= critical_dist:
            return 'CRITICAL'
        elif distance <= danger_dist:
            return 'DANGER'
        elif distance <= caution_dist:
            return 'CAUTION'
        
        # Risk assessment theo TTC
        if ttc <= 1.0:
            return 'CRITICAL'
        elif ttc <= 2.5:
            return 'DANGER'
        elif ttc <= 4.0:
            return 'CAUTION'
            
        return 'SAFE'
    
    def _translate_class_name(self, class_name: str) -> str:
        """Dịch tên class sang tiếng Việt."""
        translations = {
            'person': 'Người đi bộ',
            'car': 'Ô tô',
            'truck': 'Xe tải', 
            'bus': 'Xe buýt',
            'motorcycle': 'Xe máy',
            'bicycle': 'Xe đạp',
            'traffic_light': 'Đèn giao thông'
        }
        return translations.get(class_name.lower(), class_name)
    
    def _translate_driver_state(self, state: str) -> str:
        """Dịch trạng thái tài xế."""
        states = {
            'normal': 'Bình thường',
            'drowsy': 'Buồn ngủ',
            'distracted': 'Mất tập trung', 
            'looking_away': 'Nhìn ra ngoài',
            'eyes_closed': 'Nhắm mắt',
            'phone_use': 'Sử dụng điện thoại',
            'unknown': 'Không rõ'
        }
        return states.get(state, 'Không rõ')
    
    def _translate_sign(self, sign_type: str) -> str:
        """Dịch biển báo giao thông."""
        signs = {
            'stop_sign': 'Biển báo DỪNG',
            'yield_sign': 'Biển nhường đường',
            'speed_limit': 'Biển giới hạn tốc độ',
            'no_entry': 'Biển cấm đi vào',
            'turn_left': 'Biển rẽ trái',
            'turn_right': 'Biển rẽ phải'
        }
        return signs.get(sign_type, 'Biển báo')
    
    def draw_vietnamese_hud(self, frame: np.ndarray, results: Dict) -> np.ndarray:
        """
        Vẽ HUD (Head-Up Display) tiếng Việt đầy đủ.
        
        HUD Layout:
        - Top Left: System info (FPS, models status)
        - Top Right: Detection stats  
        - Center Top: Critical warnings
        - Bottom Left: Driver state
        - Bottom Right: Distance info cho closest object
        
        Args:
            frame: Annotated frame từ các AI models
            results: Kết quả từ process_frame
            
        Returns:
            Frame với HUD hoàn chỉnh
        """
        hud_frame = frame.copy()
        h, w, _ = hud_frame.shape
        
        # === TOP LEFT: SYSTEM INFO ===
        self._draw_system_panel(hud_frame, results)
        
        # === TOP RIGHT: DETECTION STATS ===
        self._draw_stats_panel(hud_frame, results, w)
        
        # === CENTER TOP: CRITICAL WARNINGS ===
        self._draw_warning_panel(hud_frame, results, w)
        
        # === BOTTOM LEFT: DRIVER STATE ===
        self._draw_driver_panel(hud_frame, results, h)
        
        # === BOTTOM RIGHT: CLOSEST OBJECT INFO ===
        self._draw_distance_panel(hud_frame, results, w, h)
        
        return hud_frame
    
    def _draw_system_panel(self, frame: np.ndarray, results: Dict):
        """Vẽ system info panel (top left)."""
        panel_bg = (0, 0, 0, 180)  # Đen trong suốt
        text_color = (0, 255, 0)   # Xanh lá
        
        # Background panel
        cv2.rectangle(frame, (10, 10), (300, 120), (0, 0, 0), -1)
        cv2.rectangle(frame, (10, 10), (300, 120), (0, 255, 0), 2)
        
        # System info
        y_pos, spacing = 30, 18
        
        cv2.putText(frame, f"FPS: {self.fps:.1f}", (20, y_pos), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, text_color, 2)
        y_pos += spacing
        
        cv2.putText(frame, f"Độ phân giải: {self.input_resolution[0]}x{self.input_resolution[1]}", 
                   (20, y_pos), cv2.FONT_HERSHEY_SIMPLEX, 0.5, text_color, 1)
        y_pos += spacing
        
        # Model status
        lane_ok = not results.get('lane', {}).get('error')
        obj_ok = not results.get('objects', {}).get('error') 
        traffic_ok = not results.get('traffic', {}).get('error')
        driver_ok = not results.get('driver', {}).get('error')
        
        status_color = (0, 255, 0) if all([lane_ok, obj_ok, traffic_ok, driver_ok]) else (0, 165, 255)
        cv2.putText(frame, "Models: " + ("HOẠT ĐỘNG" if status_color == (0, 255, 0) else "LỖI"), 
                   (20, y_pos), cv2.FONT_HERSHEY_SIMPLEX, 0.5, status_color, 1)
        y_pos += spacing
        
        cv2.putText(frame, f"Device: {self.device.upper()}", (20, y_pos), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, text_color, 1)
    
    def _draw_stats_panel(self, frame: np.ndarray, results: Dict, w: int):
        """Vẽ detection statistics panel (top right).""" 
        # Background
        cv2.rectangle(frame, (w-250, 10), (w-10, 150), (0, 0, 0), -1)
        cv2.rectangle(frame, (w-250, 10), (w-10, 150), (255, 255, 255), 2)
        
        y_pos, spacing = 30, 20
        text_color = (255, 255, 255)
        
        # Object stats
        objects = results.get('objects', {}).get('detections', [])
        total_objects = len(objects)
        
        cv2.putText(frame, f"Tổng vật thể: {total_objects}", (w-240, y_pos), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, text_color, 2)
        y_pos += spacing
        
        # Đếm theo loại
        type_counts = {}
        for obj in objects:
            class_vn = self._translate_class_name(obj.get('class_name', ''))
            type_counts[class_vn] = type_counts.get(class_vn, 0) + 1
        
        for obj_type, count in type_counts.items():
            cv2.putText(frame, f"{obj_type}: {count}", (w-240, y_pos), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, text_color, 1)
            y_pos += spacing if y_pos < 140 else 0
        
        # Lane status
        has_lane = results.get('lane', {}).get('has_lane', False)
        lane_color = (0, 255, 0) if has_lane else (0, 165, 255)
        lane_text = "Có làn đường" if has_lane else "Không có làn"
        cv2.putText(frame, lane_text, (w-240, 140), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, lane_color, 1)
    
    def _draw_warning_panel(self, frame: np.ndarray, results: Dict, w: int):
        """Vẽ critical warnings panel (center top)."""
        warnings = results.get('warnings', [])
        critical_warnings = [w for w in warnings if w.get('severity') in ['critical', 'high']]
        
        if not critical_warnings:
            return
        
        y_start = 50
        for i, warning in enumerate(critical_warnings[:2]):  # Tối đa 2 warnings
            msg = warning.get('message', '')
            severity = warning.get('severity', 'medium')
            
            # Màu theo severity
            if severity == 'critical':
                color = (0, 0, 255)  # Đỏ
                bg_color = (0, 0, 100)
            else:
                color = (0, 165, 255)  # Cam
                bg_color = (0, 50, 100)
            
            # Tính kích thước text
            text_size = cv2.getTextSize(msg, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)[0]
            text_w, text_h = text_size
            
            # Vị trí center
            x_center = (w - text_w) // 2
            y_pos = y_start + i * 50
            
            # Background với padding
            padding = 15
            cv2.rectangle(frame, 
                         (x_center - padding, y_pos - text_h - padding//2), 
                         (x_center + text_w + padding, y_pos + padding//2),
                         bg_color, -1)
            cv2.rectangle(frame,
                         (x_center - padding, y_pos - text_h - padding//2), 
                         (x_center + text_w + padding, y_pos + padding//2),
                         color, 3)
            
            # Warning text
            cv2.putText(frame, msg, (x_center, y_pos), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
    
    def _draw_driver_panel(self, frame: np.ndarray, results: Dict, h: int):
        """Vẽ driver state panel (bottom left)."""
        driver_info = results.get('driver', {})
        state = driver_info.get('state', 'unknown')
        confidence = driver_info.get('confidence', 0.0)
        
        # Background
        cv2.rectangle(frame, (10, h-80), (300, h-10), (0, 0, 0), -1)
        
        # Màu theo driver state
        if state == 'normal':
            color = (0, 255, 0)  # Xanh - an toàn
        elif state in ['drowsy', 'distracted', 'eyes_closed']:
            color = (0, 0, 255)  # Đỏ - nguy hiểm
        else:
            color = (0, 165, 255)  # Cam - cảnh báo
        
        cv2.rectangle(frame, (10, h-80), (300, h-10), color, 2)
        
        # Driver state text
        state_vn = self._translate_driver_state(state)
        cv2.putText(frame, f"Tài xế: {state_vn}", (20, h-50), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        
        # Confidence
        if confidence > 0:
            cv2.putText(frame, f"Độ tin cậy: {confidence:.0%}", (20, h-25), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
    
    def _draw_distance_panel(self, frame: np.ndarray, results: Dict, w: int, h: int):
        """Vẽ distance info panel cho object gần nhất (bottom right)."""
        objects = results.get('objects', {}).get('detections', [])
        if not objects:
            return
        
        # Tìm object gần nhất
        closest_obj = min(objects, key=lambda obj: obj.get('distance_m', float('inf')))
        distance = closest_obj.get('distance_m', 0)
        ttc = closest_obj.get('ttc_s', float('inf'))
        risk = closest_obj.get('risk_level', 'SAFE')
        class_vn = self._translate_class_name(closest_obj.get('class_name', ''))
        
        # Background  
        cv2.rectangle(frame, (w-280, h-100), (w-10, h-10), (0, 0, 0), -1)
        
        # Màu theo risk level
        risk_colors = {
            'SAFE': (0, 255, 0),
            'CAUTION': (0, 255, 255), 
            'DANGER': (0, 165, 255),
            'CRITICAL': (0, 0, 255)
        }
        color = risk_colors.get(risk, (255, 255, 255))
        cv2.rectangle(frame, (w-280, h-100), (w-10, h-10), color, 2)
        
        # Distance info
        y_pos = h-75
        cv2.putText(frame, f"Gần nhất: {class_vn}", (w-270, y_pos), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        
        y_pos += 20
        cv2.putText(frame, f"Khoảng cách: {distance:.1f}m", (w-270, y_pos), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
        
        y_pos += 18
        if ttc < 10:
            cv2.putText(frame, f"TTC: {ttc:.1f}s", (w-270, y_pos), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 165, 255), 1)
        else:
            cv2.putText(frame, "TTC: An toàn", (w-270, y_pos), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

    def start(self, video_source: str):
        """
        Khởi động pipeline với video source.
        
        Args:
            video_source: Đường dẫn video hoặc camera (0, 1, ...)
        """
        logger.info("=" * 60)
        logger.info("🚀 BẮT ĐẦU ADAS PIPELINE")
        logger.info("=" * 60)
        
        # Khởi động 3 threads
        threads = [
            Thread(target=self.reader_thread, args=(video_source,), daemon=True),
            Thread(target=self.processor_thread, daemon=True),
            Thread(target=self.writer_thread, daemon=True)
        ]
        
        for t in threads:
            t.start()
        
        logger.info("✅ Tất cả threads đã khởi động")
        logger.info("   Nhấn ESC để dừng...")
        
        # Đợi threads hoàn thành
        try:
            for t in threads:
                t.join()
        except KeyboardInterrupt:
            logger.info("\n⏹️  Dừng pipeline (Ctrl+C)")
            self.stop_event.set()
            for t in threads:
                t.join(timeout=2.0)
        
        logger.info("=" * 60)
        logger.info(f"✅ HOÀN THÀNH - FPS TB: {self.fps:.1f}")
        logger.info("=" * 60)


def process_video(
    input_path: str = None,
    video_path: str = None,
    output_path: str = "output_processed.mp4",
    device: str = "cuda",
    video_type: str = "dashcam",
    enable_display: bool = False,
    **kwargs
) -> Dict:
    """
    Wrapper function for backward compatibility with old API.
    Process video with ADAS pipeline.
    
    Args:
        input_path: Đường dẫn video input (old parameter name)
        video_path: Đường dẫn video input (new parameter name)
        output_path: Đường dẫn video output
        device: "cuda" hoặc "cpu"
        video_type: "dashcam" hoặc "in_cabin" (for compatibility, not used in v11)
        enable_display: Hiển thị video (default False cho worker)
        **kwargs: Other parameters for compatibility (ignored)
        
    Returns:
        Dictionary chứa thông tin kết quả (format cũ)
    """
    # Backward compatibility: support both input_path and video_path
    source_path = input_path or video_path
    
    if source_path is None:
        raise ValueError("Either input_path or video_path must be provided")
    
    logger.info(f"[process_video] Input: {source_path}")
    logger.info(f"[process_video] Output: {output_path}")
    logger.info(f"[process_video] Device: {device}, Type: {video_type}")
    
    try:
        # Khởi tạo pipeline
        pipeline = ADASPipeline(
            device=device,
            input_resolution=(1280, 720),
            enable_display=enable_display,
            save_output=True,
            output_path=output_path
        )
        
        # Chạy pipeline
        pipeline.start(source_path)
        
        # Return format matching old API
        return {
            'success': True,
            'status': 'success',
            'output_path': output_path,
            'fps': pipeline.fps,
            'frames_processed': pipeline.frame_count,
            'events': [],  # Old API expected this
            'stats': {     # Old API expected this
                'total_frames': pipeline.frame_count,
                'fps': pipeline.fps
            }
        }
        
    except Exception as e:
        logger.error(f"❌ Lỗi process_video: {e}", exc_info=True)
        # Return format matching old API error
        return {
            'success': False,
            'status': 'error',
            'error': str(e)
        }


def main():
    """Demo pipeline."""
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Khởi tạo pipeline
    pipeline = ADASPipeline(
        device="cuda",
        input_resolution=(1280, 720),
        enable_display=True,
        save_output=True,
        output_path="output_demo_tesla_style.mp4"
    )
    
    # Video source
    if len(sys.argv) > 1:
        video_path = sys.argv[1]
    else:
        # Default: Camera
        video_path = 0
        logger.info("⚠️ Không có video input, sử dụng camera")
    
    # Chạy pipeline
    pipeline.start(video_path)


if __name__ == "__main__":
    main()
