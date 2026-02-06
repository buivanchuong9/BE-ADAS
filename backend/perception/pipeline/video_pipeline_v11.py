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
from backend.perception.lane.lane_detector_v11 import LaneDetectorV11
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
            
            # 2. Lane Detection
            logger.info("   [2/4] Lane Segmentation...")
            self.lane_detector = LaneDetectorV11(
                device=device,
                use_cyan=True
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
        Xử lý 1 frame với 4 AI models.
        
        WHY Sequential (không parallel):
        - Python GIL khóa multi-threading cho CPU-bound tasks
        - Nhưng GPU inference là I/O-bound → GIL release khi gọi CUDA
        - Sequential đơn giản hơn, ít race condition
        
        Args:
            frame: Frame RGB
            
        Returns:
            Dictionary chứa kết quả từ 4 models
        """
        try:
            # Resize nếu cần
            if frame.shape[1] != self.input_resolution[0]:
                frame = cv2.resize(frame, self.input_resolution)
            
            # ===================================
            # LAYER 1: LANE SEGMENTATION (Background)
            # ===================================
            lane_result = self.lane_detector.process_frame(frame)
            overlay_frame = lane_result['annotated_frame'].copy()
            
            # ===================================
            # LAYER 2: OBJECT DETECTION (Middle)
            # ===================================
            object_result = self.object_detector.process_frame(overlay_frame)
            overlay_frame = object_result['annotated_frame'].copy()
            
            # ===================================
            # LAYER 3: TRAFFIC SIGNS (Middle)
            # ===================================
            traffic_result = self.traffic_detector.process_frame(overlay_frame)
            overlay_frame = traffic_result['annotated_frame'].copy()
            
            # ===================================
            # LAYER 4: DRIVER MONITORING (Top)
            # ===================================
            driver_result = self.driver_monitor.process_frame(overlay_frame)
            overlay_frame = driver_result['annotated_frame'].copy()
            
            return {
                'frame': overlay_frame,
                'lane': lane_result,
                'objects': object_result,
                'traffic': traffic_result,
                'driver': driver_result
            }
            
        except Exception as e:
            logger.error(f"❌ Lỗi process frame: {e}")
            return {'frame': frame, 'error': str(e)}
    
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
