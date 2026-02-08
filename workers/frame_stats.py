"""
Frame-level performance statistics tracker
Production-grade observability for ADAS pipeline
"""

import time
import logging
from contextlib import contextmanager
from collections import defaultdict
from typing import Dict, List
import numpy as np

logger = logging.getLogger(__name__)


class FrameStats:
    """
    Tracks per-frame and per-stage timing statistics.
    
    Usage:
        stats = FrameStats()
        
        with stats.measure('decode'):
            frame = decoder.read()
        
        with stats.measure('inference'):
            results = model(frame)
        
        stats.report()  # Log summary
    """
    
    def __init__(self):
        self.timings: Dict[str, List[float]] = defaultdict(list)
        self.frame_count = 0
        self.total_time = 0.0
        self._start_time = None
    
    @contextmanager
    def measure(self, stage: str):
        """Context manager to measure elapsed time for a stage."""
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            self.timings[stage].append(elapsed_ms)
    
    def begin_frame(self):
        """Mark start of frame processing."""
        self._start_time = time.perf_counter()
    
    def end_frame(self):
        """Mark end of frame processing."""
        if self._start_time is not None:
            elapsed_ms = (time.perf_counter() - self._start_time) * 1000.0
            self.timings['total_frame'].append(elapsed_ms)
            self.total_time += elapsed_ms / 1000.0
            self.frame_count += 1
            self._start_time = None
    
    def report(self):
        """Log comprehensive statistics summary."""
        if not self.timings:
            logger.warning("No timing data collected")
            return
        
        logger.info("=" * 80)
        logger.info("FRAME PROCESSING STATISTICS")
        logger.info("=" * 80)
        
        # Per-stage breakdown
        logger.info("\nPer-Stage Timing (milliseconds):")
        logger.info(f"{'Stage':<20} {'Count':>8} {'P50':>8} {'P95':>8} {'P99':>8} {'Mean':>8} {'Total':>10}")
        logger.info("-" * 80)
        
        for stage, times in sorted(self.timings.items()):
            if not times:
                continue
            
            times_arr = np.array(times)
            p50 = np.percentile(times_arr, 50)
            p95 = np.percentile(times_arr, 95)
            p99 = np.percentile(times_arr, 99)
            mean = np.mean(times_arr)
            total = np.sum(times_arr)
            
            logger.info(
                f"{stage:<20} {len(times):>8} "
                f"{p50:>8.2f} {p95:>8.2f} {p99:>8.2f} "
                f"{mean:>8.2f} {total:>10.1f}"
            )
        
        # Overall metrics
        if 'total_frame' in self.timings:
            frame_times = np.array(self.timings['total_frame'])
            avg_fps = 1000.0 / np.mean(frame_times) if np.mean(frame_times) > 0 else 0
            
            logger.info("\n" + "-" * 80)
            logger.info(f"Total Frames Processed:  {self.frame_count}")
            logger.info(f"Total Processing Time:   {self.total_time:.2f}s")
            logger.info(f"Average FPS:             {avg_fps:.2f}")
            logger.info(f"Speedup Factor:          {(self.frame_count / self.total_time) / 30.0:.2f}x (vs 30fps)")
        
        logger.info("=" * 80)
    
    def get_summary(self) -> Dict:
        """Return statistics as dictionary (for metrics export)."""
        summary = {
            'frame_count': self.frame_count,
            'total_time_seconds': self.total_time,
            'stages': {}
        }
        
        for stage, times in self.timings.items():
            if not times:
                continue
            
            times_arr = np.array(times)
            summary['stages'][stage] = {
                'count': len(times),
                'p50_ms': float(np.percentile(times_arr, 50)),
                'p95_ms': float(np.percentile(times_arr, 95)),
                'p99_ms': float(np.percentile(times_arr, 99)),
                'mean_ms': float(np.mean(times_arr)),
                'total_ms': float(np.sum(times_arr))
            }
        
        return summary
