"""
Voice Alert System
Text-to-Speech cho ADAS warnings
"""
import pyttsx3
import os
from pathlib import Path
from datetime import datetime
from typing import Optional
import threading


class VoiceAlertSystem:
    """
    Voice Alert System using pyttsx3 (offline TTS)
    """
    
    def __init__(self, output_dir: str = "logs/alerts"):
        """
        Args:
            output_dir: Directory to save alert audio files
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize TTS engine
        try:
            self.engine = pyttsx3.init()
            
            # Configure voice
            voices = self.engine.getProperty('voices')
            # Try to use Vietnamese voice if available, else default
            self.engine.setProperty('voice', voices[0].id)
            
            # Set speech rate (slower for clarity)
            self.engine.setProperty('rate', 150)  # Default is 200
            
            # Set volume
            self.engine.setProperty('volume', 1.0)
            
            self.available = True
            print("✅ Voice Alert System initialized")
            
        except Exception as e:
            print(f"⚠️ Warning: TTS engine not available: {e}")
            self.available = False
    
    def create_alert(
        self,
        message: str,
        severity: str = "high",
        save_audio: bool = True
    ) -> Optional[str]:
        """
        Create voice alert
        
        Args:
            message: Alert message to speak
            severity: critical, high, medium, low
            save_audio: Whether to save audio file
        
        Returns:
            Path to audio file if saved, else None
        """
        if not self.available:
            print(f"⚠️ TTS not available. Alert: {message}")
            return None
        
        try:
            # Clean message for TTS (remove emojis)
            clean_message = self._clean_message(message)
            
            audio_path = None
            
            if save_audio:
                # Generate filename
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                filename = f"alert_{severity}_{timestamp}.wav"
                audio_path = str(self.output_dir / filename)
                
                # Save to file
                self.engine.save_to_file(clean_message, audio_path)
                self.engine.runAndWait()
                
                print(f"🔊 Alert audio saved: {audio_path}")
            else:
                # Just speak (no file)
                self.engine.say(clean_message)
                self.engine.runAndWait()
            
            return audio_path
            
        except Exception as e:
            print(f"❌ Error creating alert: {e}")
            return None
    
    def create_alert_async(
        self,
        message: str,
        severity: str = "high",
        save_audio: bool = True
    ) -> Optional[str]:
        """
        Create alert in background thread (non-blocking)
        """
        audio_path = None
        
        def _create():
            nonlocal audio_path
            audio_path = self.create_alert(message, severity, save_audio)
        
        thread = threading.Thread(target=_create, daemon=True)
        thread.start()
        
        # Wait a bit for file to be created
        thread.join(timeout=2.0)
        
        return audio_path
    
    def _clean_message(self, message: str) -> str:
        """
        Clean message for TTS (remove emojis, special chars)
        """
        # Remove common emojis
        emojis = ['⚠️', '⚡', '✓', '🚗', '🚙', '🚦', '⚠', '❌', '✅']
        for emoji in emojis:
            message = message.replace(emoji, '')
        
        # Clean up spaces
        message = ' '.join(message.split())
        
        return message.strip()
    
    def create_collision_alert(self, distance: float, ttc: float) -> Optional[str]:
        """
        Create specific collision warning alert
        """
        if ttc < 1.0:
            message = f"Nguy hiểm! Va chạm sau {ttc:.1f} giây! Phanh gấp!"
        elif ttc < 3.0:
            message = f"Cảnh báo! Xe phía trước {distance:.0f} mét. Giảm tốc độ!"
        else:
            message = f"Chú ý xe phía trước"
        
        severity = "critical" if ttc < 1.0 else "high"
        return self.create_alert_async(message, severity, save_audio=True)
    
    def create_lane_departure_alert(self) -> Optional[str]:
        """
        Create lane departure warning
        """
        message = "Cảnh báo! Xe đang lệch làn đường!"
        return self.create_alert_async(message, severity="medium", save_audio=True)
    
    def test_voice(self):
        """
        Test TTS system
        """
        test_messages = [
            "Hệ thống ADAS đã sẵn sàng",
            "Cảnh báo! Xe phía trước đang tiến gần",
            "Nguy hiểm! Phanh gấp!"
        ]
        
        for msg in test_messages:
            print(f"Testing: {msg}")
            self.create_alert(msg, save_audio=False)
