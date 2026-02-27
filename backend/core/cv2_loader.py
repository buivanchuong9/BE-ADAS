"""
ABI-safe OpenCV CUDA loader.

Loads CUDA-enabled OpenCV ONLY when the binding was built for the running
Python version.  Falls back to the pip-installed cv2 (no CUDA) otherwise.

Safety rules
────────────
• The runtime Python version is detected dynamically.
• Only binding directories matching the runtime version are considered.
• A config-{major}.{minor}.py sentinel file must exist inside the cv2
  package directory for the CUDA path to be trusted.
• Mismatched bindings (e.g. python3.10 on a python3.12 runtime) are
  NEVER loaded — doing so would cause an ABI crash or recursion error.
"""

import os
import sys
import ctypes
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Runtime Python version (determined once) ─────────────────────────────────
PY_VER = f"{sys.version_info.major}.{sys.version_info.minor}"

# ── Configuration ────────────────────────────────────────────────────────────
_OPENCV_PREFIX  = Path(os.environ.get("OPENCV_PREFIX", "/home/phonglv/opencv_cuda"))
_OPENCV_LIB_DIR = Path(os.environ.get("OPENCV_LIB_DIR", str(_OPENCV_PREFIX / "lib")))

# ONLY version-matched binding directories — no fallback to other versions.
_OPENCV_PY_DIRS = [
    _OPENCV_PREFIX / "lib" / f"python{PY_VER}" / "dist-packages",
    _OPENCV_PREFIX / "lib" / f"python{PY_VER}" / "site-packages",
]

# Core shared libraries to pre-load (newest first)
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
    Find sys.path entries that contain a cv2 package but are NOT our
    CUDA dirs.  These come from pip (opencv-python / opencv-python-headless).
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
    proving the CUDA binding was built for the running Python version.
    """
    config_file = py_dir / "cv2" / f"config-{PY_VER}.py"
    return config_file.is_file()


# ── Main entry point ─────────────────────────────────────────────────────────

def inject() -> bool:
    """
    Load OpenCV with CUDA support **only when ABI-safe**.

    Flow
    ────
    1. Set LD_LIBRARY_PATH for child processes.
    2. Pre-load core .so via ctypes.
    3. Check candidate binding directories for ABI compatibility:
       - directory must exist
       - ``cv2/config-{PY_VER}.py`` must be present
    4. If at least one ABI-safe dir is found, temporarily remove
       conflicting pip cv2 paths, then ``import cv2``.
    5. Verify CUDA is actually usable (``cv2.cuda.getCudaEnabledDeviceCount``).
    6. On any failure, restore original sys.path and fall back to pip cv2.

    Safe to call multiple times — no-ops after the first successful run.
    """
    global _injected
    if _injected:
        return True
    _injected = True

    # Snapshot original sys.path so we can restore it on fallback.
    original_sys_path = list(sys.path)

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
            logger.info(
                "[cv2_loader] ABI mismatch — CUDA binding not built for "
                "Python %s (missing cv2/config-%s.py in %s)",
                PY_VER, PY_VER, py_dir,
            )
            continue
        abi_safe_dirs.append(str(py_dir))
        logger.debug("[cv2_loader] ABI-safe CUDA binding found: %s", py_dir)

    if not abi_safe_dirs:
        logger.info(
            "[cv2_loader] No ABI-compatible CUDA cv2 binding for Python %s. "
            "Falling back to pip OpenCV (CUDA disabled).",
            PY_VER,
        )
        return _fallback_to_pip_cv2(original_sys_path)

    # ── 4. Insert ABI-safe dirs, remove conflicting pip cv2 paths ────────────
    for d in abi_safe_dirs:
        if d not in sys.path:
            sys.path.insert(0, d)

    conflicts = _find_conflicting_cv2_paths(abi_safe_dirs)
    for p in conflicts:
        sys.path.remove(p)
        logger.debug("[cv2_loader] Temporarily removed conflicting path: %s", p)

    _clean_cv2_modules()

    # ── 5. Try CUDA cv2 import ───────────────────────────────────────────────
    cuda_err = None
    try:
        import cv2  # noqa: PLC0415

        cuda_count = 0
        if hasattr(cv2, "cuda"):
            try:
                cuda_count = cv2.cuda.getCudaEnabledDeviceCount()
            except Exception:
                pass

        if cuda_count > 0:
            logger.info(
                "[cv2_loader] cv2 %s loaded — CUDA devices=%d — %s",
                cv2.__version__, cuda_count, cv2.__file__,
            )
        else:
            logger.warning(
                "[cv2_loader] cv2 %s loaded from CUDA build but "
                "no CUDA devices detected — %s",
                cv2.__version__, cv2.__file__,
            )

        # Restore pip paths (cv2 is already loaded — won't re-import)
        for p in conflicts:
            if p not in sys.path:
                sys.path.append(p)
        return True

    except (ImportError, Exception) as exc:
        cuda_err = exc
        logger.warning("[cv2_loader] CUDA cv2 import failed: %s", exc)

    # ── 6. Fallback: pip-installed cv2 (no CUDA) ────────────────────────────
    return _fallback_to_pip_cv2(original_sys_path, cuda_err)


def _fallback_to_pip_cv2(
    original_sys_path: list[str],
    cuda_err: Exception | None = None,
) -> bool:
    """Restore sys.path and load pip cv2 without CUDA."""
    _clean_cv2_modules()

    # Restore the original sys.path exactly.
    sys.path[:] = original_sys_path

    try:
        import cv2  # noqa: PLC0415

        logger.warning(
            "[cv2_loader] Falling back to pip OpenCV (CUDA disabled) — "
            "cv2 %s — %s",
            cv2.__version__, cv2.__file__,
        )
        return True
    except ImportError as pip_err:
        logger.error(
            "[cv2_loader] ALL cv2 imports failed!\n"
            "  CUDA error : %s\n"
            "  Pip error  : %s\n"
            "  sys.path   : %s",
            cuda_err, pip_err, sys.path[:8],
        )
        return False


# ── Auto-inject on import ─────────────────────────────────────────────────────
inject()
