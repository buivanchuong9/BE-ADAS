"""
STRICT OpenCV CUDA Loader — NO CPU FALLBACK.

This loader **requires** a CUDA-enabled OpenCV build that matches the
running Python version.  If CUDA is unavailable or the binding ABI does
not match, the process is terminated immediately.

Contract:  NO GPU → NO SERVICE.

Safety rules
────────────
• Runtime Python version detected dynamically.
• Only binding dirs matching runtime ``python{major}.{minor}`` are used.
• ``cv2/config-{major}.{minor}.py`` must exist (ABI proof).
• Mismatched bindings are NEVER loaded.
• After import, ``cv2.cuda.getCudaEnabledDeviceCount() > 0`` is enforced.
• A real GPU memory upload test is performed to prove the device works.
"""

import os
import sys
import time
import ctypes
import logging
import numpy as np
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Runtime Python version (determined once) ─────────────────────────────────
PY_VER = f"{sys.version_info.major}.{sys.version_info.minor}"

# ── Configuration ────────────────────────────────────────────────────────────
_OPENCV_PREFIX  = Path(os.environ.get("OPENCV_PREFIX", "/home/phonglv/opencv_cuda"))
_OPENCV_LIB_DIR = Path(os.environ.get("OPENCV_LIB_DIR", str(_OPENCV_PREFIX / "lib")))

# ONLY version-matched binding directories — no fallback to other Python versions.
_OPENCV_PY_DIRS = [
    _OPENCV_PREFIX / "lib" / f"python{PY_VER}" / "dist-packages",
    _OPENCV_PREFIX / "lib" / f"python{PY_VER}" / "site-packages",
]

# Core .so to pre-load (newest first)
_OPENCV_CORE_LIBS = [
    "libopencv_world.so.4.14",
    "libopencv_world.so.4.10",
    "libopencv_world.so.4.9",
    "libopencv_core.so.4.14",
    "libopencv_core.so.4.10",
    "libopencv_core.so.4.9",
]

_injected: bool = False


# ── Helpers ──────────────────────────────────────────────────────────────────

def _clean_cv2_modules() -> None:
    """Remove any partially-loaded cv2 from sys.modules to prevent recursion."""
    for key in list(sys.modules.keys()):
        if key == "cv2" or key.startswith("cv2."):
            del sys.modules[key]


def _find_conflicting_cv2_paths(cuda_dirs: list[str]) -> list[str]:
    """
    Find sys.path entries containing a ``cv2`` package that do NOT belong
    to our CUDA dirs (pip opencv-python / opencv-python-headless).
    """
    cuda_set = set(cuda_dirs)
    conflicts: list[str] = []
    for p in sys.path:
        if p in cuda_set:
            continue
        if (Path(p) / "cv2").is_dir():
            conflicts.append(p)
    return conflicts


def _cuda_binding_matches_runtime(py_dir: Path) -> bool:
    """
    Return True only when ``py_dir/cv2/config-{PY_VER}.py`` exists,
    proving the CUDA binding was compiled for the running Python version.
    """
    config_file = py_dir / "cv2" / f"config-{PY_VER}.py"
    return config_file.is_file()


def verify_gpu_ready() -> None:
    """
    Verify GPU memory operations actually work.

    Uploads a small test matrix to GPU via ``cv2.cuda_GpuMat``.
    Raises ``RuntimeError`` if the upload fails.
    """
    import cv2  # noqa: PLC0415

    try:
        test = cv2.cuda_GpuMat()
        test.upload(np.zeros((16, 16, 3), dtype=np.uint8))
    except Exception as exc:
        raise RuntimeError(
            f"[cv2_loader] GPU memory upload FAILED — "
            f"CUDA device unusable: {exc}"
        ) from exc

    logger.info(
        "[cv2_loader] GPU memory upload OK — "
        "cv2.cuda_GpuMat verified on device"
    )


# ── Main entry point ─────────────────────────────────────────────────────────

