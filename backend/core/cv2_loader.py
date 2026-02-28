"""
STRICT OpenCV CUDA Loader — NO CPU FALLBACK.

This loader **requires** a CUDA-enabled OpenCV build.
If CUDA is unavailable the process is terminated immediately.

Contract:  NO GPU → NO SERVICE.

Loading strategy (in order):
  1. Custom CUDA build under OPENCV_PREFIX (exact Python version match)
  2. System cv2 (pip / conda) — still enforces CUDA
  3. Crash with actionable error

Safety rules:
  • Runtime Python version detected dynamically.
  • Both config file AND .so binary cpython tag are verified.
  • Mismatched bindings (wrong Python version) are NEVER loaded.
  • ``cv2.cuda.getCudaEnabledDeviceCount() > 0`` is enforced.
  • A real GPU memory upload test proves the device works.
"""

import os
import sys
import re
import time
import ctypes
import logging
import numpy as np
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Runtime Python version (determined once) ─────────────────────────────────
PY_MAJOR = sys.version_info.major
PY_MINOR = sys.version_info.minor
PY_VER   = f"{PY_MAJOR}.{PY_MINOR}"
# cpython tag that must appear in the .so filename, e.g. "cpython-312"
_CPYTHON_TAG = f"cpython-{PY_MAJOR}{PY_MINOR}"

# ── Configuration ────────────────────────────────────────────────────────────
_OPENCV_PREFIX  = Path(os.environ.get("OPENCV_PREFIX", os.path.expanduser("~/opencv_cuda")))
_OPENCV_LIB_DIR = Path(os.environ.get("OPENCV_LIB_DIR", str(_OPENCV_PREFIX / "lib")))

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


def _has_matching_so(cv2_dir: Path) -> bool:
    """
    Return True if cv2_dir contains a .so whose filename includes the
    current Python's cpython tag (e.g. ``cv2.cpython-312-x86_64-linux-gnu.so``).

    This is the REAL ABI check — config-*.py files can be generated for
    multiple Python versions at build time and are NOT reliable alone.
    """
    for f in cv2_dir.iterdir():
        if f.suffix == ".so" and _CPYTHON_TAG in f.name:
            return True
    # Also check python_loader directories (cv2/python-3.12/*.so)
    loader_dir = cv2_dir / f"python-{PY_VER}"
    if loader_dir.is_dir():
        for f in loader_dir.iterdir():
            if f.suffix == ".so" and _CPYTHON_TAG in f.name:
                return True
    return False


def _binding_is_abi_safe(pkg_dir: Path) -> bool:
    """
    Full ABI check for a candidate site-packages / dist-packages dir.

    Returns True only when:
      1. pkg_dir/cv2/ exists
      2. pkg_dir/cv2/config-{PY_VER}.py exists
      3. A .so with the correct cpython tag is found
    """
    cv2_dir = pkg_dir / "cv2"
    if not cv2_dir.is_dir():
        return False
    config = cv2_dir / f"config-{PY_VER}.py"
    if not config.is_file():
        logger.debug("[cv2_loader] No config-%s.py in %s", PY_VER, cv2_dir)
        return False
    if not _has_matching_so(cv2_dir):
        logger.debug(
            "[cv2_loader] config-%s.py exists but NO .so with tag '%s' in %s",
            PY_VER, _CPYTHON_TAG, cv2_dir,
        )
        return False
    return True


