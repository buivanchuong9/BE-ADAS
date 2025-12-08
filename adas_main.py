#!/usr/bin/env python3
"""
ADAS Main Application
Entry point để chạy hệ thống ADAS

Hỗ trợ:
- Webcam / USB Camera
- Video file (MP4, AVI, MKV)
- RTSP / IP Camera stream

Usage:
    python adas_main.py --source 0                    # Webcam
    python adas_main.py --source video.mp4            # Video file
    python adas_main.py --source rtsp://ip:port/path  # RTSP stream
    python adas_main.py --source 0 --speed 60         # With vehicle speed
"""

import cv2
import argparse
import sys
from pathlib import Path
import time
import numpy as np

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from ultralytics import YOLO
from adas import ADASController
from adas.config import MODELS_DIR, DISPLAY_WIDTH, DISPLAY_HEIGHT


class CameraInput:
    """
    Camera Input Handler
    Hỗ trợ webcam, video file, RTSP stream
    """
    
    def __init__(self, source):
        """
        Initialize camera input
        
        Args:
            source: Camera source (int for webcam, str for file/RTSP)
        """
        self.source = source
        
        # Convert to int if numeric (webcam index)
        try:
            self.source = int(source)
        except (ValueError, TypeError):
            pass
        
        # Open video capture
        self.cap = cv2.VideoCapture(self.source)
        
        if not self.cap.isOpened():
            raise ValueError(f"Cannot open video source: {source}")
        
        # Get video properties
        self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.fps = int(self.cap.get(cv2.CAP_PROP_FPS))
        
        print(f"📹 Video source: {source}")
        print(f"   Resolution: {self.width}x{self.height}")
        print(f"   FPS: {self.fps}")
    
    def read(self):
        """Read frame from camera"""
        return self.cap.read()
    
    def release(self):
        """Release camera"""
        self.cap.release()
    
    def is_opened(self):
        """Check if camera is opened"""
        return self.cap.isOpened()


