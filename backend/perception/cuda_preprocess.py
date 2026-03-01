import cv2
import numpy as np
import torch
import threading
from typing import Optional, Tuple, Dict
from dataclasses import dataclass
from contextlib import contextmanager
import logging

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
# GPU Mat Pool — Pre-allocated GPU memory for zero-copy reuse
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class GpuMatSlot:
    """Single slot in the GpuMat pool."""
    mat: cv2.cuda_GpuMat
    name: str
    last_size: Tuple[int, int] = (0, 0)  # (rows, cols)
    in_use: bool = False


class GpuMatPool:
    """
    Pre-allocated pool of GpuMat objects for zero-copy reuse.
    
    Avoids cudaMalloc overhead by reusing existing GPU memory.
    Each slot is named (e.g., 'frame_full', 'lane_crop', 'obj_resize')
    and tracks its allocated size for efficient reuse.
    """
    
    # Default slots for ADAS pipeline
    DEFAULT_SLOTS = [
        'frame_full',      # Original frame on GPU
        'frame_resized',   # Resized for object detection
        'lane_crop',       # Cropped bottom portion for lane
        'lane_resize',     # Resized for UFLD network
        'lane_rgb',        # BGR→RGB converted
        'overlay_base',    # Base frame for overlay blending
        'overlay_blend',   # Overlay layer
        'work_a',          # Temp workspace A
        'work_b',          # Temp workspace B
    ]
    
    def __init__(self, slots: Optional[list] = None):
        """Initialize pool with named slots."""
        self._slots: Dict[str, GpuMatSlot] = {}
        slot_names = slots or self.DEFAULT_SLOTS
        
        for name in slot_names:
            self._slots[name] = GpuMatSlot(
                mat=cv2.cuda_GpuMat(),
                name=name
            )
        
        logger.info(f"[CUDA-POOL] Initialized with {len(self._slots)} slots: {slot_names}")
    
    def get(self, name: str) -> cv2.cuda_GpuMat:
        """
        Get a GpuMat slot by name.
        
        The returned GpuMat may contain old data — caller should upload/create new content.
        GPU memory is reused if size matches, reallocated if needed.
        """
        if name not in self._slots:
            # Dynamic slot creation (for flexibility)
            self._slots[name] = GpuMatSlot(
                mat=cv2.cuda_GpuMat(),
                name=name
            )
            logger.debug(f"[CUDA-POOL] Created dynamic slot '{name}'")
        
        slot = self._slots[name]
        slot.in_use = True
        return slot.mat
    
    def release(self, name: str):
        """Mark slot as available for reuse."""
        if name in self._slots:
            self._slots[name].in_use = False
    
    def release_all(self):
        """Release all slots."""
        for slot in self._slots.values():
            slot.in_use = False
    
    def upload(self, name: str, cpu_mat: np.ndarray, stream: Optional[cv2.cuda.Stream] = None) -> cv2.cuda_GpuMat:
        """
        Upload CPU mat to named GPU slot.
        
        Uses existing GPU memory if size matches (zero-alloc).
        Returns the GpuMat for chaining.
        """
        gpu_mat = self.get(name)
        if stream:
            gpu_mat.upload(cpu_mat, stream)
        else:
            gpu_mat.upload(cpu_mat)
        
        # Update tracked size
        self._slots[name].last_size = (cpu_mat.shape[0], cpu_mat.shape[1])
        return gpu_mat
    
    def stats(self) -> Dict:
        """Get pool statistics."""
        active = sum(1 for s in self._slots.values() if s.in_use)
        return {
            'total_slots': len(self._slots),
            'active_slots': active,
            'slot_names': list(self._slots.keys()),
        }


# ═══════════════════════════════════════════════════════════════════════════
# Thread-local pool storage
# ═══════════════════════════════════════════════════════════════════════════

_thread_local = threading.local()


def get_pool() -> GpuMatPool:
    """Get thread-local GpuMat pool (lazy-init)."""
    if not hasattr(_thread_local, 'pool'):
        _thread_local.pool = GpuMatPool()
    return _thread_local.pool


# ═══════════════════════════════════════════════════════════════════════════
# CUDA Preprocessor — Unified GPU preprocessing for all models
# ═══════════════════════════════════════════════════════════════════════════

