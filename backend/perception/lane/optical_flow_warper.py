#!/usr/bin/env python3
"""
Optical Flow Lane Warping - Performance Optimization
=====================================================
Sử dụng Optical Flow để warp lane mask giữa các lần chạy LaneNet,
giảm computational cost từ 100% → ~20% mà vẫn giữ tính chính xác.

PRINCIPLE:
- LaneNet inference: EXPENSIVE (~50-100ms/frame)
- Optical Flow: CHEAP (~5ms/frame)
- Giữa 2 lần chạy LaneNet, dùng Optical Flow để "warp" lane mask cũ theo chuyển động camera

CRITICAL: Confidence Check
- Nếu optical flow confidence thấp → force re-run LaneNet
- Nếu detect scene change → force re-run LaneNet

Author: Principal AI Architect
Date: 2026-02-08
"""

import cv2
import numpy as np
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class OpticalFlowLaneWarper:
    """
    Optical Flow-based lane mask warping for performance optimization.
    
    PRODUCTION STRATEGY:
    - Run LaneNet every N frames (N=3-5)
    - Between LaneNet runs: warp previous mask using optical flow
    - Confidence gating: re-run LaneNet if flow is unstable
    
    BENEFITS:
    - 70-80% reduction in LaneNet calls
    - Smoother lane predictions (temporal consistency)
    - Real-time performance even on high-res video
    """
    
    def __init__(
        self,
        rerun_interval: int = 5,
        flow_confidence_threshold: float = 0.3,
        scene_change_threshold: float = 0.5
    ):
        """
        Initialize optical flow lane warper.
        
        Args:
            rerun_interval: Frames between full LaneNet runs (default 5)
            flow_confidence_threshold: Min flow confidence to trust warping (0-1)
            scene_change_threshold: Scene change detection threshold (higher=less sensitive)
        """
        self.rerun_interval = rerun_interval
        self.flow_confidence_threshold = flow_confidence_threshold
        self.scene_change_threshold = scene_change_threshold
        
        # State
        self.prev_gray = None
        self.prev_lane_mask = None
        self.frames_since_lanenet = 0
        
        # Optical flow parameters (Farneback)
        self.flow_params = dict(
            pyr_scale=0.5,
            levels=3,
            winsize=15,
            iterations=3,
            poly_n=5,
            poly_sigma=1.2,
            flags=0
        )
        
        # Stats
        self.total_frames = 0
        self.lanenet_runs = 0
        self.warped_frames = 0
        self.forced_reruns = 0  # Due to low confidence or scene change
        
        logger.info(
            f"OpticalFlowLaneWarper initialized: rerun_interval={rerun_interval}, "
            f"confidence_threshold={flow_confidence_threshold}"
        )
    
    def should_run_lanenet(self, frame_gray: np.ndarray) -> Tuple[bool, str]:
        """
        Decide whether to run LaneNet on this frame.
        
        Returns:
            (should_run, reason)
            
        DECISION LOGIC:
        1. First frame → YES (no previous mask)
        2. Interval reached → YES (periodic refresh)
        3. Scene change detected → YES (force rerun)
        4. Low flow confidence → YES (force rerun)
        5. Otherwise → NO (warp previous mask)
        """
        # First frame
        if self.prev_gray is None or self.prev_lane_mask is None:
            return True, "first_frame"
        
        # Periodic interval
        if self.frames_since_lanenet >= self.rerun_interval:
            return True, "interval_reached"
        
        # Compute optical flow
        flow = cv2.calcOpticalFlowFarneback(
            self.prev_gray,
            frame_gray,
            None,
            **self.flow_params
        )
        
        # Check flow confidence
        flow_magnitude = np.sqrt(flow[..., 0]**2 + flow[..., 1]**2)
        flow_mean = flow_magnitude.mean()
        
        # Scene change detection: huge flow = camera motion or scene change
        if flow_mean > self.scene_change_threshold * frame_gray.shape[0]:
            self.forced_reruns += 1
            return True, f"scene_change (flow={flow_mean:.1f})"
        
        # Low confidence: erratic flow = unstable warping
        flow_std = flow_magnitude.std()
        if flow_std > self.flow_confidence_threshold * frame_gray.shape[0]:
            self.forced_reruns += 1
            return True, f"low_confidence (std={flow_std:.1f})"
        
        # Otherwise: warp is safe
        return False, "warp_previous"
    
    def warp_lane_mask(self, frame_gray: np.ndarray) -> Optional[np.ndarray]:
        """
        Warp previous lane mask using optical flow.
        
        Args:
            frame_gray: Current grayscale frame
            
        Returns:
            Warped lane mask, or None if warping failed
        """
        if self.prev_gray is None or self.prev_lane_mask is None:
            return None
        
        try:
            # Compute optical flow
            flow = cv2.calcOpticalFlowFarneback(
                self.prev_gray,
                frame_gray,
                None,
                **self.flow_params
            )
            
            # Create remapping mesh
            h, w = frame_gray.shape
            flow_map = np.zeros((h, w, 2), dtype=np.float32)
            flow_map[..., 0] = np.arange(w) + flow[..., 0]
            flow_map[..., 1] = np.arange(h)[:, np.newaxis] + flow[..., 1]
            
            # Warp previous mask
            warped_mask = cv2.remap(
                self.prev_lane_mask,
                flow_map,
                None,
                cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=0
            )
            
            self.warped_frames += 1
            return warped_mask
            
        except Exception as e:
            logger.warning(f"Optical flow warping failed: {e}")
            return None
    
    def update(
        self,
        frame_gray: np.ndarray,
        lanenet_mask: Optional[np.ndarray] = None
    ) -> np.ndarray:
        """
        Main update function - call this every frame.
        
        Args:
            frame_gray: Current frame (grayscale)
            lanenet_mask: LaneNet output (if you ran LaneNet this frame), or None
            
        Returns:
            Lane mask for this frame (either LaneNet output or warped)
            
        USAGE:
            warper = OpticalFlowLaneWarper()
            
            for frame in video:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                
                # Check if we need to run LaneNet
                should_run, reason = warper.should_run_lanenet(gray)
                
                if should_run:
                    lane_mask = lanenet.predict(frame)  # Run expensive inference
                else:
                    lane_mask = None  # Will use warped mask
                
                # Get final mask (LaneNet or warped)
                final_mask = warper.update(gray, lane_mask)
        """
        self.total_frames += 1
        
        # If LaneNet was run this frame
        if lanenet_mask is not None:
            self.prev_gray = frame_gray.copy()
            self.prev_lane_mask = lanenet_mask.copy()
            self.frames_since_lanenet = 0
            self.lanenet_runs += 1
            return lanenet_mask
        
        # Otherwise: warp previous mask
        warped = self.warp_lane_mask(frame_gray)
        
        if warped is None:
            # Warping failed → force LaneNet next frame
            logger.warning("Warping failed, will force LaneNet next frame")
            self.frames_since_lanenet = self.rerun_interval  # Force rerun
            return self.prev_lane_mask if self.prev_lane_mask is not None else np.zeros_like(frame_gray)
        
        # Update state
        self.prev_gray = frame_gray.copy()
        self.prev_lane_mask = warped  # Use warped mask as new "previous"
        self.frames_since_lanenet += 1
        
        return warped
    
    def get_stats(self) -> dict:
        """Get performance statistics."""
        savings_percent = 0.0
        if self.total_frames > 0:
            savings_percent = ((self.total_frames - self.lanenet_runs) / self.total_frames) * 100
        
        return {
            'total_frames': self.total_frames,
            'lanenet_runs': self.lanenet_runs,
            'warped_frames': self.warped_frames,
            'forced_reruns': self.forced_reruns,
            'savings_percent': savings_percent,
            'current_interval': self.frames_since_lanenet
        }
    
    def reset(self):
        """Reset state (e.g., for new video)."""
        self.prev_gray = None
        self.prev_lane_mask = None
        self.frames_since_lanenet = 0


