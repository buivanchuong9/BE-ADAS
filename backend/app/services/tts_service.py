"""
VIETNAMESE TTS (TEXT-TO-SPEECH) SERVICE
========================================
Phase 6: Vietnamese voice alerts for ADAS system.

PURPOSE:
Generate Vietnamese audio alerts for real-time driver warnings using gTTS.

FEATURES:
- Vietnamese language support (vi-VN)
- Pre-generated alert audio for low latency
- MP3 format for compatibility
- Caching mechanism for frequent alerts

SUPPORTED ALERTS:
- "Cảnh báo va chạm phía trước!" (Forward Collision Warning)
- "Cảnh báo chệch làn đường!" (Lane Departure Warning)
- "Cảnh báo tài xế buồn ngủ!" (Driver Drowsiness Warning)
- "Cảnh báo người đi bộ!" (Pedestrian Warning)
- "Giảm tốc độ!" (Slow Down)

Author: Senior ADAS Engineer
Date: 2025-12-26 (Phase 6)
"""

import os
from pathlib import Path
from typing import Dict, Optional
import logging
import hashlib

try:
    from gtts import gTTS
except ImportError:
    gTTS = None
    logging.warning("gTTS not installed. Run: pip install gTTS==2.5.3")

logger = logging.getLogger(__name__)


class VietnameseTTS:
    """
    Vietnamese Text-to-Speech service using Google TTS.
    """
    
    # Pre-defined Vietnamese alerts
    ALERT_MESSAGES = {
        'FCW': "Cảnh báo va chạm phía trước!",
        'LDW': "Cảnh báo chệch làn đường!",
        'DDW': "Cảnh báo tài xế buồn ngủ!",
        'PCW': "Cảnh báo người đi bộ!",
        'HMW': "Giữ khoảng cách an toàn!",
        'TSV': "Vượt quá tốc độ cho phép!",
        'SLOW_DOWN': "Giảm tốc độ!",
        'ATTENTION': "Chú ý lái xe!",
        'BRAKE': "Phanh gấp!"
    }
    
    def __init__(self, cache_dir: Optional[Path] = None):
        """
        Initialize Vietnamese TTS service.
        
        Args:
            cache_dir: Directory to cache generated audio files
        """
        if gTTS is None:
            logger.error("gTTS not available - TTS service disabled")
            self.enabled = False
            return
        
        self.enabled = True
        
        # Set cache directory
        if cache_dir is None:
            cache_dir = Path(__file__).parent.parent.parent / "storage" / "audio_cache"
        
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"VietnameseTTS initialized: cache_dir={self.cache_dir}")
    
    def generate_audio(
        self,
        text: str,
        output_path: Optional[Path] = None,
        use_cache: bool = True
    ) -> Optional[Path]:
        """
        Generate Vietnamese audio from text.
        
        Args:
            text: Vietnamese text to convert to speech
            output_path: Output file path (MP3). If None, uses cache
            use_cache: Whether to use cached audio if available
            
        Returns:
            Path to generated MP3 file, or None if failed
        """
        if not self.enabled:
            logger.warning("TTS service disabled - gTTS not available")
            return None
        
        try:
            # Generate cache key
            cache_key = hashlib.md5(text.encode('utf-8')).hexdigest()
            cache_file = self.cache_dir / f"{cache_key}.mp3"
            
            # Check cache
            if use_cache and cache_file.exists():
                logger.debug(f"Using cached audio: {cache_file}")
                return cache_file
            
            # Generate TTS
            tts = gTTS(text=text, lang='vi', slow=False)
            
            # Determine output path
            if output_path is None:
                output_path = cache_file
            
            # Save audio
            tts.save(str(output_path))
            logger.info(f"Generated audio: {output_path}")
            
            return output_path
            
        except Exception as e:
            logger.error(f"Failed to generate audio: {e}")
            return None
    
    def generate_alert_audio(
        self,
        alert_type: str,
        custom_text: Optional[str] = None
    ) -> Optional[Path]:
        """
        Generate audio for predefined alert type.
        
        Args:
            alert_type: Alert type (FCW, LDW, DDW, PCW, etc.)
            custom_text: Optional custom text (overrides predefined message)
            
        Returns:
            Path to audio file, or None if failed
        """
        # Get message text
        text = custom_text or self.ALERT_MESSAGES.get(alert_type)
        
        if text is None:
            logger.warning(f"Unknown alert type: {alert_type}")
            return None
        
        return self.generate_audio(text, use_cache=True)
    
    def pregenerate_all_alerts(self) -> Dict[str, Optional[Path]]:
        """
        Pre-generate audio for all predefined alerts.
        Useful during system initialization to reduce latency.
        
        Returns:
            Dict mapping alert types to audio file paths
        """
        if not self.enabled:
            return {}
        
        results = {}
        
        logger.info("Pre-generating all alert audio files...")
        
        for alert_type, message in self.ALERT_MESSAGES.items():
            audio_path = self.generate_alert_audio(alert_type)
            results[alert_type] = audio_path
            
            if audio_path:
                logger.info(f"✓ {alert_type}: {message} → {audio_path.name}")
            else:
                logger.warning(f"✗ {alert_type}: Failed")
        
        successful_count = len([p for p in results.values() if p])
        total_count = len(self.ALERT_MESSAGES)
        logger.info(f"Pre-generation complete: {successful_count}/{total_count} successful")
        
        return results
    
    def get_alert_audio_url(
        self,
        alert_type: str,
        base_url: str = "https://adas-api.aiotlab.edu.vn:52000"
    ) -> Optional[str]:
        """
        Get URL for alert audio file.
        
        Args:
            alert_type: Alert type
            base_url: Base URL for API
            
        Returns:
            URL to audio file, or None if not available
        """
        audio_path = self.generate_alert_audio(alert_type)
        
        if audio_path is None:
            return None
        
        # Generate URL relative to storage
        relative_path = audio_path.relative_to(self.cache_dir.parent)
        url = f"{base_url}/api/files/{relative_path.as_posix()}"
        
        return url
    
    def clear_cache(self) -> int:
        """
        Clear all cached audio files.
        
        Returns:
            Number of files deleted
        """
        count = 0
        
        for file_path in self.cache_dir.glob("*.mp3"):
            try:
                file_path.unlink()
                count += 1
            except Exception as e:
                logger.error(f"Failed to delete {file_path}: {e}")
        
        logger.info(f"Cleared {count} cached audio files")
        return count


