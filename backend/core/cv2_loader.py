"""
cv2_loader.py — Runtime path injection for CUDA-enabled OpenCV
===============================================================
Import THIS MODULE before any other import that uses cv2.

Problem:
    ADF / nohup background processes do NOT load ~/.bashrc, so
    LD_LIBRARY_PATH and PYTHONPATH are NOT set.
    OpenCV was built from source with CUDA and installed to a custom
    prefix, so the system Python cannot find it.

Solution (code-level, no .bashrc needed):
    1. Prepend the OpenCV Python bindings directory to sys.path
       → allows  `import cv2`  to succeed.
    2. Prepend the OpenCV shared-library directory to LD_LIBRARY_PATH
       → propagates to any child subprocesses (ffmpeg, etc.).
    3. Pre-load the core OpenCV shared libraries with ctypes so the
       dynamic linker finds them before cv2's own __import__ runs.

Usage (must be the very first import in the entrypoint):

    import backend.core.cv2_loader   # noqa: F401  ← inject paths
    import cv2                        # now finds CUDA build
    print(cv2.cuda.getCudaEnabledDeviceCount())
"""

import os
import sys
import ctypes
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────────────
# Adjust these paths if OpenCV was installed elsewhere.
# They can also be overridden via environment variables so no code change
# is needed when moving to a different server.

_OPENCV_PREFIX   = Path(os.environ.get("OPENCV_PREFIX",   "/home/phonglv/opencv_cuda"))
_OPENCV_LIB_DIR  = Path(os.environ.get("OPENCV_LIB_DIR",  str(_OPENCV_PREFIX / "lib")))
_OPENCV_PY_DIRS  = [
    # Python 3.12 (conda on this server)
    _OPENCV_PREFIX / "lib" / "python3.12" / "dist-packages",
    _OPENCV_PREFIX / "lib" / "python3.12" / "site-packages",
    # Python 3.10 (reported install path)
    _OPENCV_PREFIX / "lib" / "python3.10" / "dist-packages",
    _OPENCV_PREFIX / "lib" / "python3.10" / "site-packages",
    # Generic (cmake sometimes puts .so directly under lib/)
    _OPENCV_LIB_DIR,
]

# Core shared libraries to pre-load (order matters: world → core → …)
_OPENCV_CORE_LIBS = [
    "libopencv_world.so.4.10",
    "libopencv_world.so.4.9",
    "libopencv_world.so.4.8",
    # Fallback if no "world" build — load individually
    "libopencv_core.so.4.10",
    "libopencv_core.so.4.9",
    "libopencv_core.so.4.8",
]

_injected: bool = False   # run once guard


def inject() -> bool:
    """
    Inject OpenCV CUDA paths into the current process.
    Safe to call multiple times (no-op after first call).

    Returns True if cv2 import succeeds after injection, False otherwise.
    """
    global _injected
    if _injected:
        return True
    _injected = True

    # ── 1. LD_LIBRARY_PATH ───────────────────────────────────────────────────
    if _OPENCV_LIB_DIR.is_dir():
        existing = os.environ.get("LD_LIBRARY_PATH", "")
        lib_str  = str(_OPENCV_LIB_DIR)
        if lib_str not in existing:
            os.environ["LD_LIBRARY_PATH"] = lib_str + (":" + existing if existing else "")
        logger.debug(f"[cv2_loader] LD_LIBRARY_PATH prepended: {_OPENCV_LIB_DIR}")
    else:
        logger.warning(f"[cv2_loader] OpenCV lib dir not found: {_OPENCV_LIB_DIR}")

    # ── 2. sys.path (Python bindings) ────────────────────────────────────────
    injected_py = False
    for py_dir in _OPENCV_PY_DIRS:
        if py_dir.is_dir():
            dir_str = str(py_dir)
            if dir_str not in sys.path:
                sys.path.insert(0, dir_str)
                logger.debug(f"[cv2_loader] sys.path prepended: {py_dir}")
            injected_py = True

    if not injected_py:
        logger.warning(
            f"[cv2_loader] No OpenCV Python binding dir found under {_OPENCV_PREFIX}. "
            f"Searched: {[str(d) for d in _OPENCV_PY_DIRS]}"
        )

    # ── 3. Pre-load core shared libs with ctypes ─────────────────────────────
    # Changing LD_LIBRARY_PATH after process start does NOT affect the current
    # process's already-running linker search for NEW dlopen() calls — BUT
    # explicitly loading with ctypes.CDLL *does* work because ctypes calls
    # dlopen() directly with the full path.
    for lib_name in _OPENCV_CORE_LIBS:
        lib_path = _OPENCV_LIB_DIR / lib_name
        if lib_path.exists():
            try:
                ctypes.CDLL(str(lib_path))
                logger.debug(f"[cv2_loader] Pre-loaded: {lib_name}")
            except OSError as e:
                logger.debug(f"[cv2_loader] Could not pre-load {lib_name}: {e}")
            break   # only need the first one that exists

    # ── 4. Verify cv2 import ─────────────────────────────────────────────────
    try:
        import cv2  # noqa: PLC0415
        cuda_count = 0
        if hasattr(cv2, "cuda"):
            try:
                cuda_count = cv2.cuda.getCudaEnabledDeviceCount()
            except Exception:
                pass
        logger.info(
            f"[cv2_loader] cv2 {cv2.__version__} loaded  "
            f"CUDA devices={cuda_count}  "
            f"build={cv2.getBuildInformation().splitlines()[0].strip()}"
        )
        return True
    except ImportError as e:
        logger.warning(
            f"[cv2_loader] cv2 import still failed after path injection: {e}\n"
            f"  OPENCV_PREFIX={_OPENCV_PREFIX}\n"
            f"  LD_LIBRARY_PATH={os.environ.get('LD_LIBRARY_PATH', '(not set)')}\n"
            f"  sys.path[:5]={sys.path[:5]}"
        )
        return False


# ── Auto-inject on import ─────────────────────────────────────────────────────
# Importing this module is enough — no explicit inject() call needed.
inject()
