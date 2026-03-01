import subprocess
import logging
import atexit
import shutil
import glob as _glob
from typing import Optional, List, Tuple
from pathlib import Path
import signal
import os


def _resolve_binary(name: str) -> str:
    """
    Resolve an ffmpeg/ffprobe binary that works even when the worker is
    started via `nohup` and the conda PATH is NOT inherited.

    Resolution order:
      1. Explicit env override  FFMPEG_BIN / FFPROBE_BIN
      2. shutil.which           (works when PATH is set)
      3. bash -i -c 'which …'  (interactive shell → sources .bashrc/conda)
      4. Static candidate list  (/opt/anaconda, conda envs, snap, system)
      5. Raise RuntimeError with install instructions (fail fast, clear message)
    """
    # 1. Explicit env override
    env_key = f"{name.upper()}_BIN"
    if os.environ.get(env_key):
        return os.environ[env_key]

    # 2. shutil.which — honours current PATH
    found = shutil.which(name)
    if found:
        return found

    # 3. bash interactive shell — sources .bashrc / conda init so conda bin
    #    dirs are on PATH even when the parent process never ran `conda activate`
    try:
        result = subprocess.run(
            ['bash', '-i', '-c', f'which {name}'],
            capture_output=True, text=True, timeout=8,
            env={**os.environ, 'TERM': 'dumb'},   # suppress colour codes
        )
        path = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ''
        if path and os.path.isfile(path) and os.access(path, os.X_OK):
            # Inject the containing dir into PATH so child processes also work
            bin_dir = os.path.dirname(path)
            os.environ['PATH'] = bin_dir + ':' + os.environ.get('PATH', '')
            return path
    except Exception:
        pass

    # 4. Static candidate list (common conda + system locations)
    home = os.path.expanduser('~')
    candidates = [
        # Anaconda / Miniconda system-wide
        f"/opt/anaconda/bin/{name}",
        f"/opt/anaconda3/bin/{name}",
        f"/opt/miniconda/bin/{name}",
        f"/opt/miniconda3/bin/{name}",
        # Per-user
        f"{home}/anaconda3/bin/{name}",
        f"{home}/miniconda3/bin/{name}",
        f"{home}/.conda/bin/{name}",
        # Conda envs (glob all active envs)
        *_glob.glob(f"/opt/anaconda/envs/*/bin/{name}"),
        *_glob.glob(f"/opt/anaconda3/envs/*/bin/{name}"),
        *_glob.glob(f"{home}/anaconda3/envs/*/bin/{name}"),
        *_glob.glob(f"{home}/miniconda3/envs/*/bin/{name}"),
        # System
        f"/usr/bin/{name}",
        f"/usr/local/bin/{name}",
        f"/snap/bin/{name}",
        f"/snap/{name}/current/bin/{name}",
    ]
    for path in candidates:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            bin_dir = os.path.dirname(path)
            os.environ['PATH'] = bin_dir + ':' + os.environ.get('PATH', '')
            return path

    # 5. Not found anywhere — raise immediately with clear install instructions
    raise RuntimeError(
        f"\n"
        f"╔══════════════════════════════════════════════════════════╗\n"
        f"║  {name} NOT FOUND — please install it on the server:    \n"
        f"║                                                          \n"
        f"║  Option A (apt):                                         \n"
        f"║    sudo apt-get update && sudo apt-get install -y ffmpeg \n"
        f"║                                                          \n"
        f"║  Option B (conda):                                       \n"
        f"║    conda install -c conda-forge ffmpeg                   \n"
        f"║                                                          \n"
        f"║  Option C (manual path override):                        \n"
        f"║    export FFMPEG_BIN=/path/to/ffmpeg                     \n"
        f"║    export FFPROBE_BIN=/path/to/ffprobe                   \n"
        f"╚══════════════════════════════════════════════════════════╝"
    )


# ── Resolved at import time; raises clearly if binary is missing ──────────────
try:
    FFMPEG  = _resolve_binary('ffmpeg')
    FFPROBE = _resolve_binary('ffprobe')
except RuntimeError as _e:
    import sys as _sys
    print(str(_e), file=_sys.stderr, flush=True)
    # Re-raise so the worker exits immediately with a useful message instead
    # of silently failing 100 frames into a job.
    raise

_logger_init = logging.getLogger(__name__)
_logger_init.info(f"[ffmpeg_utils] ffmpeg={FFMPEG}")
_logger_init.info(f"[ffmpeg_utils] ffprobe={FFPROBE}")


def _check_nvenc() -> bool:
    """
    Thực sự encode 1 frame giả để kiểm tra h264_nvenc có hoạt động không.
    Chỉ chạy 1 lần lúc import — kết quả cache vào NVENC_AVAILABLE.

    ffmpeg -encoders | grep nvenc KHÔNG đủ — encoder có thể được compile vào
    ffmpeg nhưng OpenEncodeSession vẫn fail khi NVENC SDK không tương thích
    với driver (lỗi "unsupported device (2)").
    """
    try:
        result = subprocess.run(
            [
                FFMPEG, '-y',
                '-f', 'lavfi', '-i', 'color=black:size=32x32:rate=1',
                '-frames:v', '1',
                '-c:v', 'h264_nvenc',
                '-f', 'null', '-',
            ],
            capture_output=True,
            timeout=15,
        )
        ok = (result.returncode == 0)
        _logger_init.info(
            f"[ffmpeg_utils] NVENC probe: {'OK ✅' if ok else 'FAILED — will use libx264 CPU fallback'}"
        )
        return ok
    except Exception as exc:
        _logger_init.warning(f"[ffmpeg_utils] NVENC probe exception: {exc} — using libx264")
        return False