# Global TTS service instance
_tts_service: Optional[VietnameseTTS] = None


def get_tts_service() -> VietnameseTTS:
    """
    Get global TTS service instance (singleton).
    
    Returns:
        VietnameseTTS instance
    """
    global _tts_service
    
    if _tts_service is None:
        _tts_service = VietnameseTTS()
        
        # Pre-generate common alerts on first initialization
        _tts_service.pregenerate_all_alerts()
    
    return _tts_service


if __name__ == "__main__":
    # Test TTS service
    logging.basicConfig(level=logging.INFO)
    
    print("Vietnamese TTS Service Test")
    print("=" * 50)
    
    tts = VietnameseTTS()
    
    if not tts.enabled:
        print("ERROR: gTTS not available")
        print("Install with: pip install gTTS==2.5.3")
        exit(1)
    
    print("\nPre-generating all alert audio...")
    results = tts.pregenerate_all_alerts()
    
    print(f"\nGenerated {len([p for p in results.values() if p])} audio files:")
    for alert_type, path in results.items():
        if path:
            size_kb = path.stat().st_size / 1024
            print(f"  {alert_type}: {tts.ALERT_MESSAGES[alert_type]}")
            print(f"    → {path} ({size_kb:.1f} KB)")
    
    print("\nTest custom message:")
    custom_audio = tts.generate_audio("Xin chào! Đây là hệ thống ADAS.")
    if custom_audio:
        print(f"  Custom audio: {custom_audio}")
    
    print("\nCache statistics:")
    print(f"  Cache directory: {tts.cache_dir}")
    print(f"  Cached files: {len(list(tts.cache_dir.glob('*.mp3')))}")
    
    print("\nAudio URLs:")
    for alert_type in ['FCW', 'LDW', 'DDW']:
        url = tts.get_alert_audio_url(alert_type)
        print(f"  {alert_type}: {url}")
