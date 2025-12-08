"""
ADAS Controller - Main Pipeline
Điều khiển tổng hợp hệ thống ADAS

Tích hợp tất cả module:
- TSR: Traffic Sign Recognition
- FCW: Forward Collision Warning
- LDW: Lane Departure Warning
- Speeding Alert

Xử lý real-time từ camera/video/RTSP
"""

import cv2
import numpy as np
from typing import Dict, List, Optional, Tuple
import time
from pathlib import Path
import pyttsx3
import threading

from .tsr import TrafficSignRecognizer
from .fcw import ForwardCollisionWarning
from .ldw import LaneDepartureWarning
from .config import (
    ALERT_NONE,
    ALERT_INFO,
    ALERT_WARNING,
    ALERT_DANGER,
    COLOR_GREEN,
    COLOR_YELLOW,
    COLOR_RED,
    COLOR_WHITE,
    COLOR_CYAN,
    ENABLE_AUDIO,
    SHOW_FPS,
    DISPLAY_WIDTH,
    DISPLAY_HEIGHT,
)


class ADASController:
    """
    ADAS Controller - Pipeline tổng hợp
    
    Tích hợp và điều phối tất cả các module ADAS.
    Xử lý video stream real-time và hiển thị kết quả.
    """
    
    def __init__(
        self,
        yolo_model,  # YOLO11 model instance
        enable_tsr: bool = True,
        enable_fcw: bool = True,
        enable_ldw: bool = True,
        enable_audio: bool = ENABLE_AUDIO,
        vehicle_speed: float = 0.0,  # Current vehicle speed (km/h)
    ):
        """
        Initialize ADAS Controller
        
        Args:
            yolo_model: YOLO11 model instance (shared)
            enable_tsr: Enable Traffic Sign Recognition
            enable_fcw: Enable Forward Collision Warning
            enable_ldw: Enable Lane Departure Warning
            enable_audio: Enable audio alerts
            vehicle_speed: Current vehicle speed in km/h
        """
        self.yolo_model = yolo_model
        self.enable_tsr = enable_tsr
        self.enable_fcw = enable_fcw
        self.enable_ldw = enable_ldw
        self.enable_audio = enable_audio
        self.vehicle_speed = vehicle_speed
        
        # Initialize modules
        self.tsr = TrafficSignRecognizer() if enable_tsr else None
        self.fcw = ForwardCollisionWarning(yolo_model) if enable_fcw else None
        self.ldw = LaneDepartureWarning() if enable_ldw else None
        
        # Text-to-Speech for audio alerts
        self.tts_engine = None
        self.last_alert_time = {}
        self.alert_cooldown = 3.0  # Seconds between same alerts
        
        if enable_audio:
            try:
                self.tts_engine = pyttsx3.init()
                self.tts_engine.setProperty('rate', 150)  # Speed
                self.tts_engine.setProperty('volume', 0.9)  # Volume
            except Exception as e:
                print(f"⚠️  Audio alerts disabled: {e}")
                self.enable_audio = False
        
        # Performance tracking
        self.fps = 0
        self.frame_count = 0
        self.start_time = time.time()
        
        print("🚀 ADAS Controller initialized")
        print(f"   TSR: {'✅' if enable_tsr else '❌'}")
        print(f"   FCW: {'✅' if enable_fcw else '❌'}")
        print(f"   LDW: {'✅' if enable_ldw else '❌'}")
        print(f"   Audio: {'✅' if enable_audio else '❌'}")
    
    def set_vehicle_speed(self, speed: float):
        """
        Update vehicle speed
        
        Args:
            speed: Current vehicle speed in km/h
        """
        self.vehicle_speed = speed
    
    def process_frame(
        self,
        frame: np.ndarray
    ) -> Tuple[np.ndarray, Dict]:
        """
        Process single frame through ADAS pipeline
        
        Args:
            frame: Input frame (BGR)
            
        Returns:
            Tuple of (annotated_frame, adas_data)
        """
        frame_start = time.time()
        
        # Initialize output
        output = frame.copy()
        adas_data = {
            'timestamp': time.time(),
            'vehicle_speed': self.vehicle_speed,
            'alerts': [],
        }
        
        # 1. Traffic Sign Recognition (TSR)
        if self.enable_tsr and self.tsr:
            tsr_detections = self.tsr.detect_signs(frame)
            output = self.tsr.draw_detections(output, tsr_detections)
            
            current_speed_limit = self.tsr.get_current_speed_limit()
            adas_data['speed_limit'] = current_speed_limit
            adas_data['tsr_detections'] = len(tsr_detections)
            
            # Check for speeding
            if current_speed_limit and self.vehicle_speed > current_speed_limit:
                overspeed_amount = self.vehicle_speed - current_speed_limit
                adas_data['alerts'].append({
                    'type': 'SPEEDING',
                    'level': ALERT_DANGER if overspeed_amount > 20 else ALERT_WARNING,
                    'message': f"Overspeeding: {self.vehicle_speed:.0f} km/h (Limit: {current_speed_limit} km/h)",
                })
                self._trigger_audio_alert('speeding', "Speed limit exceeded")
        
        # 2. Forward Collision Warning (FCW)
        if self.enable_fcw and self.fcw:
            fcw_detections = self.fcw.detect_vehicles(frame)
            output = self.fcw.draw_detections(output, fcw_detections)
            
            closest_vehicle = self.fcw.get_closest_vehicle()
            adas_data['fcw_detections'] = len(fcw_detections)
            adas_data['closest_vehicle'] = closest_vehicle
            
            # Check for collision risk
            if closest_vehicle:
                alert_level = closest_vehicle['alert_level']
                if alert_level == ALERT_DANGER:
                    adas_data['alerts'].append({
                        'type': 'COLLISION_DANGER',
                        'level': ALERT_DANGER,
                        'message': f"Collision warning! Vehicle {closest_vehicle['distance']:.1f}m ahead",
                    })
                    self._trigger_audio_alert('collision', "Collision warning, brake now")
                elif alert_level == ALERT_WARNING:
                    adas_data['alerts'].append({
                        'type': 'COLLISION_WARNING',
                        'level': ALERT_WARNING,
                        'message': f"Vehicle approaching: {closest_vehicle['distance']:.1f}m",
                    })
                    self._trigger_audio_alert('approaching', "Vehicle ahead, reduce speed")
        
        # 3. Lane Departure Warning (LDW)
        if self.enable_ldw and self.ldw:
            ldw_data = self.ldw.detect_lanes(frame)
            output = self.ldw.draw_lanes(output, ldw_data)
            
            adas_data['ldw_data'] = ldw_data
            
            # Check for lane departure
            if ldw_data['alert_level'] == ALERT_DANGER:
                direction = ldw_data.get('departure_direction', 'unknown')
                adas_data['alerts'].append({
                    'type': 'LANE_DEPARTURE',
                    'level': ALERT_DANGER,
                    'message': f"Lane departure detected ({direction})",
                })
                self._trigger_audio_alert('lane_departure', f"Lane departure {direction}")
        
        # 4. Draw HUD (Heads-Up Display)
        output = self._draw_hud(output, adas_data)
        
        # Update FPS
        self.frame_count += 1
        frame_time = time.time() - frame_start
        if frame_time > 0:
            self.fps = 0.9 * self.fps + 0.1 * (1.0 / frame_time)  # Smoothed FPS
        
        return output, adas_data
    
    def _draw_hud(
        self,
        frame: np.ndarray,
        adas_data: Dict
    ) -> np.ndarray:
        """
        Draw Heads-Up Display with ADAS information
        
        Args:
            frame: Input frame
            adas_data: ADAS data dictionary
            
        Returns:
            Frame with HUD overlay
        """
        output = frame.copy()
        h, w = frame.shape[:2]
        
        # Semi-transparent overlay for HUD
        overlay = output.copy()
        
        # Top-left: Speed and Speed Limit
        hud_y = 30
        
        # Vehicle Speed
        speed_text = f"Speed: {self.vehicle_speed:.0f} km/h"
        cv2.putText(
            overlay,
            speed_text,
            (20, hud_y),
            cv2.FONT_HERSHEY_DUPLEX,
            0.8,
            COLOR_WHITE,
            2
        )
        
        # Speed Limit
        if 'speed_limit' in adas_data and adas_data['speed_limit']:
            limit = adas_data['speed_limit']
            limit_color = COLOR_RED if self.vehicle_speed > limit else COLOR_GREEN
            limit_text = f"Limit: {limit} km/h"
            cv2.putText(
                overlay,
                limit_text,
                (20, hud_y + 35),
                cv2.FONT_HERSHEY_DUPLEX,
                0.8,
                limit_color,
                2
            )
        
        # Top-right: FPS and Status
        if SHOW_FPS:
            fps_text = f"FPS: {self.fps:.1f}"
            text_size, _ = cv2.getTextSize(fps_text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            cv2.putText(
                overlay,
                fps_text,
                (w - text_size[0] - 20, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                COLOR_CYAN,
                2
            )
        
        # Status indicators
        status_y = 60
        status_x = w - 200
        
        tsr_status = "TSR: ✓" if self.enable_tsr else "TSR: ✗"
        fcw_status = "FCW: ✓" if self.enable_fcw else "FCW: ✗"
        ldw_status = "LDW: ✓" if self.enable_ldw else "LDW: ✗"
        
        cv2.putText(overlay, tsr_status, (status_x, status_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLOR_GREEN, 1)
        cv2.putText(overlay, fcw_status, (status_x, status_y + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLOR_GREEN, 1)
        cv2.putText(overlay, ldw_status, (status_x, status_y + 40), cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLOR_GREEN, 1)
        
        # Alerts panel (bottom-left)
        if adas_data.get('alerts'):
            alert_y = h - 120
            cv2.rectangle(overlay, (10, alert_y - 10), (w - 10, h - 10), (0, 0, 0), -1)
            
            for i, alert in enumerate(adas_data['alerts'][:3]):  # Show max 3 alerts
                level = alert['level']
                message = alert['message']
                
                # Color based on level
                if level == ALERT_DANGER:
                    alert_color = COLOR_RED
                elif level == ALERT_WARNING:
                    alert_color = COLOR_YELLOW
                else:
                    alert_color = COLOR_WHITE
                
                cv2.putText(
                    overlay,
                    f"⚠ {message}",
                    (20, alert_y + 20 + i * 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    alert_color,
                    2
                )
        
        # Blend overlay
        output = cv2.addWeighted(output, 0.7, overlay, 0.3, 0)
        
        return output
    
    def _trigger_audio_alert(self, alert_type: str, message: str):
        """
        Trigger audio alert with cooldown
        
        Args:
            alert_type: Type of alert (for cooldown tracking)
            message: TTS message
        """
        if not self.enable_audio or not self.tts_engine:
            return
        
        current_time = time.time()
        last_time = self.last_alert_time.get(alert_type, 0)
        
        # Check cooldown
        if current_time - last_time < self.alert_cooldown:
            return
        
        # Update last alert time
        self.last_alert_time[alert_type] = current_time
        
        # Speak in background thread to avoid blocking
        def speak():
            try:
                self.tts_engine.say(message)
                self.tts_engine.runAndWait()
            except Exception as e:
                print(f"Audio alert error: {e}")
        
        thread = threading.Thread(target=speak, daemon=True)
        thread.start()
    
    def get_stats(self) -> Dict:
        """Get comprehensive ADAS statistics"""
        stats = {
            'frames_processed': self.frame_count,
            'fps': self.fps,
            'runtime': time.time() - self.start_time,
        }
        
        if self.tsr:
            stats['tsr'] = self.tsr.get_stats()
        if self.fcw:
            stats['fcw'] = self.fcw.get_stats()
        if self.ldw:
            stats['ldw'] = self.ldw.get_stats()
        
        return stats
    
    def reset(self):
        """Reset all ADAS modules"""
        if self.tsr:
            self.tsr.reset()
        if self.fcw:
            self.fcw.reset()
        if self.ldw:
            self.ldw.reset()
        
        self.frame_count = 0
        self.start_time = time.time()
        self.last_alert_time = {}
    
    def cleanup(self):
        """Cleanup resources"""
        if self.tts_engine:
            try:
                self.tts_engine.stop()
            except:
                pass
        
        print("ADAS Controller cleaned up")