# ============================================
# DEMO
# ============================================
def demo_optical_flow_warping():
    """
    Demo optical flow lane warping với synthetic video.
    """
    import time
    
    print("=" * 80)
    print("OPTICAL FLOW LANE WARPING DEMO")
    print("=" * 80)
    
    # Create warper
    warper = OpticalFlowLaneWarper(
        rerun_interval=5,
        flow_confidence_threshold=0.3
    )
    
    # Simulate video processing
    num_frames = 100
    h, w = 720, 1280
    
    for frame_idx in range(num_frames):
        # Create synthetic frame (moving gradient)
        offset = frame_idx * 10
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        frame[:, :] = ((offset + np.arange(w)) % 256).astype(np.uint8)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Decide whether to run LaneNet
        should_run, reason = warper.should_run_lanenet(gray)
        
        if should_run:
            # Simulate expensive LaneNet inference
            print(f"Frame {frame_idx:3d}: 🔴 RUN LANENET ({reason})")
            time.sleep(0.05)  # Simulate 50ms inference
            
            # Create synthetic lane mask
            lane_mask = np.zeros((h, w), dtype=np.uint8)
            lane_mask[h//2:, w//3:2*w//3] = 255
            
            final_mask = warper.update(gray, lane_mask)
        else:
            # Warp previous mask (cheap)
            print(f"Frame {frame_idx:3d}: ✅ WARP ({reason})")
            time.sleep(0.005)  # Simulate 5ms warping
            
            final_mask = warper.update(gray, None)
    
    # Print stats
    stats = warper.get_stats()
    print("\n" + "=" * 80)
    print("PERFORMANCE STATS:")
    print("=" * 80)
    for key, value in stats.items():
        print(f"  {key}: {value}")
    print("=" * 80)
    print(f"\n💰 Computational Savings: {stats['savings_percent']:.1f}%")
    print(f"   (Ran LaneNet only {stats['lanenet_runs']}/{stats['total_frames']} times)")


if __name__ == '__main__':
    demo_optical_flow_warping()
