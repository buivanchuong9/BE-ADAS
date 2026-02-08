#!/usr/bin/env python3
"""
HLS Streaming Writer - Production Grade
========================================
Ghi video output dạng HLS segments để client có thể stream ngay trong khi processing.

CRITICAL FEATURES:
- Progressive segment generation (client xem được ngay khi segment đầu tiên sẵn sàng)
- Atomic playlist updates (tránh race condition)
- Thread-safe operations
- Proper segment duration (2-4 seconds optimal cho latency vs overhead)

Author: Principal AI Architect
Date: 2026-02-08
"""

import os
import logging
import tempfile
import subprocess
from pathlib import Path
from typing import Optional, Callable
from threading import Lock
import cv2
import numpy as np

logger = logging.getLogger(__name__)


class HLSWriter:
    """
    HLS Writer for progressive video streaming.
    
    Architecture:
    - Writes video frames to temporary buffer
    - When buffer reaches segment duration → flush to .ts file
    - Update playlist.m3u8 atomically
    - Signal backend when first segment is ready
    
    PRODUCTION NOTES:
    - Segment duration: 2 seconds (balance latency vs segment count)
    - Use H.264 codec (universal browser support)
    - Use libx264 preset=veryfast (speed priority)
    - Write to SSD/RAM disk for performance
    """
    
    def __init__(
        self,
        output_dir: str,
        fps: float,
        width: int,
        height: int,
        segment_duration: float = 2.0,
        on_first_segment_ready: Optional[Callable] = None,
        on_segment_generated: Optional[Callable[[int, int]]] = None
    ):
        """
        Initialize HLS writer.
        
        Args:
            output_dir: Directory to write HLS files
            fps: Video FPS
            width: Frame width
            height: Frame height
            segment_duration: Duration per segment in seconds (default 2s)
            on_first_segment_ready: Callback when first segment is ready
            on_segment_generated: Callback(segment_idx, total_segments) on each segment
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.fps = fps
        self.width = width
        self.height = height
        self.segment_duration = segment_duration
        self.on_first_segment_ready = on_first_segment_ready
        self.on_segment_generated = on_segment_generated
        
        # Segment tracking
        self.current_segment_idx = 0
        self.frames_per_segment = int(fps * segment_duration)
        self.current_segment_frames = []
        self.total_frames_written = 0
        self.first_segment_ready = False
        
        # Thread safety
        self._lock = Lock()
        
        # Playlist path
        self.playlist_path = self.output_dir / "playlist.m3u8"
        self.segment_paths = []
        
        # Initialize empty playlist
        self._init_playlist()
        
        logger.info(
            f"HLS Writer initialized: {width}x{height} @ {fps}fps, "
            f"segment_duration={segment_duration}s ({self.frames_per_segment} frames/segment)"
        )
    
    def _init_playlist(self):
        """Initialize empty HLS playlist."""
        with open(self.playlist_path, 'w') as f:
            f.write("#EXTM3U\n")
            f.write("#EXT-X-VERSION:3\n")
            f.write(f"#EXT-X-TARGETDURATION:{int(self.segment_duration) + 1}\n")
            f.write("#EXT-X-MEDIA-SEQUENCE:0\n")
        logger.info(f"Initialized HLS playlist: {self.playlist_path}")
    
    def write_frame(self, frame: np.ndarray):
        """
        Write a single frame.
        Automatically flushes to segment when buffer is full.
        
        Args:
            frame: BGR frame from OpenCV
        """
        with self._lock:
            # Add frame to current segment buffer
            self.current_segment_frames.append(frame.copy())
            self.total_frames_written += 1
            
            # Check if segment is complete
            if len(self.current_segment_frames) >= self.frames_per_segment:
                self._flush_segment()
    
    def _flush_segment(self):
        """
        Flush current segment buffer to .ts file.
        CRITICAL: Must be called within _lock context.
        """
        if not self.current_segment_frames:
            return
        
        segment_filename = f"segment_{self.current_segment_idx:05d}.ts"
        segment_path = self.output_dir / segment_filename
        
        try:
            # Write segment using OpenCV + FFmpeg
            self._write_segment_file(segment_path, self.current_segment_frames)
            
            # Update playlist atomically
            self._update_playlist(segment_filename, self.segment_duration)
            
            # Track segment
            self.segment_paths.append(str(segment_path))
            
            # Callbacks
            if not self.first_segment_ready:
                self.first_segment_ready = True
                if self.on_first_segment_ready:
                    self.on_first_segment_ready()
                logger.info("🎉 First HLS segment ready! Client can start playback.")
            
            if self.on_segment_generated:
                # Estimate total segments (may update as we go)
                estimated_total = max(
                    self.current_segment_idx + 1,
                    int(self.total_frames_written / self.frames_per_segment) + 1
                )
                self.on_segment_generated(self.current_segment_idx, estimated_total)
            
            logger.info(
                f"✅ Segment {self.current_segment_idx} written: "
                f"{len(self.current_segment_frames)} frames → {segment_path.name}"
            )
            
            # Reset buffer
            self.current_segment_frames = []
            self.current_segment_idx += 1
            
        except Exception as e:
            logger.error(f"Failed to flush segment {self.current_segment_idx}: {e}", exc_info=True)
            raise
    
    def _write_segment_file(self, segment_path: Path, frames: list):
        """
        Write frames to a single .ts segment file using FFmpeg.
        
        WHY FFmpeg pipe instead of cv2.VideoWriter:
        - Direct TS encoding without intermediate files
        - Better codec support (libx264)
        - Faster encoding with hardware acceleration options
        
        Args:
            segment_path: Output .ts file path
            frames: List of BGR frames
        """
        # FFmpeg command for HLS segment
        cmd = [
            'ffmpeg',
            '-y',  # Overwrite
            '-f', 'rawvideo',
            '-vcodec', 'rawvideo',
            '-pix_fmt', 'bgr24',
            '-s', f'{self.width}x{self.height}',
            '-r', str(self.fps),
            '-i', '-',  # Input from pipe
            '-c:v', 'libx264',
            '-preset', 'veryfast',  # Speed priority
            '-tune', 'zerolatency',  # Low latency
            '-crf', '23',  # Quality (18-28, lower=better)
            '-pix_fmt', 'yuv420p',  # Browser compatibility
            '-movflags', '+faststart',
            '-f', 'mpegts',  # MPEG-TS format
            str(segment_path)
        ]
        
        # Run FFmpeg with pipe
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Write frames to stdin
        for frame in frames:
            process.stdin.write(frame.tobytes())
        
        # Close and wait
        process.stdin.close()
        process.wait()
        
        if process.returncode != 0:
            stderr = process.stderr.read().decode()
            raise RuntimeError(f"FFmpeg encoding failed: {stderr}")
    
    def _update_playlist(self, segment_filename: str, duration: float):
        """
        Update HLS playlist atomically.
        
        CRITICAL: Use atomic write (write to temp → rename) to prevent
        client from reading partially written playlist.
        
        Args:
            segment_filename: New segment filename to append
            duration: Segment duration in seconds
        """
        # Write to temporary file first
        temp_path = self.playlist_path.with_suffix('.m3u8.tmp')
        
        with open(temp_path, 'w') as f:
            f.write("#EXTM3U\n")
            f.write("#EXT-X-VERSION:3\n")
            f.write(f"#EXT-X-TARGETDURATION:{int(self.segment_duration) + 1}\n")
            f.write("#EXT-X-MEDIA-SEQUENCE:0\n")
            
            # Write all segments
            for seg_path in self.segment_paths:
                seg_name = Path(seg_path).name
                f.write(f"#EXTINF:{duration:.3f},\n")
                f.write(f"{seg_name}\n")
            
            # Add latest segment
            f.write(f"#EXTINF:{duration:.3f},\n")
            f.write(f"{segment_filename}\n")
            
            # Note: Don't write #EXT-X-ENDLIST until finalize()
        
        # Atomic rename
        temp_path.replace(self.playlist_path)
    
    def finalize(self):
        """
        Finalize HLS stream.
        - Flush remaining frames
        - Mark playlist as complete (#EXT-X-ENDLIST)
        """
        with self._lock:
            # Flush remaining frames as final segment
            if self.current_segment_frames:
                self._flush_segment()
            
            # Add #EXT-X-ENDLIST to playlist
            with open(self.playlist_path, 'a') as f:
                f.write("#EXT-X-ENDLIST\n")
            
            logger.info(f"HLS stream finalized: {self.current_segment_idx} segments total")
    
    def get_stats(self) -> dict:
        """Get current HLS writer stats."""
        with self._lock:
            return {
                'total_frames_written': self.total_frames_written,
                'current_segment_idx': self.current_segment_idx,
                'segments_completed': len(self.segment_paths),
                'first_segment_ready': self.first_segment_ready,
                'playlist_path': str(self.playlist_path)
            }


# ============================================
# DEMO
# ============================================
def demo_hls_writer():
    """Demo HLS writer with synthetic frames."""
    import time
    
    # Create test output directory
    output_dir = "/tmp/hls_test"
    
    # Callbacks
    def on_first_ready():
        print("🎉 First segment ready! Start playback now.")
    
    def on_segment(idx, total):
        print(f"📦 Segment {idx}/{total} generated")
    
    # Create writer
    writer = HLSWriter(
        output_dir=output_dir,
        fps=30,
        width=1280,
        height=720,
        segment_duration=2.0,
        on_first_segment_ready=on_first_ready,
        on_segment_generated=on_segment
    )
    
    # Generate 10 seconds of test video (300 frames @ 30fps)
    print("Generating test video...")
    for i in range(300):
        # Create test frame (gradient with frame number)
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        frame[:, :] = (i % 256, (i * 2) % 256, (i * 3) % 256)
        cv2.putText(frame, f"Frame {i}", (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 255, 255), 3)
        
        writer.write_frame(frame)
        time.sleep(0.01)  # Simulate processing time
    
    # Finalize
    writer.finalize()
    
    # Print stats
    stats = writer.get_stats()
    print("\n" + "=" * 60)
    print("HLS WRITER STATS:")
    for key, value in stats.items():
        print(f"  {key}: {value}")
    print("=" * 60)
    print(f"\nPlaylist: {output_dir}/playlist.m3u8")
    print(f"To play: ffplay {output_dir}/playlist.m3u8")


if __name__ == '__main__':
    demo_hls_writer()
