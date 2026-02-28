"""
STRICT OpenCV CUDA Loader — NO CPU FALLBACK.

This loader **requires** a CUDA-enabled OpenCV build that matches the
running Python version.  If CUDA is unavailable or the binding ABI does
not match, the process is terminated immediately.

Contract:  NO GPU → NO SERVICE.

Safety rules
────────────
• Runtime Python version detected dynamically.
• Binding directories auto-discovered under OPENCV_PREFIX.
• ``cv2/config-{major}.{minor}.py`` must exist (ABI proof).
• Mismatched bindings are NEVER loaded.
• Falls back to system cv2 if custom build not found (still enforces CUDA).
• After import, ``cv2.cuda.getCudaEnabledDeviceCount() > 0`` is enforced.
• A real GPU memory upload test is performed to prove the device works.
"""

import os
import sys
import time
import ctypes
import logging
import glob
import numpy as np
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Runtime Python version (determined once) ─────────────────────────────────
PY_VER = f"{sys.version_info.major}.{sys.version_info.minor}"

# ── Configuration ────────────────────────────────────────────────────────────
_OPENCV_PREFIX  = Path(os.environ.get("OPENCV_PREFIX", os.path.expanduser("~/opencv_cuda")))
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


def _auto_discover_binding_dirs(prefix: Path) -> list[Path]:
    """
    Scan *prefix*/lib/python*/{{dist,site}}-packages for cv2 bindings
    matching the current Python runtime version.

    Returns a list of ABI-safe directories found.
    """
    discovered: list[Path] = []
    lib_dir = prefix / "lib"
    if not lib_dir.is_dir():
        return discovered

    # Look for any python* directories
    for py_dir in sorted(lib_dir.glob("python*")):
        for suffix in ("dist-packages", "site-packages"):
            candidate = py_dir / suffix
            if candidate.is_dir() and (candidate / "cv2").is_dir():
                if _cuda_binding_matches_runtime(candidate):
                    discovered.append(candidate)
                else:
                    logger.debug(
                        "[cv2_loader] Found cv2 at %s but ABI mismatch "
                        "(no config-%s.py)",
                        candidate, PY_VER,
                    )
    return discovered


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

    Strategy:
    1. Try OPENCV_PREFIX custom build (exact version match).
    2. Auto-discover bindings under OPENCV_PREFIX/lib/python*/.
    3. Fall back to system cv2 (pip / conda).
    4. In ALL cases enforce: cv2.cuda present, device count > 0,
       GPU memory upload succeeds.

    Contract: NO GPU → NO SERVICE.
    """
    global _injected
    if _injected:
        return
    _injected = True

    t0 = time.monotonic()

    using_custom_build = False

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

    # 3a. Try explicit version-matched dirs first
    for py_dir in _OPENCV_PY_DIRS:
        if not py_dir.is_dir():
            logger.debug("[cv2_loader] Candidate dir does not exist: %s", py_dir)
            continue
        if not _cuda_binding_matches_runtime(py_dir):
            logger.warning(
                "[cv2_loader] ABI mismatch — CUDA binding at %s not built for "
                "Python %s (missing cv2/config-%s.py).",
                py_dir, PY_VER, PY_VER,
            )
            continue
        abi_safe_dirs.append(str(py_dir))
        logger.debug("[cv2_loader] ABI-safe CUDA binding: %s", py_dir)

    # 3b. Auto-discover if explicit dirs not found
    if not abi_safe_dirs and _OPENCV_PREFIX.is_dir():
        logger.info(
            "[cv2_loader] Exact binding dirs not found, auto-discovering under %s ...",
            _OPENCV_PREFIX,
        )
        discovered = _auto_discover_binding_dirs(_OPENCV_PREFIX)
        for d in discovered:
            abi_safe_dirs.append(str(d))
            logger.info("[cv2_loader] Auto-discovered ABI-safe binding: %s", d)

    # ── 4. Insert ABI-safe dirs, remove conflicting pip cv2 paths ────────────
    if abi_safe_dirs:
        using_custom_build = True
        for d in abi_safe_dirs:
            if d not in sys.path:
                sys.path.insert(0, d)

        conflicts = _find_conflicting_cv2_paths(abi_safe_dirs)
        for p in conflicts:
            sys.path.remove(p)
            logger.debug("[cv2_loader] Removed conflicting pip cv2 path: %s", p)

        _clean_cv2_modules()
    else:
        conflicts = []
        logger.warning(
            "[cv2_loader] No custom CUDA OpenCV build found under %s for Python %s. "
            "Falling back to system cv2 — CUDA will still be enforced.",
            _OPENCV_PREFIX, PY_VER,
        )

    # ── 5. Import & enforce CUDA ─────────────────────────────────────────────
    try:
        import cv2  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError(
            f"[cv2_loader] Cannot import cv2 at all. "
            f"Install opencv-python or build OpenCV with CUDA under {_OPENCV_PREFIX}. "
            f"NO GPU → NO SERVICE. Error: {exc}"
        ) from exc

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
    if using_custom_build:
        for p in conflicts:
            if p not in sys.path:
                sys.path.append(p)

    elapsed = (time.monotonic() - t0) * 1000
    source = "custom CUDA build" if using_custom_build else "system cv2"
    logger.info(
        "[cv2_loader] cv2 %s loaded (%s) — CUDA devices=%d — "
        "GPU overlay ENABLED — init %.0fms — %s",
        cv2.__version__, source, cuda_count, elapsed, cv2.__file__,
    )


# ── Auto-inject on import ─────────────────────────────────────────────────────
inject()