def main():
    """Main application"""
    
    # Parse arguments
    parser = argparse.ArgumentParser(description="ADAS - Advanced Driver Assistance System")
    parser.add_argument(
        '--source',
        type=str,
        default='0',
        help='Video source: 0 for webcam, path for video file, rtsp://... for IP camera'
    )
    parser.add_argument(
        '--model',
        type=str,
        default='yolo11n.pt',
        help='YOLO model to use (yolo11n.pt, yolo11s.pt, yolo11m.pt)'
    )
    parser.add_argument(
        '--speed',
        type=float,
        default=0.0,
        help='Initial vehicle speed in km/h (can be changed during runtime)'
    )
    parser.add_argument(
        '--no-tsr',
        action='store_true',
        help='Disable Traffic Sign Recognition'
    )
    parser.add_argument(
        '--no-fcw',
        action='store_true',
        help='Disable Forward Collision Warning'
    )
    parser.add_argument(
        '--no-ldw',
        action='store_true',
        help='Disable Lane Departure Warning'
    )
    parser.add_argument(
        '--no-audio',
        action='store_true',
        help='Disable audio alerts'
    )
    parser.add_argument(
        '--width',
        type=int,
        default=DISPLAY_WIDTH,
        help='Display width'
    )
    parser.add_argument(
        '--height',
        type=int,
        default=DISPLAY_HEIGHT,
        help='Display height'
    )
    parser.add_argument(
        '--no-display',
        action='store_true',
        help='Run without display (headless mode)'
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("🚗 ADAS - Advanced Driver Assistance System")
    print("=" * 60)
    
    # Load YOLO model
    model_path = MODELS_DIR / args.model
    if not model_path.exists():
        print(f"⚠️  Model not found: {model_path}")
        print(f"   Using default model...")
        model_path = "yolo11n.pt"  # Will download automatically
    
    print(f"\n📦 Loading YOLO11 model: {model_path}")
    yolo_model = YOLO(str(model_path))
    print("✅ Model loaded")
    
    # Initialize camera
    print(f"\n📹 Initializing camera...")
    try:
        camera = CameraInput(args.source)
    except Exception as e:
        print(f"❌ Camera initialization failed: {e}")
        return 1
    
    # Initialize ADAS Controller
    print(f"\n🚀 Initializing ADAS Controller...")
    adas = ADASController(
        yolo_model=yolo_model,
        enable_tsr=not args.no_tsr,
        enable_fcw=not args.no_fcw,
        enable_ldw=not args.no_ldw,
        enable_audio=not args.no_audio,
        vehicle_speed=args.speed,
    )
    
    # Display settings
    display_size = (args.width, args.height)
    window_name = "ADAS - Press Q to quit, +/- to adjust speed"
    
    if not args.no_display:
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(window_name, args.width, args.height)
    
    print("\n" + "=" * 60)
    print("🎬 ADAS Started!")
    print("=" * 60)
    print("Controls:")
    print("  Q / ESC  : Quit")
    print("  +        : Increase speed (+10 km/h)")
    print("  -        : Decrease speed (-10 km/h)")
    print("  SPACE    : Pause/Resume")
    print("  R        : Reset statistics")
    print("  S        : Show statistics")
    print("=" * 60)
    
    # Main loop
    paused = False
    frame_count = 0
    
    try:
        while camera.is_opened():
            if not paused:
                # Read frame
                ret, frame = camera.read()
                
                if not ret:
                    print("End of video stream")
                    break
                
                # Resize frame if needed
                if frame.shape[1] != display_size[0] or frame.shape[0] != display_size[1]:
                    frame = cv2.resize(frame, display_size)
                
                # Process through ADAS
                output, adas_data = adas.process_frame(frame)
                
                frame_count += 1
            else:
                # Use last frame when paused
                pass
            
            # Display
            if not args.no_display:
                # Add pause indicator
                if paused:
                    cv2.putText(
                        output,
                        "PAUSED",
                        (display_size[0] // 2 - 80, 50),
                        cv2.FONT_HERSHEY_DUPLEX,
                        1.5,
                        (0, 0, 255),
                        3
                    )
                
                cv2.imshow(window_name, output)
            
            # Handle keyboard input
            key = cv2.waitKey(1) & 0xFF
            
            if key == ord('q') or key == 27:  # Q or ESC
                print("\n👋 Quitting...")
                break
            
            elif key == ord('+') or key == ord('='):  # Increase speed
                adas.set_vehicle_speed(adas.vehicle_speed + 10)
                print(f"Speed: {adas.vehicle_speed:.0f} km/h")
            
            elif key == ord('-') or key == ord('_'):  # Decrease speed
                adas.set_vehicle_speed(max(0, adas.vehicle_speed - 10))
                print(f"Speed: {adas.vehicle_speed:.0f} km/h")
            
            elif key == ord(' '):  # Pause/Resume
                paused = not paused
                print("PAUSED" if paused else "RESUMED")
            
            elif key == ord('r'):  # Reset
                adas.reset()
                print("Statistics reset")
            
            elif key == ord('s'):  # Show stats
                stats = adas.get_stats()
                print("\n" + "=" * 60)
                print("📊 ADAS Statistics")
                print("=" * 60)
                for module, module_stats in stats.items():
                    if isinstance(module_stats, dict):
                        print(f"\n{module.upper()}:")
                        for key, value in module_stats.items():
                            print(f"  {key}: {value}")
                    else:
                        print(f"{module}: {module_stats}")
                print("=" * 60)
    
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
    
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Cleanup
        print("\n🧹 Cleaning up...")
        camera.release()
        cv2.destroyAllWindows()
        adas.cleanup()
        
        # Final statistics
        stats = adas.get_stats()
        print("\n" + "=" * 60)
        print("📊 Final Statistics")
        print("=" * 60)
        print(f"Total frames processed: {stats['frames_processed']}")
        print(f"Average FPS: {stats['fps']:.1f}")
        print(f"Total runtime: {stats['runtime']:.1f}s")
        
        if 'tsr' in stats:
            print(f"\nTSR:")
            print(f"  Detections: {stats['tsr']['total_detections']}")
        
        if 'fcw' in stats:
            print(f"\nFCW:")
            print(f"  Detections: {stats['fcw']['total_detections']}")
            print(f"  Warnings: {stats['fcw']['warning_count']}")
            print(f"  Dangers: {stats['fcw']['danger_count']}")
        
        if 'ldw' in stats:
            print(f"\nLDW:")
            print(f"  Detection rate: {stats['ldw']['detection_rate']:.1%}")
            print(f"  Left departures: {stats['ldw']['left_departures']}")
            print(f"  Right departures: {stats['ldw']['right_departures']}")
        
        print("=" * 60)
        print("✅ ADAS shutdown complete")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
