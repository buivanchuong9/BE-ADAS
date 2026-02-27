"""
TENSORRT MODEL OPTIMIZER — Auto Export & Load
===============================================
Tự động export YOLO .pt → TensorRT .engine cho inference tối ưu.

Features:
  - Auto-detect TensorRT availability
  - Export .pt → .engine với FP16 (A30 support)
  - Cache .engine file → chỉ export 1 lần
  - Fallback graceful về PyTorch nếu TRT không khả dụng
  - Edge profile: YOLOv8n-TRT cho thiết bị nhỏ
  - Cloud profile: YOLOv11x-TRT cho server mạnh

Usage::

    from backend.perception.engine.tensorrt_optimizer import TensorRTOptimizer

    optimizer = TensorRTOptimizer()
    model = optimizer.load_optimized("backend/models/yolo11x.pt", imgsz=416)
    # Returns: YOLO model (TensorRT engine nếu có, PyTorch nếu không)

Author  : ADAS Research Team
Version : 1.0.0
Date    : 2026-02-27
"""

import logging
import os
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


def _check_tensorrt() -> bool:
    """Check nếu TensorRT runtime khả dụng."""
    try:
        import tensorrt  # noqa: F401
        logger.info(f"[TRT] TensorRT {tensorrt.__version__} available ✅")
        return True
    except ImportError:
        return False


def _check_torch_tensorrt() -> bool:
    """Check nếu torch-tensorrt khả dụng (PyTorch TRT integration)."""
    try:
        import torch_tensorrt  # noqa: F401
        return True
    except ImportError:
        return False


# Module-level detection
TENSORRT_AVAILABLE = _check_tensorrt()


