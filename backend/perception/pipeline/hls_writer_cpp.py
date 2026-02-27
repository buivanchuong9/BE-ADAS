"""
Python wrapper for HLS Encoder with fallback to FFmpeg subprocess
"""

import logging
from pathlib import Path
from typing import Optional, Callable
import numpy as np

logger = logging.getLogger(__name__)

# Try to import C++ module
try:
    import hlsenc as _hlsenc_cpp
    CPP_AVAILABLE = True
    logger.info("✅ C++ HLS encoder loaded")
except ImportError:
    CPP_AVAILABLE = False
    logger.warning("⚠️  C++ HLS encoder not available, using Python fallback")


class HLSWriter:
    """
    HLS writer with automatic C++/Python fallback.
    
    Tries to use C++ encoder (hlsenc.so) first, falls back to Python
    FFmpeg subprocess if C++ is not available.
    """
    
    def __init__(
        self,
        output_dir: str,
        width: int,
        height: int,
        fps: float,
        segment_duration: float = 2.0,
        on_first_segment_ready: Optional[Callable] = None,
        on_segment_generated: Optional[Callable] = None
    ):
        self.output_dir = Path(output_dir)
        self.width = width
        self.height = height
        self.fps = fps
        self.segment_duration = segment_duration
        
        self.on_first_segment_ready = on_first_segment_ready
        self.on_segment_generated = on_segment_generated
        
        self.frames_per_segment = int(fps * segment_duration)
        self.current_frames = []
        self.frame_count = 0
        self.segment_count = 0
        self.first_segment_ready = False
        
        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Try to use C++ encoder
        if CPP_AVAILABLE:
            try:
                self.encoder = _hlsenc_cpp.HLSEncoder(
                    str(self.output_dir),
                    width,
                    height,
                    fps,
                    segment_duration
                )
                self.backend = "cpp"
                
                # Report which encoder is active (NVENC vs CPU)
                enc_name = self.encoder.encoder_name
                if enc_name == "h264_nvenc":
                    logger.info(f"✅ Using GPU HLS encoder: {enc_name} (Fast)")
                else:
                    logger.warning(f"⚠️  Using CPU HLS encoder: {enc_name} (Slow - check GPU)")
                    
            except Exception as e:
                logger.warning(f"C++ encoder init failed: {e}, falling back to Python")
                self.encoder = None
                self.backend = "python"
        else:
            self.encoder = None
            self.backend = "python"
            
            # Import Python fallback
            from backend.perception.pipeline.hls_writer import HLSWriter as PythonHLSWriter
            self.fallback_writer = PythonHLSWriter(
                output_dir=str(self.output_dir),
                width=width,
                height=height,
                fps=fps,
                segment_duration=segment_duration,
                on_first_segment_ready=on_first_segment_ready,
                on_segment_generated=on_segment_generated
            )
    
    def write_frame(self, frame: np.ndarray):
        """Write one frame."""
        if self.backend == "cpp":
            # C++ path (FAST)
            self.encoder.encode_frame(frame, pts=self.frame_count)
            self.frame_count += 1
            
            # Check if segment was flushed
            if self.frame_count % self.frames_per_segment == 0:
                self.segment_count += 1
                
                if not self.first_segment_ready:
                    self.first_segment_ready = True
                    if self.on_first_segment_ready:
                        self.on_first_segment_ready()
                
                if self.on_segment_generated:
                    estimated_total = (self.frame_count // self.frames_per_segment) + 1
                    self.on_segment_generated(self.segment_count, estimated_total)
        
        else:
            # Python fallback (SLOW)
            self.fallback_writer.write_frame(frame)
    
    def finalize(self):
        """Finalize HLS stream."""
        if self.backend == "cpp":
            self.encoder.finalize()
            logger.info(f"HLS encoding finalized: {self.segment_count} segments (C++)")
        else:
            self.fallback_writer.finalize()
    
    def get_stats(self) -> dict:
        """Get encoding statistics."""
        if self.backend == "cpp":
            stats = self.encoder.get_stats()
            return {
                'backend': 'cpp',
                'total_frames': stats.total_frames_encoded,
                'total_segments': stats.total_segments_written,
                'frames_in_current_segment': stats.frames_in_current_segment
            }
        else:
            python_stats = self.fallback_writer.get_stats()
            python_stats['backend'] = 'python'
            return python_stats
