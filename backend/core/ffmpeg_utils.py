"""
FFmpeg Utilities - Safe Subprocess Management
==============================================
Context manager for FFmpeg subprocess with guaranteed cleanup.

CRITICAL FEATURES:
- Auto-kill FFmpeg on exception (prevents zombie processes)
- NVENC GPU encoding with web-compatible format
- Data type safety (int() all dimensions)
- Detailed logging for debugging

Author: Senior Backend Engineer
Date: 2026-02-09
"""

import subprocess
import logging
import atexit
from typing import Optional, List, Tuple
from pathlib import Path
import signal
import os

logger = logging.getLogger(__name__)

# Global registry of active FFmpeg processes
_active_processes = []


def _cleanup_all_processes():
    """Kill all active FFmpeg processes on exit (safety net)."""
    global _active_processes
    if _active_processes:
        logger.warning(f"🧹 [CLEANUP] Killing {len(_active_processes)} zombie FFmpeg processes on exit")
        for proc in _active_processes:
            try:
                proc.kill()
                proc.wait(timeout=2)
                logger.info(f"  ✓ Killed FFmpeg PID: {proc.pid}")
            except:
                pass
        _active_processes.clear()


# Register cleanup on exit
atexit.register(_cleanup_all_processes)


class FFmpegEncoder:
    """
    Safe FFmpeg video encoder with guaranteed cleanup.
    
    Usage:
        with FFmpegEncoder(output_path, width, height, fps, use_nvenc=True) as encoder:
            for frame in frames:
                encoder.write(frame)
    
    Features:
        - Auto-kill on exception
        - NVENC GPU encoding (if available)
        - Web-compatible format (yuv420p, H.264 Main profile)
        - Progress tracking
    """
    
    def __init__(
        self,
        output_path: str,
        width: int,
        height: int,
        fps: float,
        use_nvenc: bool = True,
        crf: int = 23,
        preset: str = "fast"
    ):
        """
        Initialize FFmpeg encoder.
        
        Args:
            output_path: Output video file path
            width: Video width (MUST be int, not float)
            height: Video height (MUST be int, not float)
            fps: Frame rate (can be float)
            use_nvenc: Use NVIDIA GPU encoder (h264_nvenc)
            crf: Quality (18-28, lower=better). Only for CPU encoding
            preset: Encoding speed preset
        """
        # DATA TYPE SAFETY - CRITICAL!
        self.width = int(width)
        self.height = int(height)
        self.fps = float(fps)
        self.output_path = Path(output_path)
        self.use_nvenc = use_nvenc
        self.crf = int(crf)
        self.preset = preset
        
        self.process: Optional[subprocess.Popen] = None
        self.frames_written = 0
        
        logger.info(
            f"[FFmpeg] Initializing encoder: {self.width}x{self.height}@{self.fps}fps "
            f"→ {self.output_path.name} (NVENC={'ON' if use_nvenc else 'OFF'})"
        )
    
    def __enter__(self):
        """Start FFmpeg process."""
        self._start_process()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Cleanup FFmpeg process (GUARANTEED)."""
        self._cleanup(exc_type is not None)
        return False  # Don't suppress exceptions
    
    def _start_process(self):
        """Start FFmpeg subprocess."""
        global _active_processes
        
        # Build FFmpeg command
        cmd = self._build_command()
        
        logger.info(f"[FFmpeg] Starting encoder: {' '.join(cmd[:8])}...")
        
        try:
            self.process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=10**8  # Large buffer for stability
            )
            
            # Register for cleanup
            _active_processes.append(self.process)
            
            logger.info(f"[FFmpeg] ✓ Started PID: {self.process.pid}")
            
        except Exception as e:
            logger.error(f"[FFmpeg] ✗ Failed to start: {e}")
            raise RuntimeError(f"Cannot start FFmpeg: {e}")
    
    def _build_command(self) -> List[str]:
        """
        Build FFmpeg command with NVENC GPU encoding.
        
        CRITICAL REQUIREMENTS:
        - yuv420p pixel format (Safari/Chrome compatible)
        - H.264 Main profile (universal compatibility)
        - faststart flag (progressive download)
        """
        cmd = [
            'ffmpeg',
            '-y',  # Overwrite output
            '-f', 'rawvideo',
            '-vcodec', 'rawvideo',
            '-pix_fmt', 'bgr24',
            '-s', f'{self.width}x{self.height}',  # SAFE: int() enforced in __init__
            '-r', str(self.fps),
            '-i', '-',  # Read from stdin
        ]
        
        if self.use_nvenc:
            # NVIDIA GPU encoding (FAST)
            cmd.extend([
                '-c:v', 'h264_nvenc',
                '-preset', self.preset,  # p1-p7, or fast/medium/slow
                '-profile:v', 'main',  # CRITICAL: Safari/Chrome compatible
                '-pix_fmt', 'yuv420p',  # CRITICAL: Web compatible
                '-movflags', '+faststart',  # CRITICAL: Progressive download
                '-b:v', '5M',  # Target bitrate (adjust as needed)
                '-maxrate', '8M',
                '-bufsize', '10M',
            ])
        else:
            # CPU encoding (SLOW - fallback only)
            cmd.extend([
                '-c:v', 'libx264',
                '-preset', self.preset,
                '-crf', str(self.crf),
                '-profile:v', 'main',
                '-pix_fmt', 'yuv420p',
                '-movflags', '+faststart',
            ])
        
        cmd.append(str(self.output_path))
        
        return cmd
    
    def write(self, frame):
        """
        Write a single frame to encoder.
        
        Args:
            frame: BGR numpy array (H, W, 3)
        
        Raises:
            RuntimeError: If FFmpeg process died
        """
        if not self.process or self.process.poll() is not None:
            raise RuntimeError("FFmpeg process is not running")
        
        try:
            self.process.stdin.write(frame.tobytes())
            self.frames_written += 1
            
            # Log progress every 30 frames
            if self.frames_written % 30 == 0:
                logger.debug(f"[FFmpeg] Wrote {self.frames_written} frames")
                
        except BrokenPipeError:
            # FFmpeg crashed - read stderr
            stderr = self.process.stderr.read().decode('utf-8', errors='ignore')
            logger.error(f"[FFmpeg] Broken pipe! FFmpeg stderr:\n{stderr}")
            raise RuntimeError(f"FFmpeg crashed after {self.frames_written} frames")
    
    def _cleanup(self, had_error: bool = False):
        """
        Cleanup FFmpeg process (GUARANTEED).
        
        Args:
            had_error: Whether cleanup is due to exception
        """
        global _active_processes
        
        if not self.process:
            return
        
        try:
            # Close stdin to signal end of input
            if self.process.stdin:
                try:
                    self.process.stdin.close()
                except:
                    pass
            
            # Wait for FFmpeg to finish (with timeout)
            try:
                returncode = self.process.wait(timeout=10)
                
                if returncode == 0:
                    logger.info(
                        f"[FFmpeg] ✓ Encoding complete: {self.frames_written} frames → {self.output_path.name}"
                    )
                else:
                    stderr = self.process.stderr.read().decode('utf-8', errors='ignore')
                    logger.error(f"[FFmpeg] ✗ Exit code {returncode}:\n{stderr}")
                    
            except subprocess.TimeoutExpired:
                logger.warning(f"[FFmpeg] Timeout waiting for PID {self.process.pid}, killing...")
                self.process.kill()
                self.process.wait()
            
            # Remove from active processes
            if self.process in _active_processes:
                _active_processes.remove(self.process)
                
            logger.info(f"[CLEANUP] ✓ FFmpeg PID {self.process.pid} cleaned up")
            
        except Exception as e:
            logger.error(f"[CLEANUP] Error cleaning up FFmpeg: {e}")
            # Force kill
            try:
                self.process.kill()
            except:
                pass
        
        finally:
            self.process = None


class FFmpegDecoder:
    """
    Safe FFmpeg video decoder (for GPU decoding with NVDEC).
    
    Usage:
        with FFmpegDecoder(input_path, use_nvdec=True) as decoder:
            for frame in decoder:
                process(frame)
    
    Note: For simple cases, cv2.VideoCapture is sufficient.
          Use this only when you need GPU decoding (NVDEC).
    """
    
    def __init__(self, input_path: str, use_nvdec: bool = False):
        """
        Initialize FFmpeg decoder.
        
        Args:
            input_path: Input video file path
            use_nvdec: Use NVIDIA GPU decoder (requires NVDEC support)
        """
        self.input_path = Path(input_path)
        self.use_nvdec = use_nvdec
        self.process: Optional[subprocess.Popen] = None
        
        if not self.input_path.exists():
            raise FileNotFoundError(f"Video not found: {input_path}")
    
    def __enter__(self):
        """Start FFmpeg decoder."""
        global _active_processes
        
        cmd = ['ffmpeg']
        
        if self.use_nvdec:
            cmd.extend(['-hwaccel', 'cuda', '-hwaccel_output_format', 'cuda'])
        
        cmd.extend([
            '-i', str(self.input_path),
            '-f', 'rawvideo',
            '-pix_fmt', 'bgr24',
            '-'  # Output to stdout
        ])
        
        logger.info(f"[FFmpeg] Starting decoder: {self.input_path.name}")
        
        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=10**8
        )
        
        _active_processes.append(self.process)
        logger.info(f"[FFmpeg] ✓ Decoder started PID: {self.process.pid}")
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Cleanup decoder."""
        self._cleanup()
        return False
    
    def _cleanup(self):
        """Cleanup FFmpeg decoder process."""
        global _active_processes
        
        if self.process:
            try:
                self.process.kill()
                self.process.wait(timeout=2)
                
                if self.process in _active_processes:
                    _active_processes.remove(self.process)
                
                logger.info(f"[CLEANUP] ✓ FFmpeg decoder PID {self.process.pid} cleaned up")
            except:
                pass
            finally:
                self.process = None


def get_video_info(video_path: str) -> Tuple[int, int, float, int]:
    """
    Get video metadata using FFprobe.
    
    Args:
        video_path: Path to video file
        
    Returns:
        (width, height, fps, frame_count)
        
    Raises:
        RuntimeError: If ffprobe fails
    """
    cmd = [
        'ffprobe',
        '-v', 'error',
        '-select_streams', 'v:0',
        '-count_packets',
        '-show_entries', 'stream=width,height,r_frame_rate,nb_read_packets',
        '-of', 'csv=p=0',
        str(video_path)
    ]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            raise RuntimeError(f"ffprobe failed: {result.stderr}")
        
        # Parse output: width,height,fps_num/fps_den,frame_count
        parts = result.stdout.strip().split(',')
        
        width = int(parts[0])
        height = int(parts[1])
        
        # Parse fps (e.g., "30/1" or "30000/1001")
        fps_parts = parts[2].split('/')
        fps = float(fps_parts[0]) / float(fps_parts[1])
        
        frame_count = int(parts[3]) if len(parts) > 3 else 0
        
        return width, height, fps, frame_count
        
    except Exception as e:
        logger.error(f"Failed to get video info: {e}")
        raise RuntimeError(f"Cannot read video metadata: {e}")