class TensorRTOptimizer:
    """
    Quản lý export & load TensorRT engine cho YOLO models.

    Flow:
      1. Check: .engine file đã tồn tại? → load trực tiếp
      2. Nếu chưa: export .pt → .engine (FP16, dynamic batch)
      3. Nếu TRT không khả dụng: fallback về PyTorch

    Profiles:
      - 'edge': YOLOv8n, imgsz=320, FP16 → real-time trên Jetson/mobile
      - 'cloud': YOLOv11x, imgsz=416-640, FP16 → throughput cao trên A30/A100
    """

    # Default export settings per profile
    PROFILES = {
        'edge': {
            'imgsz': 320,
            'half': True,
            'simplify': True,
            'batch': 1,
            'workspace': 4,  # GB
        },
        'cloud': {
            'imgsz': 416,
            'half': True,
            'simplify': True,
            'batch': 1,
            'workspace': 8,  # GB
        },
    }

    def __init__(self, cache_dir: Optional[str] = None):
        """
        Args:
            cache_dir: Thư mục cache cho .engine files.
                       Mặc định: cùng thư mục với model .pt
        """
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.trt_available = TENSORRT_AVAILABLE

        if self.trt_available:
            logger.info("[TRT] TensorRT optimizer initialized ✅")
        else:
            logger.info("[TRT] TensorRT not available — will use PyTorch fallback")

    def get_engine_path(self, model_path: str, imgsz: int = 416) -> Path:
        """
        Trả về path tới .engine file (có thể chưa tồn tại).

        Naming: yolo11x_416_fp16.engine
        """
        pt_path = Path(model_path)
        stem = pt_path.stem  # e.g., 'yolo11x'
        engine_name = f"{stem}_{imgsz}_fp16.engine"

        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            return self.cache_dir / engine_name
        return pt_path.parent / engine_name

    def export_to_tensorrt(
        self,
        model_path: str,
        imgsz: int = 416,
        half: bool = True,
        batch: int = 1,
        workspace: int = 8,
    ) -> Optional[Path]:
        """
        Export YOLO .pt → TensorRT .engine.

        Uses Ultralytics built-in export (handles ONNX → TRT automatically).

        Args:
            model_path: Path tới .pt file
            imgsz: Input image size
            half: FP16 precision (recommended cho A30)
            batch: Batch size (1 for streaming)
            workspace: TRT workspace memory (GB)

        Returns:
            Path tới .engine file, hoặc None nếu export thất bại.
        """
        if not self.trt_available:
            logger.warning("[TRT] Cannot export — TensorRT not installed")
            return None

        engine_path = self.get_engine_path(model_path, imgsz)

        if engine_path.exists():
            size_mb = engine_path.stat().st_size / (1024 * 1024)
            logger.info(f"[TRT] Engine already cached: {engine_path} ({size_mb:.0f}MB)")
            return engine_path

        try:
            from ultralytics import YOLO

            logger.info(f"[TRT] Exporting {model_path} → TensorRT engine...")
            logger.info(f"[TRT]   imgsz={imgsz}, half={half}, batch={batch}, "
                        f"workspace={workspace}GB")

            model = YOLO(model_path)
            export_path = model.export(
                format='engine',
                imgsz=imgsz,
                half=half,
                batch=batch,
                workspace=workspace,
                simplify=True,
                device=0,       # GPU 0
            )

            if export_path and Path(export_path).exists():
                # Move to cache location if different
                exported = Path(export_path)
                if exported != engine_path:
                    import shutil
                    shutil.move(str(exported), str(engine_path))

                size_mb = engine_path.stat().st_size / (1024 * 1024)
                logger.info(f"[TRT] ✅ Export complete: {engine_path} ({size_mb:.0f}MB)")
                return engine_path
            else:
                logger.error("[TRT] Export returned invalid path")
                return None

        except Exception as e:
            logger.error(f"[TRT] Export failed: {e}", exc_info=True)
            return None

    def load_optimized(
        self,
        model_path: str,
        imgsz: int = 416,
        device: str = 'cuda',
        auto_export: bool = True,
        profile: str = 'cloud',
    ):
        """
        Load model tối ưu nhất: TRT engine > PyTorch .pt

        Args:
            model_path: Path tới .pt file gốc
            imgsz: Input image size
            device: 'cuda' hoặc 'cpu'
            auto_export: Tự động export TRT nếu chưa có
            profile: 'edge' hoặc 'cloud'

        Returns:
            YOLO model instance (TRT hoặc PyTorch)
        """
        from ultralytics import YOLO

        # 1. Check TRT engine cache
        if self.trt_available and device == 'cuda':
            engine_path = self.get_engine_path(model_path, imgsz)

            if engine_path.exists():
                try:
                    logger.info(f"[TRT] Loading cached engine: {engine_path}")
                    model = YOLO(str(engine_path))
                    logger.info("[TRT] ✅ TensorRT engine loaded — maximum performance")
                    return model
                except Exception as e:
                    logger.warning(f"[TRT] Failed to load engine: {e}, falling back to .pt")

            # 2. Auto-export
            if auto_export:
                prof = self.PROFILES.get(profile, self.PROFILES['cloud'])
                engine = self.export_to_tensorrt(
                    model_path=model_path,
                    imgsz=imgsz,
                    half=prof['half'],
                    batch=prof['batch'],
                    workspace=prof['workspace'],
                )
                if engine and engine.exists():
                    try:
                        model = YOLO(str(engine))
                        logger.info("[TRT] ✅ TensorRT engine loaded after auto-export")
                        return model
                    except Exception as e:
                        logger.warning(f"[TRT] Auto-exported engine failed to load: {e}")

        # 3. Fallback: standard PyTorch
        logger.info(f"[YOLO] Loading PyTorch model: {model_path}")
        model = YOLO(model_path)
        return model

    def benchmark(
        self,
        model_path: str,
        imgsz: int = 416,
        warmup: int = 10,
        iterations: int = 100,
    ) -> dict:
        """
        So sánh PyTorch vs TensorRT inference speed.

        Returns:
            {'pytorch_ms': float, 'tensorrt_ms': float, 'speedup': float}
        """
        import time
        import numpy as np
        import torch
        from ultralytics import YOLO

        dummy = np.random.randint(0, 255, (imgsz, imgsz, 3), dtype=np.uint8)
        results = {}

        # PyTorch
        model_pt = YOLO(model_path)
        for _ in range(warmup):
            model_pt(dummy, imgsz=imgsz, verbose=False)
        torch.cuda.synchronize()

        t0 = time.perf_counter()
        for _ in range(iterations):
            model_pt(dummy, imgsz=imgsz, verbose=False)
        torch.cuda.synchronize()
        results['pytorch_ms'] = (time.perf_counter() - t0) / iterations * 1000

        # TensorRT
        engine_path = self.get_engine_path(model_path, imgsz)
        if engine_path.exists():
            model_trt = YOLO(str(engine_path))
            for _ in range(warmup):
                model_trt(dummy, imgsz=imgsz, verbose=False)
            torch.cuda.synchronize()

            t0 = time.perf_counter()
            for _ in range(iterations):
                model_trt(dummy, imgsz=imgsz, verbose=False)
            torch.cuda.synchronize()
            results['tensorrt_ms'] = (time.perf_counter() - t0) / iterations * 1000
            results['speedup'] = results['pytorch_ms'] / results['tensorrt_ms']
        else:
            results['tensorrt_ms'] = None
            results['speedup'] = None

        logger.info(
            f"[BENCH] PyTorch: {results['pytorch_ms']:.1f}ms | "
            f"TensorRT: {results.get('tensorrt_ms', 'N/A')}ms | "
            f"Speedup: {results.get('speedup', 'N/A')}x"
        )
        return results


# ---------------------------------------------------------------------------
# Convenience: export CLI
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import argparse

    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description='Export YOLO to TensorRT')
    parser.add_argument('model', help='Path to .pt model')
    parser.add_argument('--imgsz', type=int, default=416)
    parser.add_argument('--profile', choices=['edge', 'cloud'], default='cloud')
    parser.add_argument('--benchmark', action='store_true')
    args = parser.parse_args()

    opt = TensorRTOptimizer()

    if args.benchmark:
        opt.benchmark(args.model, args.imgsz)
    else:
        opt.load_optimized(args.model, args.imgsz, profile=args.profile)