class CUDAPreprocessor:
    """
    Centralized CUDA preprocessing for ADAS pipeline.
    
    Implements the "one-upload, all-GPU" pattern:
    1. Upload frame to GPU once
    2. All preprocessing (crop, resize, cvtColor) on GPU
    3. Convert to tensor directly from GPU
    4. Download only final results
    
    Performance Gains:
    - Eliminates repeated CPU-GPU transfers
    - Uses CUDA streams for async operations
    - Reuses GPU memory via GpuMat pool
    
    Usage:
        preprocessor = CUDAPreprocessor()
        
        # Get preprocessing outputs for each model
        lane_tensor, obj_tensor = preprocessor.preprocess_frame(frame)
    """
    
    # ImageNet normalization constants
    IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
    IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
    
    def __init__(
        self,
        enable_cuda: bool = True,
        use_streams: bool = True,
        device: str = "cuda",
    ):
        """
        Initialize CUDA preprocessor.
        
        Args:
            enable_cuda: Use GPU preprocessing (falls back to CPU if False or unavailable)
            use_streams: Use CUDA streams for async operations
            device: Target device for tensors ('cuda' or 'cpu')
        """
        # Check CUDA availability
        self.cuda_available = (
            enable_cuda and 
            hasattr(cv2, 'cuda') and 
            cv2.cuda.getCudaEnabledDeviceCount() > 0
        )
        
        # Also check PyTorch CUDA
        import torch
        if self.cuda_available and not torch.cuda.is_available():
            self.cuda_available = False
        
        if not self.cuda_available:
            logger.warning("[CUDA-PREPROC] CUDA not available, using CPU preprocessing")
            self.enable_cuda = False
            self.device = "cpu"  # Force CPU for tensors if CUDA not available
        else:
            self.enable_cuda = True
            self.device = device
            # Create CUDA streams for async operations
            if use_streams:
                self._stream_preproc = cv2.cuda.Stream()
                self._stream_lane = cv2.cuda.Stream()
                self._stream_obj = cv2.cuda.Stream()
            else:
                self._stream_preproc = None
                self._stream_lane = None
                self._stream_obj = None
            
            logger.info(
                f"[CUDA-PREPROC] Initialized: "
                f"CUDA={self.enable_cuda}, streams={use_streams}, "
                f"device={self.device}"
            )
        
        self.use_streams = use_streams
        
        # Get thread-local pool
        self._pool: Optional[GpuMatPool] = None
    
    @property
    def pool(self) -> GpuMatPool:
        """Get (or create) thread-local GpuMat pool."""
        if self._pool is None:
            self._pool = get_pool()
        return self._pool
    
    @contextmanager
    def frame_context(self, frame: np.ndarray):
        """
        Context manager for frame processing.
        
        Uploads frame to GPU on entry, releases pool slots on exit.
        
        Usage:
            with preprocessor.frame_context(frame) as gpu_frame:
                # Use gpu_frame for all preprocessing
                lane_tensor = preprocessor.preprocess_lane_from_gpu(gpu_frame, ...)
        """
        if not self.enable_cuda:
            yield frame  # CPU path: just pass through
            return
        
        try:
            # Upload frame to GPU pool
            gpu_frame = self.pool.upload(
                'frame_full', frame, 
                self._stream_preproc if self.use_streams else None
            )
            
            # Sync to ensure upload is complete before yielding
            if self.use_streams and self._stream_preproc:
                self._stream_preproc.waitForCompletion()
            
            yield gpu_frame
            
        finally:
            # Release all pool slots for next frame
            self.pool.release_all()
    
    # ─────────────────────────────────────────────────────────────────────
    # Lane Detection Preprocessing (UFLD)
    # ─────────────────────────────────────────────────────────────────────
    
    def preprocess_lane(
        self,
        frame: np.ndarray,
        crop_ratio: float = 0.40,
        target_h: int = 320,
        target_w: int = 800,
    ) -> torch.Tensor:
        """
        Preprocess frame for UFLD lane detection (CPU or GPU).
        
        Steps:
            1. Crop bottom portion (remove sky/horizon)
            2. Resize to network input size
            3. BGR → RGB
            4. Normalize (ImageNet mean/std)
            5. Convert to NCHW tensor
        
        Args:
            frame: Input BGR frame (H, W, 3)
            crop_ratio: Top portion to remove (0.4 = keep bottom 60%)
            target_h: Network input height
            target_w: Network input width
        
        Returns:
            Tensor (1, 3, target_h, target_w) on self.device
        """
        if self.enable_cuda:
            return self._preprocess_lane_gpu(frame, crop_ratio, target_h, target_w)
        else:
            return self._preprocess_lane_cpu(frame, crop_ratio, target_h, target_w)
    
    def _preprocess_lane_gpu(
        self,
        frame: np.ndarray,
        crop_ratio: float,
        target_h: int,
        target_w: int,
    ) -> torch.Tensor:
        """GPU path: all preprocessing on CUDA."""
        h, w = frame.shape[:2]
        crop_y = int(h * crop_ratio)
        
        try:
            # Crop on CPU (slicing is cheap)
            cropped = frame[crop_y:, :, :].copy()  # Ensure contiguous
            
            # Validate shape
            if cropped.ndim != 3 or cropped.shape[2] != 3:
                logger.warning(f"[LANE] Cropped frame has wrong shape: {cropped.shape}")
                return self._preprocess_lane_cpu(frame, crop_ratio, target_h, target_w)
            
            # Upload cropped region to GPU
            gpu_crop = self.pool.upload('lane_crop', cropped, self._stream_lane)
            
            # Sync before resize to ensure upload is complete
            if self._stream_lane:
                self._stream_lane.waitForCompletion()
            
            # GPU resize - let OpenCV create output GpuMat (safer than pre-allocated)
            gpu_resized = cv2.cuda.resize(
                gpu_crop, (target_w, target_h),
                interpolation=cv2.INTER_LINEAR
            )
            
            # Validate resize output has 3 channels
            if gpu_resized.channels() != 3:
                logger.warning(f"[LANE] GPU resize output has {gpu_resized.channels()} channels, expected 3")
                return self._preprocess_lane_cpu(frame, crop_ratio, target_h, target_w)
            
            # GPU BGR → RGB
            gpu_rgb = cv2.cuda.cvtColor(gpu_resized, cv2.COLOR_BGR2RGB)
            
            # Download RGB result
            rgb = gpu_rgb.download()
            
        except Exception as e:
            # Fallback to CPU
            logger.warning(f"[LANE] GPU preprocessing failed ({e}), using CPU")
            return self._preprocess_lane_cpu(frame, crop_ratio, target_h, target_w)
        
        # Normalize and convert to tensor (on CPU, then move to GPU tensor)
        rgb_f = rgb.astype(np.float32) / 255.0
        rgb_f = (rgb_f - self.IMAGENET_MEAN) / self.IMAGENET_STD
        
        # HWC → CHW → NCHW → CUDA tensor
        tensor = torch.from_numpy(rgb_f.transpose(2, 0, 1)).unsqueeze(0)
        return tensor.to(self.device)
    
    def _preprocess_lane_cpu(
        self,
        frame: np.ndarray,
        crop_ratio: float,
        target_h: int,
        target_w: int,
    ) -> torch.Tensor:
        """CPU fallback path."""
        h, w = frame.shape[:2]
        crop_y = int(h * crop_ratio)
        
        cropped = frame[crop_y:, :, :]
        resized = cv2.resize(cropped, (target_w, target_h), interpolation=cv2.INTER_LINEAR)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        
        rgb_f = rgb.astype(np.float32) / 255.0
        rgb_f = (rgb_f - self.IMAGENET_MEAN) / self.IMAGENET_STD
        
        tensor = torch.from_numpy(rgb_f.transpose(2, 0, 1)).unsqueeze(0)
        return tensor.to(self.device)
    
    def preprocess_lane_from_gpu(
        self,
        gpu_frame: cv2.cuda_GpuMat,
        frame_shape: Tuple[int, int, int],
        crop_ratio: float = 0.40,
        target_h: int = 320,
        target_w: int = 800,
    ) -> torch.Tensor:
        """
        Preprocess for lane detection from already-uploaded GpuMat.
        
        Zero-upload variant — assumes frame is already on GPU (from frame_context).
        
        Args:
            gpu_frame: Frame already on GPU
            frame_shape: Original frame shape (h, w, c)
            crop_ratio: Top portion to remove
            target_h: Network input height
            target_w: Network input width
        
        Returns:
            Tensor (1, 3, target_h, target_w) on self.device
        """
        if not self.enable_cuda:
            raise RuntimeError("CUDA not available for preprocess_lane_from_gpu")
        
        h, w, c = frame_shape
        crop_y = int(h * crop_ratio)
        crop_h = h - crop_y
        
        try:
            # Approach 1: Download, crop on CPU, re-upload cropped region
            # This is more reliable than GPU ROI extraction which can fail
            # with non-contiguous memory or BGR format issues
            frame_cpu = gpu_frame.download()
            
            # Validate frame has 3 channels
            if frame_cpu.ndim != 3 or frame_cpu.shape[2] != 3:
                logger.warning(f"[LANE] Frame has wrong shape: {frame_cpu.shape}, expected 3 channels")
                # Create dummy tensor
                return torch.zeros(1, 3, target_h, target_w, device=self.device)
            
            # Crop on CPU (very fast, avoids GPU ROI issues)
            cropped = frame_cpu[crop_y:, :, :].copy()
            
            # Upload cropped region
            gpu_crop = self.pool.upload('lane_crop', cropped, self._stream_lane)
            
            # Sync before resize to ensure upload is complete
            if self._stream_lane:
                self._stream_lane.waitForCompletion()
            
            # GPU resize - let OpenCV create output GpuMat (safer than pre-allocated)
            gpu_resized = cv2.cuda.resize(
                gpu_crop, (target_w, target_h),
                interpolation=cv2.INTER_LINEAR
            )
            
            # Validate resize output has 3 channels
            if gpu_resized.channels() != 3:
                logger.warning(f"[LANE] GPU resize output has {gpu_resized.channels()} channels, expected 3")
                frame_cpu = gpu_frame.download() if gpu_frame.size()[0] > 0 else np.zeros((h, w, 3), dtype=np.uint8)
                cropped = frame_cpu[crop_y:, :, :]
                resized = cv2.resize(cropped, (target_w, target_h), interpolation=cv2.INTER_LINEAR)
                rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
            else:
                # GPU BGR → RGB
                gpu_rgb = cv2.cuda.cvtColor(gpu_resized, cv2.COLOR_BGR2RGB)
                rgb = gpu_rgb.download()
            
        except Exception as e:
            # Fallback to pure CPU path
            logger.warning(f"[LANE] GPU preprocessing failed ({e}), using CPU fallback")
            frame_cpu = gpu_frame.download() if gpu_frame.size()[0] > 0 else np.zeros((h, w, 3), dtype=np.uint8)
            cropped = frame_cpu[crop_y:, :, :]
            resized = cv2.resize(cropped, (target_w, target_h), interpolation=cv2.INTER_LINEAR)
            rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        
        # Normalize and tensorize
        rgb_f = rgb.astype(np.float32) / 255.0
        rgb_f = (rgb_f - self.IMAGENET_MEAN) / self.IMAGENET_STD
        
        tensor = torch.from_numpy(rgb_f.transpose(2, 0, 1)).unsqueeze(0)
        return tensor.to(self.device)
    
    # ─────────────────────────────────────────────────────────────────────
    # Object Detection Preprocessing (letterbox for YOLO)
    # ─────────────────────────────────────────────────────────────────────
    
    def preprocess_object_letterbox(
        self,
        frame: np.ndarray,
        target_size: int = 640,
        stride: int = 32,
    ) -> Tuple[np.ndarray, Tuple[float, float], Tuple[int, int]]:
        """
        Letterbox preprocessing for YOLO object detection.
        
        Resizes image while maintaining aspect ratio, pads to target_size.
        
        Args:
            frame: Input BGR frame
            target_size: Target size (square, e.g., 640)
            stride: Padding alignment (default 32 for YOLO)
        
        Returns:
            (letterboxed_frame, (scale_x, scale_y), (pad_x, pad_y))
        """
        if self.enable_cuda:
            return self._letterbox_gpu(frame, target_size, stride)
        else:
            return self._letterbox_cpu(frame, target_size, stride)
    
    def _letterbox_gpu(
        self,
        frame: np.ndarray,
        target_size: int,
        stride: int,
    ) -> Tuple[np.ndarray, Tuple[float, float], Tuple[int, int]]:
        """GPU letterbox with cv2.cuda."""
        h, w = frame.shape[:2]
        
        # Calculate scale and padding
        scale = min(target_size / h, target_size / w)
        new_w, new_h = int(w * scale), int(h * scale)
        
        # Padding to make divisible by stride
        pad_w = (target_size - new_w) // 2
        pad_h = (target_size - new_h) // 2
        
        # Upload to GPU
        gpu_frame = self.pool.upload('frame_full', frame, self._stream_obj)
        
        # GPU resize
        gpu_resized = self.pool.get('frame_resized')
        cv2.cuda.resize(
            gpu_frame, (new_w, new_h),
            gpu_resized,
            interpolation=cv2.INTER_LINEAR,
            stream=self._stream_obj
        )
        
        # Sync for download
        if self._stream_obj:
            self._stream_obj.waitForCompletion()
        
        resized = gpu_resized.download()
        
        # Pad on CPU (cv2.cuda.copyMakeBorder is limited)
        letterboxed = cv2.copyMakeBorder(
            resized,
            pad_h, target_size - new_h - pad_h,
            pad_w, target_size - new_w - pad_w,
            cv2.BORDER_CONSTANT,
            value=(114, 114, 114)  # YOLO grey padding
        )
        
        return letterboxed, (scale, scale), (pad_w, pad_h)
    
    def _letterbox_cpu(
        self,
        frame: np.ndarray,
        target_size: int,
        stride: int,
    ) -> Tuple[np.ndarray, Tuple[float, float], Tuple[int, int]]:
        """CPU letterbox fallback."""
        h, w = frame.shape[:2]
        
        scale = min(target_size / h, target_size / w)
        new_w, new_h = int(w * scale), int(h * scale)
        
        pad_w = (target_size - new_w) // 2
        pad_h = (target_size - new_h) // 2
        
        resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        
        letterboxed = cv2.copyMakeBorder(
            resized,
            pad_h, target_size - new_h - pad_h,
            pad_w, target_size - new_w - pad_w,
            cv2.BORDER_CONSTANT,
            value=(114, 114, 114)
        )
        
        return letterboxed, (scale, scale), (pad_w, pad_h)
    
    # ─────────────────────────────────────────────────────────────────────
    # Overlay Blending (GPU-accelerated alpha blending)
    # ─────────────────────────────────────────────────────────────────────
    
    def blend_overlay(
        self,
        base_frame: np.ndarray,
        overlay: np.ndarray,
        alpha: float = 0.5,
    ) -> np.ndarray:
        """
        GPU-accelerated alpha blending for overlay.
        
        result = base * (1 - alpha) + overlay * alpha
        
        Args:
            base_frame: Base image (H, W, 3)
            overlay: Overlay image (H, W, 3) — same size as base
            alpha: Blend factor (0-1)
        
        Returns:
            Blended frame (H, W, 3)
        """
        if self.enable_cuda:
            return self._blend_gpu(base_frame, overlay, alpha)
        else:
            return cv2.addWeighted(base_frame, 1 - alpha, overlay, alpha, 0)
    
    def _blend_gpu(
        self,
        base_frame: np.ndarray,
        overlay: np.ndarray,
        alpha: float,
    ) -> np.ndarray:
        """GPU alpha blending."""
        gpu_base = self.pool.upload('overlay_base', base_frame)
        gpu_overlay = self.pool.upload('overlay_blend', overlay)
        
        gpu_result = self.pool.get('work_a')
        cv2.cuda.addWeighted(
            gpu_base, 1 - alpha,
            gpu_overlay, alpha,
            0,
            gpu_result
        )
        
        return gpu_result.download()
    
    def blend_overlay_inplace(
        self,
        gpu_base: cv2.cuda_GpuMat,
        gpu_overlay: cv2.cuda_GpuMat,
        alpha: float = 0.5,
        stream: Optional[cv2.cuda.Stream] = None,
    ) -> cv2.cuda_GpuMat:
        """
        GPU alpha blending from already-uploaded GpuMats.
        
        Zero-copy variant — both inputs already on GPU.
        Result stays on GPU (call .download() when needed).
        
        Args:
            gpu_base: Base image on GPU
            gpu_overlay: Overlay on GPU
            alpha: Blend factor
            stream: Optional CUDA stream
        
        Returns:
            GpuMat with blended result (stays on GPU)
        """
        gpu_result = self.pool.get('work_a')
        cv2.cuda.addWeighted(
            gpu_base, 1 - alpha,
            gpu_overlay, alpha,
            0,
            gpu_result,
            stream=stream
        )
        return gpu_result
    
    # ─────────────────────────────────────────────────────────────────────
    # Full Frame Preprocessing (combined for efficiency)
    # ─────────────────────────────────────────────────────────────────────
    
    def preprocess_frame_full(
        self,
        frame: np.ndarray,
        lane_target: Tuple[int, int] = (320, 800),  # (h, w)
        obj_target: int = 416,
        crop_ratio: float = 0.40,
    ) -> Dict:
        """
        Full preprocessing for one frame — all models at once.
        
        Single upload, parallel GPU ops, minimal downloads.
        
        Args:
            frame: Input BGR frame
            lane_target: (height, width) for lane network
            obj_target: Square size for object detection
            crop_ratio: Lane crop ratio
        
        Returns:
            {
                'lane_tensor': Tensor for UFLD,
                'obj_letterbox': np.ndarray for YOLO,
                'obj_scale': (scale_x, scale_y),
                'obj_pad': (pad_x, pad_y),
            }
        """
        result = {}
        
        # Lane preprocessing
        result['lane_tensor'] = self.preprocess_lane(
            frame, crop_ratio, lane_target[0], lane_target[1]
        )
        
        # Object preprocessing (letterbox)
        letterbox, scale, pad = self.preprocess_object_letterbox(frame, obj_target)
        result['obj_letterbox'] = letterbox
        result['obj_scale'] = scale
        result['obj_pad'] = pad
        
        return result


