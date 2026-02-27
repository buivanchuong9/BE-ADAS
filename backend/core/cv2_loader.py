import os
import sys
import ctypes
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────────────
_OPENCV_PREFIX   = Path(os.environ.get("OPENCV_PREFIX",   "/home/phonglv/opencv_cuda"))
_OPENCV_LIB_DIR  = Path(os.environ.get("OPENCV_LIB_DIR",  str(_OPENCV_PREFIX / "lib")))

# Python version-matched binding directories (try current Python version first)
_PY_VER = f"{sys.version_info.major}.{sys.version_info.minor}"
_OPENCV_PY_DIRS  = [
    _OPENCV_PREFIX / "lib" / f"python{_PY_VER}" / "dist-packages",
    _OPENCV_PREFIX / "lib" / f"python{_PY_VER}" / "site-packages",
    _OPENCV_PREFIX / "lib" / "python3.10" / "dist-packages",
    _OPENCV_PREFIX / "lib" / "python3.10" / "site-packages",
    _OPENCV_PREFIX / "lib" / "python3",
    _OPENCV_LIB_DIR,
]

# Core shared libraries to pre-load
_OPENCV_CORE_LIBS = [
    "libopencv_world.so.4.14",
    "libopencv_world.so.4.10",
    "libopencv_world.so.4.9",
    "libopencv_core.so.4.14",
    "libopencv_core.so.4.10",
    "libopencv_core.so.4.9",
]

_injected: bool = False


def _clean_cv2_modules():
    """Remove any partially-loaded cv2 from sys.modules to prevent recursion."""
    for key in list(sys.modules.keys()):
        if key == 'cv2' or key.startswith('cv2.'):
            del sys.modules[key]


def _find_conflicting_cv2_paths(cuda_dirs: list) -> list:
    """
    Find sys.path entries that contain a cv2 package BUT are NOT our CUDA dirs.
    These are from pip (opencv-python, opencv-python-headless) and conflict.
    """
    cuda_str = {str(d) for d in cuda_dirs}
    conflicts = []
    for p in sys.path:
        if p in cuda_str:
            continue
        cv2_dir = Path(p) / 'cv2'
        if cv2_dir.is_dir():
            conflicts.append(p)
    return conflicts


def inject() -> bool:
    """
    Load OpenCV with CUDA support, handling conflicts with pip-installed
    opencv-python / opencv-python-headless.

    Strategy:
      1. Pre-load .so libs via ctypes (LD_LIBRARY_PATH doesn't work post-exec)
      2. Temporarily remove conflicting cv2 paths from sys.path
      3. Try import cv2 from CUDA build
      4. On failure: restore paths, fall back to pip cv2 (no CUDA)
    
    Safe to call multiple times.
    """
    global _injected
    if _injected:
        return True
    _injected = True

    # ── 1. LD_LIBRARY_PATH (for child processes / FFmpeg) ────────────────────
    if _OPENCV_LIB_DIR.is_dir():
        existing = os.environ.get("LD_LIBRARY_PATH", "")
        lib_str  = str(_OPENCV_LIB_DIR)
        if lib_str not in existing:
            os.environ["LD_LIBRARY_PATH"] = lib_str + (":" + existing if existing else "")

    # ── 2. Pre-load core .so with ctypes ─────────────────────────────────────
    for lib_name in _OPENCV_CORE_LIBS:
        lib_path = _OPENCV_LIB_DIR / lib_name
        if lib_path.exists():
            try:
                ctypes.CDLL(str(lib_path))
                logger.debug(f"[cv2_loader] Pre-loaded: {lib_name}")
            except OSError as e:
                logger.debug(f"[cv2_loader] Could not pre-load {lib_name}: {e}")
            break

    # ── 3. Inject CUDA Python binding dirs into sys.path ─────────────────────
    cuda_dirs_exist = []
    for py_dir in _OPENCV_PY_DIRS:
        if py_dir.is_dir():
            dir_str = str(py_dir)
            if dir_str not in sys.path:
                sys.path.insert(0, dir_str)
            cuda_dirs_exist.append(dir_str)

    # ── 4. Remove conflicting cv2 packages (pip) to avoid recursion ──────────
    conflicts = _find_conflicting_cv2_paths(cuda_dirs_exist)
    for p in conflicts:
        sys.path.remove(p)
        logger.debug(f"[cv2_loader] Temporarily removed conflicting cv2 path: {p}")

    # Also remove any stale old opencv build paths that may be in PYTHONPATH
    old_build_paths = [p for p in sys.path if 'opencv/build' in p and 'opencv_cuda' not in p]
    for p in old_build_paths:
        sys.path.remove(p)
        logger.debug(f"[cv2_loader] Removed old opencv build path: {p}")

    # Clean any partial cv2 module references
    _clean_cv2_modules()

    # ── 5. Try CUDA cv2 ─────────────────────────────────────────────────────
    try:
        import cv2  # noqa: PLC0415
        cuda_count = 0
        if hasattr(cv2, "cuda"):
            try:
                cuda_count = cv2.cuda.getCudaEnabledDeviceCount()
            except Exception:
                pass
        logger.info(
            f"[cv2_loader] ✅ cv2 {cv2.__version__} loaded  "
            f"CUDA devices={cuda_count}  "
            f"path={cv2.__file__}"
        )
        # Restore conflicting paths AFTER cv2 is loaded (won't re-import)
        for p in conflicts + old_build_paths:
            if p not in sys.path:
                sys.path.append(p)
        return True

    except (ImportError, Exception) as e:
        logger.warning(f"[cv2_loader] CUDA cv2 import failed: {e}")

    # ── 6. Fallback: pip-installed cv2 (no CUDA) ────────────────────────────
    _clean_cv2_modules()

    # Remove CUDA dirs, restore pip dirs
    for d in cuda_dirs_exist:
        if d in sys.path:
            sys.path.remove(d)
    for p in conflicts + old_build_paths:
        if p not in sys.path:
            sys.path.append(p)

    try:
        import cv2  # noqa: PLC0415
        logger.warning(
            f"[cv2_loader] ⚠️ Fallback to pip cv2 {cv2.__version__} (no CUDA)  "
            f"path={cv2.__file__}"
        )
        return True
    except ImportError as e2:
        logger.error(
            f"[cv2_loader] ❌ ALL cv2 imports failed!\n"
            f"  CUDA error: {e}\n"
            f"  Pip error: {e2}\n"
            f"  sys.path={sys.path[:8]}"
        )
        return False


# ── Auto-inject on import ─────────────────────────────────────────────────────
inject()