def _find_all_opencv_paths() -> list[str]:
    """
    Find ALL sys.path entries that contain any cv2 package or opencv build
    artifacts — including partial build trees like ``opencv/build/lib/python3``.
    """
    opencv_paths: list[str] = []
    for p in sys.path:
        pp = Path(p)
        # Standard cv2 package
        if (pp / "cv2").is_dir():
            opencv_paths.append(p)
            continue
        # opencv build tree (e.g. ~/opencv/build/lib/python3)
        if "opencv" in p.lower() and pp.is_dir():
            opencv_paths.append(p)
    return opencv_paths


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
      1. Scan OPENCV_PREFIX for binding dirs with EXACT Python version match
         (both config file AND .so binary cpython tag).
      2. If no custom build matches, fall back to system cv2 (pip/conda).
      3. In ALL cases enforce: cv2.cuda present, device count > 0,
         GPU memory upload succeeds.

    Contract: NO GPU → NO SERVICE.
    """
    global _injected
    if _injected:
        return
    _injected = True

    t0 = time.monotonic()

    using_custom_build = False
    removed_paths: list[str] = []

    logger.info(
        "[cv2_loader] Python %s (%s) — looking for CUDA OpenCV under %s",
        PY_VER, _CPYTHON_TAG, _OPENCV_PREFIX,
    )

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
    #     Scan OPENCV_PREFIX/lib/ for any python*/{{dist,site}}-packages
    #     that pass the full ABI check (config + .so tag).
    abi_safe_dirs: list[str] = []

    if _OPENCV_PREFIX.is_dir():
        lib_dir = _OPENCV_PREFIX / "lib"
        if lib_dir.is_dir():
            # Gather ALL candidate dirs (both explicit and discovered)
            candidates: list[Path] = []

            # Explicit version-matched dirs (highest priority)
            for suffix in ("dist-packages", "site-packages"):
                candidates.append(lib_dir / f"python{PY_VER}" / suffix)

            # Also scan other python* dirs in case layout is non-standard
            for py_dir in sorted(lib_dir.glob("python*")):
                for suffix in ("dist-packages", "site-packages"):
                    c = py_dir / suffix
                    if c not in candidates:
                        candidates.append(c)

            for candidate in candidates:
                if not candidate.is_dir():
                    continue
                if _binding_is_abi_safe(candidate):
                    abi_safe_dirs.append(str(candidate))
                    logger.info("[cv2_loader] ABI-safe CUDA binding: %s", candidate)
                elif (candidate / "cv2").is_dir():
                    logger.info(
                        "[cv2_loader] SKIP %s — cv2 found but ABI mismatch "
                        "(need %s .so)",
                        candidate, _CPYTHON_TAG,
                    )

    # ── 4. Prepare sys.path ──────────────────────────────────────────────────
    if abi_safe_dirs:
        using_custom_build = True

        # Remove ALL other opencv-related paths to prevent recursion
        all_opencv_paths = _find_all_opencv_paths()
        abi_set = set(abi_safe_dirs)
        for p in all_opencv_paths:
            if p not in abi_set and p in sys.path:
                sys.path.remove(p)
                removed_paths.append(p)
                logger.debug("[cv2_loader] Removed conflicting path: %s", p)

        # Insert our ABI-safe dirs at front
        for d in reversed(abi_safe_dirs):
            if d in sys.path:
                sys.path.remove(d)
            sys.path.insert(0, d)

        _clean_cv2_modules()

        logger.info("[cv2_loader] Using custom CUDA build from: %s", abi_safe_dirs)
    else:
        # No custom build found — clean up any partial/mismatched opencv paths
        # that would cause recursion, then fall back to system cv2
        all_opencv_paths = _find_all_opencv_paths()
        for p in all_opencv_paths:
            # Remove paths under OPENCV_PREFIX (wrong version) and opencv build trees
            pp = Path(p)
            is_custom_opencv = (
                str(_OPENCV_PREFIX) in p
                or ("opencv" in p.lower() and "build" in p.lower())
            )
            if is_custom_opencv:
                sys.path.remove(p)
                removed_paths.append(p)
                logger.debug("[cv2_loader] Removed mismatched opencv path: %s", p)

        _clean_cv2_modules()

        logger.warning(
            "[cv2_loader] No ABI-compatible CUDA OpenCV found under %s "
            "for Python %s (need .so with %s tag). "
            "Falling back to system cv2 — CUDA still enforced.",
            _OPENCV_PREFIX, PY_VER, _CPYTHON_TAG,
        )

    # ── 5. Import & enforce CUDA ─────────────────────────────────────────────
    try:
        import cv2  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError(
            f"[cv2_loader] Cannot import cv2. "
            f"On this server (Python {PY_VER}), either:\n"
            f"  1. Rebuild OpenCV CUDA for Python {PY_VER}:\n"
            f"     cmake -DPYTHON3_EXECUTABLE=$(which python3) -DWITH_CUDA=ON ...\n"
            f"  2. Or install system cv2 with CUDA: pip install opencv-contrib-python\n"
            f"Error: {exc}"
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

    # Restore removed paths AFTER cv2 is loaded (won't re-import)
    for p in removed_paths:
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