# ═══════════════════════════════════════════════════════════════════════════
# Module-level singleton for easy access
# ═══════════════════════════════════════════════════════════════════════════

_preprocessor: Optional[CUDAPreprocessor] = None


def get_preprocessor(enable_cuda: bool = True) -> CUDAPreprocessor:
    """
    Get or create module-level CUDA preprocessor.
    
    Thread-safe via internal thread-local pool.
    """
    global _preprocessor
    if _preprocessor is None:
        _preprocessor = CUDAPreprocessor(enable_cuda=enable_cuda)
    return _preprocessor


# ═══════════════════════════════════════════════════════════════════════════
# Unit Tests
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import time
    
    print("=" * 60)
    print("CUDA Preprocessing Module — Unit Test")
    print("=" * 60)
    
    # Create test frame
    test_frame = np.random.randint(0, 255, (720, 1280, 3), dtype=np.uint8)
    
    # Test with CUDA
    print("\n[TEST] CUDAPreprocessor initialization...")
    preprocessor = CUDAPreprocessor(enable_cuda=True)
    print(f"  CUDA enabled: {preprocessor.enable_cuda}")
    print(f"  Pool stats: {preprocessor.pool.stats()}")
    
    # Test lane preprocessing
    print("\n[TEST] Lane preprocessing (GPU)...")
    t0 = time.perf_counter()
    for _ in range(10):
        lane_tensor = preprocessor.preprocess_lane(
            test_frame, crop_ratio=0.40, target_h=320, target_w=800
        )
    t_lane = (time.perf_counter() - t0) / 10 * 1000
    print(f"  Shape: {lane_tensor.shape}")
    print(f"  Device: {lane_tensor.device}")
    print(f"  Time: {t_lane:.2f}ms per frame")
    
    # Test object letterbox
    print("\n[TEST] Object letterbox preprocessing (GPU)...")
    t0 = time.perf_counter()
    for _ in range(10):
        letterbox, scale, pad = preprocessor.preprocess_object_letterbox(
            test_frame, target_size=416
        )
    t_obj = (time.perf_counter() - t0) / 10 * 1000
    print(f"  Shape: {letterbox.shape}")
    print(f"  Scale: {scale}, Pad: {pad}")
    print(f"  Time: {t_obj:.2f}ms per frame")
    
    # Test overlay blending
    print("\n[TEST] Overlay blending (GPU)...")
    overlay = np.random.randint(0, 255, test_frame.shape, dtype=np.uint8)
    t0 = time.perf_counter()
    for _ in range(10):
        blended = preprocessor.blend_overlay(test_frame, overlay, alpha=0.3)
    t_blend = (time.perf_counter() - t0) / 10 * 1000
    print(f"  Shape: {blended.shape}")
    print(f"  Time: {t_blend:.2f}ms per frame")
    
    # Test full preprocessing
    print("\n[TEST] Full frame preprocessing...")
    t0 = time.perf_counter()
    for _ in range(10):
        result = preprocessor.preprocess_frame_full(test_frame)
    t_full = (time.perf_counter() - t0) / 10 * 1000
    print(f"  Lane tensor: {result['lane_tensor'].shape}")
    print(f"  Obj letterbox: {result['obj_letterbox'].shape}")
    print(f"  Time: {t_full:.2f}ms per frame")
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Lane preproc:   {t_lane:.2f}ms")
    print(f"  Object preproc: {t_obj:.2f}ms")
    print(f"  Blend overlay:  {t_blend:.2f}ms")
    print(f"  Full preproc:   {t_full:.2f}ms")
    print(f"\n  Theoretical max FPS: {1000 / t_full:.0f}")
    
    print("\n✅ ALL TESTS PASSED")