# Kiểm tra NVENC 1 lần khi module load
NVENC_AVAILABLE: bool = _check_nvenc()

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
        preset: str = "fast",
        profile: str = "baseline",
        level: str = "3.0"
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
            profile: H.264 profile (baseline/main/high) - baseline for max mobile compatibility
            level: H.264 level (3.0/3.1/4.0) - 3.0 for older mobile devices
        """
        # DATA TYPE SAFETY - CRITICAL!
        self.width = int(width)
        self.height = int(height)
        self.fps = float(fps)
        self.output_path = Path(output_path)
        self.crf = int(crf)
        self.preset = preset
        self.profile = profile  # baseline/main/high
        self.level = level      # 3.0/3.1/4.0

        # Tự động fallback sang CPU nếu NVENC không khả dụng trên server này
        if use_nvenc and not NVENC_AVAILABLE:
            logger.warning(
                "[FFmpeg] NVENC không khả dụng (OpenEncodeSession failed) — "
                "dùng libx264 CPU thay thế. GPU vẫn chạy YOLO + lane detection."
            )
            use_nvenc = False
        self.use_nvenc = use_nvenc
        
        self.process: Optional[subprocess.Popen] = None
        self.frames_written = 0
        
        logger.info(
            f"[FFmpeg] Initializing encoder: {self.width}x{self.height}@{self.fps}fps "
            f"→ {self.output_path.name} (NVENC={'ON' if use_nvenc else 'OFF'}, profile={self.profile}, level={self.level})"
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
        Build FFmpeg command with mobile-compatible encoding.
        
        CRITICAL REQUIREMENTS for mobile streaming:
        - yuv420p pixel format (Safari/Chrome compatible)
        - H.264 Baseline profile, Level 3.0 (universal mobile compatibility)
        - faststart flag (progressive download - allows instant playback)
        
        Without these, mobile video players will buffer/download entire file before playing.
        """
        cmd = [
            FFMPEG,
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
                '-profile:v', self.profile,  # CRITICAL: baseline for max mobile compatibility
                '-level', self.level,        # CRITICAL: 3.0 for older mobile devices
                '-pix_fmt', 'yuv420p',       # CRITICAL: Web/mobile compatible
                '-movflags', '+faststart',   # CRITICAL: Progressive download (instant streaming)
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
                '-profile:v', self.profile,  # baseline for mobile
                '-level', self.level,         # 3.0 for mobile
                '-pix_fmt', 'yuv420p',        # Web/mobile compatible
                '-movflags', '+faststart',    # Progressive download
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
        
        cmd = [FFMPEG]

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
        FFPROBE,
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


def convert_to_mobile_compatible(
    input_path: str,
    output_path: Optional[str] = None,
    use_nvenc: bool = True
) -> str:
    """
    Convert video to mobile-compatible format for instant streaming.
    
    Re-encodes with:
    - H.264 Baseline profile, Level 3.0 (max mobile compatibility)
    - yuv420p pixel format (iOS/Android compatible)
    - AAC audio codec (universal support)
    - faststart flag (progressive download - instant playback)
    
    Args:
        input_path: Input video file
        output_path: Output file (default: input_mobile.mp4)
        use_nvenc: Use GPU encoding if available
        
    Returns:
        Path to converted video
        
    Example:
        # Convert result video for mobile streaming
        mobile_path = convert_to_mobile_compatible("result.mp4")
        # → result_mobile.mp4 (can stream instantly on iOS/Android)
    """
    input_path = Path(input_path)
    
    if not input_path.exists():
        raise FileNotFoundError(f"Input video not found: {input_path}")
    
    # Default output: add _mobile suffix
    if output_path is None:
        output_path = input_path.parent / f"{input_path.stem}_mobile.mp4"
    else:
        output_path = Path(output_path)
    
    logger.info(f"[Mobile Convert] {input_path.name} → {output_path.name}")
    
    # Build FFmpeg command
    cmd = [FFMPEG, '-y', '-i', str(input_path)]
    
    # Choose encoder
    if use_nvenc and NVENC_AVAILABLE:
        cmd.extend([
            '-c:v', 'h264_nvenc',
            '-preset', 'fast',
            '-profile:v', 'baseline',     # Max mobile compatibility
            '-level', '3.0',               # Older devices support
        ])
        logger.info("[Mobile Convert] Using NVENC GPU encoding")
    else:
        cmd.extend([
            '-c:v', 'libx264',
            '-preset', 'fast',
            '-profile:v', 'baseline',
            '-level', '3.0',
        ])
        logger.info("[Mobile Convert] Using CPU encoding (slower)")
    
    # Common mobile-compatible settings
    cmd.extend([
        '-pix_fmt', 'yuv420p',         # iOS/Android compatible
        '-movflags', '+faststart',      # Progressive download (CRITICAL for streaming)
        '-acodec', 'aac',               # Universal audio codec
        '-b:a', '128k',                 # Audio bitrate
        '-ar', '44100',                 # Audio sample rate
        str(output_path)
    ])
    
    logger.info(f"[Mobile Convert] Running: {' '.join(cmd[:10])}...")
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=300  # 5 minutes max
        )
        
        if result.returncode != 0:
            stderr = result.stderr.decode('utf-8', errors='ignore')
            logger.error(f"[Mobile Convert] Failed:\n{stderr}")
            raise RuntimeError(f"FFmpeg conversion failed: {stderr[:500]}")
        
        logger.info(f"[Mobile Convert] ✓ Success: {output_path.name} ({output_path.stat().st_size / 1024 / 1024:.1f}MB)")
        return str(output_path)
        
    except subprocess.TimeoutExpired:
        logger.error("[Mobile Convert] Timeout after 5 minutes")
        raise RuntimeError("Video conversion timed out")
    except Exception as e:
        logger.error(f"[Mobile Convert] Error: {e}")
        raise