def inject() -> None:
    """
    Load OpenCV CUDA build and **enforce** GPU availability.

    This function will raise ``RuntimeError`` and crash the process if:
    • No ABI-compatible CUDA binding exists for this Python version
    • cv2 fails to import
    • ``cv2.cuda`` module is missing
    • No CUDA devices detected
    • GPU memory test (upload) fails

    Contract: NO GPU → NO SERVICE.
    """
    global _injected
    if _injected:
        return
    _injected = True

    t0 = time.monotonic()

    # ── 1. LD_LIBRARY_PATH (for child processes / FFmpeg) ────────────────────
    if _OPENCV_LIB_DIR.is_dir():
        existing = os.environ.get("LD_LIBRARY_PATH", "")
        lib_str = str(_OPENCV_LIB_DIR)
        if lib_str not in existing:
            os.environ["LD_LIBRARY_PATH"] = (
                lib_str + (":" + existing if existing else "")
            )

    # ── 2. Pre-load core .so with ctypes ─────────────────────────────────────
    for lib_name in _OPENCV_CORE_LIBS:
        lib_path = _OPENCV_LIB_DIR / lib_name
        if lib_path.exists():
            try:
                ctypes.CDLL(str(lib_path))
                logger.debug("[cv2_loader] Pre-loaded: %s", lib_name)
            except OSError as exc:
                logger.debug("[cv2_loader] Could not pre-load %s: %s", lib_name, exc)
            break  # only load the first available world/core lib

    # ── 3. ABI-safe binding discovery ────────────────────────────────────────
    abi_safe_dirs: list[str] = []
    for py_dir in _OPENCV_PY_DIRS:
        if not py_dir.is_dir():
            logger.debug("[cv2_loader] Candidate dir does not exist: %s", py_dir)
            continue
        if not _cuda_binding_matches_runtime(py_dir):
            raise RuntimeError(
                f"[cv2_loader] ABI mismatch — CUDA binding not built for "
                f"Python {PY_VER} (missing cv2/config-{PY_VER}.py in {py_dir}). "
                f"Rebuild OpenCV with -DPYTHON3_EXECUTABLE matching Python {PY_VER}."
            )
        abi_safe_dirs.append(str(py_dir))
        logger.debug("[cv2_loader] ABI-safe CUDA binding: %s", py_dir)

    if not abi_safe_dirs:
        raise RuntimeError(
            f"[cv2_loader] FATAL — No CUDA OpenCV binding directory found for "
            f"Python {PY_VER} under {_OPENCV_PREFIX}. "
            f"Expected one of: {[str(d) for d in _OPENCV_PY_DIRS]}. "
            f"NO GPU → NO SERVICE."
        )

    # ── 4. Insert ABI-safe dirs, remove conflicting pip cv2 paths ────────────
    for d in abi_safe_dirs:
        if d not in sys.path:
            sys.path.insert(0, d)

    conflicts = _find_conflicting_cv2_paths(abi_safe_dirs)
    for p in conflicts:
        sys.path.remove(p)
        logger.debug("[cv2_loader] Removed conflicting pip cv2 path: %s", p)

    _clean_cv2_modules()

    # ── 5. Import & enforce CUDA ─────────────────────────────────────────────
    import cv2  # noqa: PLC0415

    if not hasattr(cv2, "cuda"):
        raise RuntimeError(
            "[cv2_loader] OpenCV loaded but cv2.cuda MODULE MISSING. "
            "The build at %s was not compiled with -DWITH_CUDA=ON. "
            "NO GPU → NO SERVICE." % cv2.__file__
        )

    cuda_count = cv2.cuda.getCudaEnabledDeviceCount()
    if cuda_count <= 0:
        raise RuntimeError(
            "[cv2_loader] CUDA OpenCV loaded but NO GPU detected "
            "(getCudaEnabledDeviceCount() == 0). "
            "Check NVIDIA driver / CUDA toolkit. "
            "NO GPU → NO SERVICE."
        )

    # ── 6. GPU memory readiness test ─────────────────────────────────────────
    verify_gpu_ready()

    # Restore pip paths AFTER cv2 is loaded (won't re-import)
    for p in conflicts:
        if p not in sys.path:
            sys.path.append(p)

    elapsed = (time.monotonic() - t0) * 1000
    logger.info(
        "[cv2_loader] cv2 %s loaded — CUDA devices=%d — "
        "GPU overlay ENABLED — init %.0fms — %s",
        cv2.__version__, cuda_count, elapsed, cv2.__file__,
    )


# ── Auto-inject on import ─────────────────────────────────────────────────────
inject()
