import cv2
import numpy as np
import logging
from collections import deque
from typing import Optional, Tuple, Dict, List

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Detect cv2.cuda once at module import
# ---------------------------------------------------------------------------
try:
    _CV2_CUDA: bool = (
        hasattr(cv2, 'cuda') and cv2.cuda.getCudaEnabledDeviceCount() > 0
    )
except Exception:
    _CV2_CUDA = False

if _CV2_CUDA:
    logger.info("[LaneV4] cv2.cuda detected ✅ — all image ops routed to GPU")
else:
    logger.info("[LaneV4] cv2.cuda not available — CPU image ops (fallback)")


# ---------------------------------------------------------------------------
# Moving Average Smoother for polynomial coefficients
# ---------------------------------------------------------------------------

class PolynomialSmoother:
    """
    Exponential Moving Average (EMA) smoother for 2nd-order polynomial
    coefficients [a, b, c].

    Prevents flickering when YOLO/binary mask produces slightly different
    polynomial fits frame-to-frame.
    """

    def __init__(self, window: int = 12, alpha: float = 0.25):
        """
        Args:
            window : Hard history window (for fallback mean)
            alpha  : EMA weight — lower = smoother but laggier
        """
        self.alpha = alpha
        self.history_a: deque = deque(maxlen=window)
        self.history_b: deque = deque(maxlen=window)
        self.history_c: deque = deque(maxlen=window)
        self._ema: Optional[np.ndarray] = None   # [a, b, c]

    def update(self, coeffs: Optional[np.ndarray]) -> Optional[np.ndarray]:
        """
        Feed a new (a, b, c) measurement; returns EMA-smoothed coefficients.
        If coeffs is None (no lane detected this frame) returns last known values.
        """
        if coeffs is None or len(coeffs) != 3:
            return self._ema  # hold last value

        self.history_a.append(coeffs[0])
        self.history_b.append(coeffs[1])
        self.history_c.append(coeffs[2])

        if self._ema is None:
            self._ema = coeffs.copy()
        else:
            self._ema = self.alpha * coeffs + (1.0 - self.alpha) * self._ema

        return self._ema.copy()

    def reset(self) -> None:
        self._ema = None
        self.history_a.clear()
        self.history_b.clear()
        self.history_c.clear()

    @property
    def is_initialized(self) -> bool:
        return self._ema is not None


# ---------------------------------------------------------------------------
# Perspective Transform Helper
# ---------------------------------------------------------------------------

class PerspectiveTransformer:
    """
    Manages the perspective (BEV) transform matrices.

    Default source points are tuned for a standard dashcam mounted at
    ~1.2 m height, 1280×720 input resolution.  Override via calibrate().
    """

    # Source quad (trapezoid on road surface — original frame)
    # Format: top-left, top-right, bottom-right, bottom-left
    DEFAULT_SRC_RATIO = np.float32([
        [0.42, 0.65],   # top-left
        [0.58, 0.65],   # top-right
        [0.90, 0.95],   # bottom-right
        [0.10, 0.95],   # bottom-left
    ])

    # Destination quad (rectangle — BEV frame)
    DEFAULT_DST_RATIO = np.float32([
        [0.25, 0.00],   # top-left
        [0.75, 0.00],   # top-right
        [0.75, 1.00],   # bottom-right
        [0.25, 1.00],   # bottom-left
    ])

    def __init__(self, frame_w: int = 1280, frame_h: int = 720):
        self.frame_w = frame_w
        self.frame_h = frame_h
        self._build_matrices()

    def _build_matrices(self) -> None:
        src = (self.DEFAULT_SRC_RATIO * [self.frame_w, self.frame_h]).astype(np.float32)
        dst = (self.DEFAULT_DST_RATIO * [self.frame_w, self.frame_h]).astype(np.float32)
        self.M     = cv2.getPerspectiveTransform(src, dst)
        self.M_inv = cv2.getPerspectiveTransform(dst, src)
        self._src  = src
        self._dst  = dst
        logger.debug(f"BEV transform built for {self.frame_w}×{self.frame_h}")

    def calibrate(self, src_pts: np.ndarray, dst_pts: np.ndarray) -> None:
        """Override default src/dst points (for per-device calibration)."""
        self.M     = cv2.getPerspectiveTransform(src_pts.astype(np.float32),
                                                 dst_pts.astype(np.float32))
        self.M_inv = cv2.getPerspectiveTransform(dst_pts.astype(np.float32),
                                                 src_pts.astype(np.float32))
        self._src  = src_pts
        self._dst  = dst_pts
        logger.info("BEV transform recalibrated with custom points")

    def warp(self, frame: np.ndarray) -> np.ndarray:
        """Warp frame into Bird's Eye View."""
        return cv2.warpPerspective(
            frame, self.M,
            (self.frame_w, self.frame_h),
            flags=cv2.INTER_LINEAR
        )

    def unwarp(self, bev_frame: np.ndarray,
               out_w: Optional[int] = None,
               out_h: Optional[int] = None) -> np.ndarray:
        """Warp BEV frame back to original perspective."""
        w = out_w or self.frame_w
        h = out_h or self.frame_h
        return cv2.warpPerspective(
            bev_frame, self.M_inv,
            (w, h),
            flags=cv2.INTER_LINEAR
        )

    def update_resolution(self, w: int, h: int) -> None:
        """Rebuild matrices when input resolution changes."""
        if w != self.frame_w or h != self.frame_h:
            self.frame_w = w
            self.frame_h = h
            self._build_matrices()


# ---------------------------------------------------------------------------
# Lane Detector V4 — Main Class
# ---------------------------------------------------------------------------

class LaneDetectorV4:
    """
    Full V4 lane detection pipeline.

    Usage::

        detector = LaneDetectorV4(device='cuda')

        for frame in video:
            result = detector.process_frame(frame)
            annotated = result['annotated_frame']
            lane_offset = result['lane_offset']     # -1.0 (far left) .. +1.0 (far right)
            has_lane   = result['has_lane']
    """

    # Color thresholds (HSV) for yellow/white lane lines
    YELLOW_HSV_LO = np.array([18,  60,  60])
    YELLOW_HSV_HI = np.array([35, 255, 255])
    WHITE_V_THRESH = 200          # Grayscale threshold for white lines

    # Sliding window parameters
    SW_N_WINDOWS      = 12        # Number of horizontal slices
    SW_MARGIN         = 80        # Search half-width per window (px)
    SW_MIN_PIX        = 50        # Min pixels to recenter window

    # Driving corridor fill
    CORRIDOR_COLOR_BGR = (0, 200, 60)       # Green (BGR)
    CORRIDOR_ALPHA     = 0.40               # Transparency (0=invisible, 1=solid)

    # Lane offset threshold for LDW trigger
    OFFSET_WARNING_THRESHOLD  = 0.35        # 35 % of lane half-width
    OFFSET_CRITICAL_THRESHOLD = 0.60        # 60 %

    def __init__(
        self,
        device: str = "cuda",
        frame_w: int = 1280,
        frame_h: int = 720,
        smooth_window: int = 12,
        smooth_alpha: float = 0.25,
    ):
        self.device   = device
        self.frame_w  = frame_w
        self.frame_h  = frame_h

        # Perspective transformer (rebuilt when resolution changes)
        self.bev = PerspectiveTransformer(frame_w, frame_h)

        # Per-lane EMA smoothers
        self._left_smoother  = PolynomialSmoother(smooth_window, smooth_alpha)
        self._right_smoother = PolynomialSmoother(smooth_window, smooth_alpha)

        # Confidence tracking (frames since last valid detection)
        self._left_lost  = 0
        self._right_lost = 0
        self.MAX_LOST_FRAMES = 8   # Keep last fit for up to N frames

        # Stats
        self._frame_count = 0

        # ── GPU acceleration (cv2.cuda) ──────────────────────────────────
        # _cuda_ok  : False if cv2.cuda not available OR a GPU op fails at runtime
        # _gf       : dict of pre-created cv2.cuda filter objects (lazy, per resolution)
        # _gf_res   : (w, h) for which _gf was built — rebuild on resolution change
        self._cuda_ok: bool      = _CV2_CUDA
        self._gf     : Optional[Dict] = None
        self._gf_res : tuple     = (0, 0)
        if self._cuda_ok:
            self._init_gpu_filters(frame_w, frame_h)

        logger.info(
            f"[LaneV4] Initialized — BEV {frame_w}×{frame_h}  "
            f"smooth_window={smooth_window}  alpha={smooth_alpha}  "
            f"cuda={'ON' if self._cuda_ok else 'OFF'}"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process_frame(self, frame: np.ndarray) -> Dict:
        """
        Main processing entry point.  Returns full result dict.

        Returns
        -------
        dict with keys:
          annotated_frame : np.ndarray  — original frame with overlay drawn
          bev_debug       : np.ndarray  — BEV binary mask (for debug display)
          has_lane        : bool
          left_fit        : np.ndarray | None   — [a, b, c] smoothed
          right_fit       : np.ndarray | None
          lane_offset     : float  — [-1, +1], positive = drifting right
          offset_level    : str    — 'SAFE' | 'WARNING' | 'CRITICAL'
          lane_width_px   : int    — lane width in BEV pixels
          corridor_pts    : np.ndarray | None  — filled polygon pts (original space)
        """
        self._frame_count += 1
        h, w = frame.shape[:2]

        # Rebuild BEV transform if resolution changed
        self.bev.update_resolution(w, h)

        # 1.  Build binary lane mask in BEV space
        bev_binary = self._bev_binary_mask(frame)

        # 2.  Sliding window search → raw polynomial coefficients
        left_raw, right_raw, sw_debug = self._sliding_window(bev_binary)

        # 3.  Smooth coefficients (EMA)
        left_fit  = self._left_smoother.update(left_raw)
        right_fit = self._right_smoother.update(right_raw)

        # Track confidence
        self._left_lost  = 0 if left_raw is not None  else self._left_lost  + 1
        self._right_lost = 0 if right_raw is not None else self._right_lost + 1

        # If lost too long, reset smoother
        if self._left_lost  > self.MAX_LOST_FRAMES: self._left_smoother.reset();  left_fit  = None
        if self._right_lost > self.MAX_LOST_FRAMES: self._right_smoother.reset(); right_fit = None

        has_lane = (left_fit is not None) or (right_fit is not None)

        # 4.  Render corridor onto BEV, then unwarp back
        annotated, corridor_pts = self._render_and_unwarp(frame, left_fit, right_fit, h, w)

        # 5.  Lane offset (vehicle center vs lane center)
        lane_offset, lane_width_px = self._compute_lane_offset(left_fit, right_fit, h)

        offset_level = self._classify_offset(lane_offset)

        return {
            'annotated_frame': annotated,
            'bev_debug'      : sw_debug,
            'has_lane'       : has_lane,
            'left_fit'       : left_fit,
            'right_fit'      : right_fit,
            'lane_offset'    : lane_offset,       # float [-1, +1]
            'offset_level'   : offset_level,      # SAFE / WARNING / CRITICAL
            'lane_width_px'  : lane_width_px,
            'corridor_pts'   : corridor_pts,
            'left_lost'      : self._left_lost,
            'right_lost'     : self._right_lost,
        }

    def calibrate(self, src_pts: np.ndarray, dst_pts: np.ndarray) -> None:
        """Override default BEV calibration points."""
        self.bev.calibrate(src_pts, dst_pts)
        self._left_smoother.reset()
        self._right_smoother.reset()

    # ------------------------------------------------------------------
    # GPU filter init
    # ------------------------------------------------------------------

    def _init_gpu_filters(self, w: int, h: int) -> None:
        """
        Pre-create all cv2.cuda filter objects.
        Called once at startup and whenever the input resolution changes.
        All filters are stateless w.r.t. image size — they apply to any GpuMat.
        The ROI mask IS size-dependent and is rebuilt here.
        """
        # ROI mask: zeros in top 40 % (sky + car hood), ones in bottom 60 %
        roi_cpu = np.ones((h, w), dtype=np.uint8) * 255
        roi_cpu[:int(h * 0.40), :] = 0
        gpu_roi = cv2.cuda_GpuMat()
        gpu_roi.upload(roi_cpu)

        k3 = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        self._gf = {
            'gauss'       : cv2.cuda.createGaussianFilter(
                                cv2.CV_8UC1, cv2.CV_8UC1, (5, 5), 0),
            'sobel'       : cv2.cuda.createSobelFilter(
                                cv2.CV_8UC1, cv2.CV_32F, 1, 0, ksize=3),
            'morph_close' : cv2.cuda.createMorphologyFilter(
                                cv2.MORPH_CLOSE, cv2.CV_8UC1, k3),
            'morph_open'  : cv2.cuda.createMorphologyFilter(
                                cv2.MORPH_OPEN,  cv2.CV_8UC1, k3),
            'roi_mask'    : gpu_roi,
        }
        self._gf_res = (w, h)
        logger.debug(f"[LaneV4] GPU filters built for {w}\u00d7{h}")

    # ------------------------------------------------------------------
    # Step 1: Binary mask in BEV space
    # ------------------------------------------------------------------

    def _bev_binary_mask(self, frame: np.ndarray) -> np.ndarray:
        """
        Binary lane mask in BEV space (0/255).
        Routes to GPU (cv2.cuda) when available; falls back to CPU on error.
        """
        h, w = frame.shape[:2]
        # Rebuild GPU filters if input resolution changed
        if self._cuda_ok and self._gf_res != (w, h):
            self._init_gpu_filters(w, h)

        if self._cuda_ok and self._gf:
            try:
                return self._bev_binary_mask_gpu(frame)
            except Exception as exc:
                logger.warning(f"[LaneV4] GPU mask error ({exc}) — falling back to CPU")
                self._cuda_ok = False   # disable GPU for this session

        return self._bev_binary_mask_cpu(frame)

    # -- GPU path (cv2.cuda) --

    def _bev_binary_mask_gpu(self, frame: np.ndarray) -> np.ndarray:
        """
        GPU-accelerated binary mask.
        ALL heavy ops run on GPU (BEV warp, color convert, Sobel, morph).
        CPU is only used for the final download.
        """
        gf   = self._gf
        bw   = self.bev.frame_w
        bh   = self.bev.frame_h

        # ── Upload once → BEV warp on GPU ────────────────────────────────
        gpu_src = cv2.cuda_GpuMat()
        gpu_src.upload(frame)
        gpu_bev = cv2.cuda.warpPerspective(
            gpu_src, self.bev.M, (bw, bh), flags=cv2.INTER_LINEAR
        )

        # ── Yellow mask: per-channel HSV thresholds on GPU ───────────────
        gpu_hsv = cv2.cuda.cvtColor(gpu_bev, cv2.COLOR_BGR2HSV)
        chs = cv2.cuda.split(gpu_hsv)          # [H, S, V] GpuMats
        gh, gs, gv = chs[0], chs[1], chs[2]

        _, h_lo = cv2.cuda.threshold(gh, int(self.YELLOW_HSV_LO[0]) - 1, 255, cv2.THRESH_BINARY)
        _, h_hi = cv2.cuda.threshold(gh, int(self.YELLOW_HSV_HI[0]),     255, cv2.THRESH_BINARY_INV)
        _, s_lo = cv2.cuda.threshold(gs, int(self.YELLOW_HSV_LO[1]) - 1, 255, cv2.THRESH_BINARY)
        _, v_lo = cv2.cuda.threshold(gv, int(self.YELLOW_HSV_LO[2]) - 1, 255, cv2.THRESH_BINARY)
        yellow  = cv2.cuda.bitwise_and(
            cv2.cuda.bitwise_and(h_lo, h_hi),
            cv2.cuda.bitwise_and(s_lo, v_lo),
        )

        # ── White mask: grayscale threshold on GPU ────────────────────────
        gpu_gray = cv2.cuda.cvtColor(gpu_bev, cv2.COLOR_BGR2GRAY)
        _, white = cv2.cuda.threshold(gpu_gray, self.WHITE_V_THRESH, 255, cv2.THRESH_BINARY)

        # ── Sobel-x gradient mask on GPU ──────────────────────────────────
        gpu_blur = gf['gauss'].apply(gpu_gray)          # uint8 blur
        gpu_sx   = gf['sobel'].apply(gpu_blur)          # float32, signed
        try:
            gpu_abs = cv2.cuda.abs(gpu_sx)              # element-wise abs (float32)
        except AttributeError:
            # Older OpenCV without cuda.abs: 1 download/upload (~0.5 ms)
            gpu_abs = cv2.cuda_GpuMat()
            gpu_abs.upload(np.abs(gpu_sx.download()).astype(np.float32))
        gpu_norm = cv2.cuda_GpuMat(gpu_sx.size(), cv2.CV_8UC1)
        cv2.cuda.normalize(gpu_abs, gpu_norm, 0, 255, cv2.NORM_MINMAX, cv2.CV_8UC1)
        _, grad  = cv2.cuda.threshold(gpu_norm, 30, 255, cv2.THRESH_BINARY)

        # ── Combine all masks + apply pre-built ROI mask ──────────────────
        combined = cv2.cuda.bitwise_or(cv2.cuda.bitwise_or(yellow, white), grad)
        combined = cv2.cuda.bitwise_and(combined, gf['roi_mask'])

        # ── Morphological cleanup on GPU ──────────────────────────────────
        combined = gf['morph_close'].apply(combined)
        combined = gf['morph_open'].apply(combined)

        # ── Download: only 1 D2H copy per frame ──────────────────────────
        return combined.download()

    # -- CPU fallback path --

    def _bev_binary_mask_cpu(self, frame: np.ndarray) -> np.ndarray:
        """CPU fallback — identical algorithm, pure OpenCV/numpy."""
        bev = self.bev.warp(frame)

        # Yellow mask (HSV)
        hsv = cv2.cvtColor(bev, cv2.COLOR_BGR2HSV)
        yellow_mask = cv2.inRange(hsv, self.YELLOW_HSV_LO, self.YELLOW_HSV_HI)

        # White mask (grayscale)
        gray = cv2.cvtColor(bev, cv2.COLOR_BGR2GRAY)
        _, white_mask = cv2.threshold(gray, self.WHITE_V_THRESH, 255, cv2.THRESH_BINARY)

        # Sobel-x gradient
        blur   = cv2.GaussianBlur(gray, (5, 5), 0)
        sobelx = cv2.Sobel(blur, cv2.CV_64F, 1, 0, ksize=3)
        abs_sx = np.absolute(sobelx)
        scaled = np.uint8(255 * abs_sx / (abs_sx.max() + 1e-6))
        _, grad_mask = cv2.threshold(scaled, 30, 255, cv2.THRESH_BINARY)

        combined = cv2.bitwise_or(yellow_mask, white_mask)
        combined = cv2.bitwise_or(combined, grad_mask)

        roi_h = int(combined.shape[0] * 0.40)
        combined[:roi_h, :] = 0

        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        combined = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, kernel)
        combined = cv2.morphologyEx(combined, cv2.MORPH_OPEN,  kernel)
        return combined

    # ------------------------------------------------------------------
    # Step 2: Sliding window search
    # ------------------------------------------------------------------

    def _sliding_window(
        self, binary: np.ndarray
    ) -> Tuple[Optional[np.ndarray], Optional[np.ndarray], np.ndarray]:
        """
        Classic sliding-window lane pixel search.

        Returns
        -------
        left_coeffs  : np.ndarray [a,b,c] or None
        right_coeffs : np.ndarray [a,b,c] or None
        debug_img    : coloured BEV debug visualisation
        """
        h, w = binary.shape
        debug = np.dstack([binary, binary, binary])   # 3-channel for colour draw

        # --- Histogram of bottom half to find base x positions ---
        histogram = np.sum(binary[h // 2:, :], axis=0)
        midpoint  = w // 2
        left_base  = int(np.argmax(histogram[:midpoint]))
        right_base = int(np.argmax(histogram[midpoint:]) + midpoint)

        win_h = h // self.SW_N_WINDOWS
        margin = self.SW_MARGIN
        minpix = self.SW_MIN_PIX

        # All non-zero pixels
        nonzero   = binary.nonzero()
        nz_y      = np.array(nonzero[0])
        nz_x      = np.array(nonzero[1])

        left_cur  = left_base
        right_cur = right_base

        left_lane_ids  = []
        right_lane_ids = []

        for win_idx in range(self.SW_N_WINDOWS):
            y_lo  = h - (win_idx + 1) * win_h
            y_hi  = h - win_idx * win_h
            lx_lo = left_cur  - margin
            lx_hi = left_cur  + margin
            rx_lo = right_cur - margin
            rx_hi = right_cur + margin

            # Draw debug rectangles
            cv2.rectangle(debug, (lx_lo, y_lo), (lx_hi, y_hi), (255, 255,   0), 1)
            cv2.rectangle(debug, (rx_lo, y_lo), (rx_hi, y_hi), (  0, 255, 255), 1)

            # Identify non-zero pixels in each window
            good_left  = ((nz_y >= y_lo) & (nz_y < y_hi) &
                          (nz_x >= lx_lo) & (nz_x < lx_hi)).nonzero()[0]
            good_right = ((nz_y >= y_lo) & (nz_y < y_hi) &
                          (nz_x >= rx_lo) & (nz_x < rx_hi)).nonzero()[0]

            left_lane_ids.append(good_left)
            right_lane_ids.append(good_right)

            # Recenter windows
            if len(good_left)  > minpix: left_cur  = int(np.mean(nz_x[good_left]))
            if len(good_right) > minpix: right_cur = int(np.mean(nz_x[good_right]))

        # Concatenate all lane pixel indices
        try:
            left_ids  = np.concatenate(left_lane_ids)
            right_ids = np.concatenate(right_lane_ids)
        except ValueError:
            return None, None, debug

        lx = nz_x[left_ids];   ly = nz_y[left_ids]
        rx = nz_x[right_ids];  ry = nz_y[right_ids]

        # Colour debug image
        debug[ly, lx] = [255, 0,   0]    # Blue = left
        debug[ry, rx] = [0,   0, 255]    # Red  = right

        # --- Fit 2nd-order polynomials — x = f(y) avoids vertical ambiguity ---
        #   x = a*y^2 + b*y + c   (fit x as function of y for vertical lanes)
        left_fit  = self._fit_poly(lx, ly, h)
        right_fit = self._fit_poly(rx, ry, h)

        # Draw fitted curves on debug image
        if left_fit  is not None: self._draw_poly_debug(debug, left_fit,  h, (255, 64,  64 ))
        if right_fit is not None: self._draw_poly_debug(debug, right_fit, h, (64,  64,  255))

        return left_fit, right_fit, debug

    def _fit_poly(
        self, x_px: np.ndarray, y_px: np.ndarray, frame_h: int
    ) -> Optional[np.ndarray]:
        """
        Fit 2nd-order polynomial x = a*y^2 + b*y + c.
        Normalise y to [0,1] for numerical stability.
        Returns [a, b, c] array or None if not enough points.
        """
        MIN_POINTS = 60
        if len(x_px) < MIN_POINTS:
            return None

        try:
            # Normalise to avoid ill-conditioned matrices
            yn = y_px / frame_h
            coeffs = np.polyfit(yn, x_px, 2)     # [a, b, c] in normalised space
            return coeffs.astype(np.float64)
        except (np.linalg.LinAlgError, TypeError):
            return None

    def _draw_poly_debug(
        self, img: np.ndarray, coeffs: np.ndarray, h: int, color: tuple
    ) -> None:
        """Draw polynomial curve on debug image."""
        ys  = np.linspace(0, h - 1, h)
        yn  = ys / h
        xs  = np.polyval(coeffs, yn)
        pts = np.column_stack([xs, ys]).astype(np.int32)
        for i in range(1, len(pts)):
            p1 = tuple(pts[i - 1])
            p2 = tuple(pts[i])
            x1, y1 = p1
            x2, y2 = p2
            if 0 <= x1 < img.shape[1] and 0 <= x2 < img.shape[1]:
                cv2.line(img, (x1, y1), (x2, y2), color, 3)

    # ------------------------------------------------------------------
    # Step 3: Render corridor + Inverse Warp
    # ------------------------------------------------------------------

    def _render_and_unwarp(
        self,
        original: np.ndarray,
        left_fit : Optional[np.ndarray],
        right_fit: Optional[np.ndarray],
        h: int, w: int
    ) -> Tuple[np.ndarray, Optional[np.ndarray]]:
        """
        Draw the driving corridor (green polygon) in BEV space,
        then inverse-warp it back to the original camera perspective
        and alpha-blend onto the original frame.

        Returns (annotated_frame, corridor_pts_original_space).
        """
        if left_fit is None and right_fit is None:
            return original.copy(), None

        # Canvas in BEV space (black background)
        bev_canvas = np.zeros((h, w, 3), dtype=np.uint8)

        # y values going top-to-bottom in BEV
        ys  = np.linspace(0, h - 1, h)
        yn  = ys / h

        # If only one lane is detected, mirror it with a fixed width offset
        LANE_HALF_PX = int(w * 0.15)   # ~15 % of width as estimated half-lane

        if left_fit is not None:
            left_xs = np.polyval(left_fit, yn)
        else:
            right_xs = np.polyval(right_fit, yn)
            left_xs  = right_xs - 2 * LANE_HALF_PX

        if right_fit is not None:
            right_xs = np.polyval(right_fit, yn)
        else:
            left_xs_tmp = np.polyval(left_fit, yn)
            right_xs    = left_xs_tmp + 2 * LANE_HALF_PX
            left_xs     = left_xs_tmp

        # Build polygon: left lane (top→bottom) then right lane (bottom→top)
        left_pts  = np.column_stack([left_xs,  ys]).astype(np.int32)
        right_pts = np.column_stack([right_xs, ys]).astype(np.int32)
        poly_pts  = np.vstack([left_pts, right_pts[::-1]])   # closed polygon

        # Draw filled corridor on BEV canvas
        cv2.fillPoly(bev_canvas, [poly_pts], self.CORRIDOR_COLOR_BGR)

        # Draw lane boundary lines
        for pts, clr in [(left_pts, (0, 255, 255)), (right_pts, (0, 255, 255))]:
            for i in range(1, len(pts)):
                x1, y1 = pts[i - 1]
                x2, y2 = pts[i]
                if 0 <= x1 < w and 0 <= x2 < w:
                    cv2.line(bev_canvas, (x1, y1), (x2, y2), clr, 4)

        # ── Inverse warp BEV corridor → original camera view (GPU if available) ──
        if self._cuda_ok:
            _gc = cv2.cuda_GpuMat()
            _gc.upload(bev_canvas)
            _gu = cv2.cuda.warpPerspective(
                _gc, self.bev.M_inv, (w, h), flags=cv2.INTER_LINEAR
            )
            corridor_unwarped = _gu.download()
        else:
            corridor_unwarped = self.bev.unwarp(bev_canvas, w, h)

        # ── Alpha-blend corridor onto original frame (GPU if available) ──
        if self._cuda_ok:
            _go = cv2.cuda_GpuMat(); _go.upload(original.astype(np.uint8))
            _gcr = cv2.cuda_GpuMat(); _gcr.upload(corridor_unwarped)
            _gout = cv2.cuda_GpuMat()
            cv2.cuda.addWeighted(
                _go,  1.0 - self.CORRIDOR_ALPHA,
                _gcr, self.CORRIDOR_ALPHA,
                0, _gout
            )
            annotated = _gout.download()
        else:
            annotated = cv2.addWeighted(
                original.astype(np.uint8), 1.0 - self.CORRIDOR_ALPHA,
                corridor_unwarped,          self.CORRIDOR_ALPHA,
                0
            )

        # Project corridor polygon vertices back to original space for reference
        corridor_pts_orig = None
        try:
            poly_h = poly_pts.reshape(-1, 1, 2).astype(np.float32)
            corridor_pts_orig = cv2.perspectiveTransform(poly_h, self.bev.M_inv)
            corridor_pts_orig = corridor_pts_orig.reshape(-1, 2).astype(np.int32)
        except Exception:
            pass

        return annotated, corridor_pts_orig

    # ------------------------------------------------------------------
    # Step 4: Lane offset (for LDW)
    # ------------------------------------------------------------------

    def _compute_lane_offset(
        self,
        left_fit : Optional[np.ndarray],
        right_fit: Optional[np.ndarray],
        frame_h  : int,
    ) -> Tuple[float, int]:
        """
        Compute normalised lane offset.

        Convention:
          offset = (vehicle_center_x - lane_center_x) / (lane_half_width_x)
          Positive → vehicle drifting RIGHT
          Negative → vehicle drifting LEFT
          Range: typically [-1, +1]

        The vehicle center is assumed to be the horizontal midpoint of the
        BEV frame (camera on dashboard centre line).

        Returns
        -------
        offset : float  (0.0 if both lanes missing)
        lane_w : int    (BEV pixels; 0 if missing)
        """
        if left_fit is None and right_fit is None:
            return 0.0, 0

        # Evaluate polynomials at 80 % of frame height (near vehicle)
        eval_yn   = 0.80
        vehicle_x = self.frame_w / 2.0

        if left_fit is not None:
            lx = float(np.polyval(left_fit, eval_yn))
        else:
            rx = float(np.polyval(right_fit, eval_yn))
            lx = rx - 2 * int(self.frame_w * 0.15)

        if right_fit is not None:
            rx = float(np.polyval(right_fit, eval_yn))
        else:
            rx = lx + 2 * int(self.frame_w * 0.15)

        lane_center  = (lx + rx) / 2.0
        lane_half_w  = max((rx - lx) / 2.0, 1.0)
        lane_width_px = int(rx - lx)

        offset = (vehicle_x - lane_center) / lane_half_w
        offset = float(np.clip(offset, -2.0, 2.0))   # safety clamp

        return offset, lane_width_px

    def _classify_offset(self, offset: float) -> str:
        """Map raw offset to SAFE / WARNING / CRITICAL."""
        abs_off = abs(offset)
        if abs_off >= self.OFFSET_CRITICAL_THRESHOLD:
            return 'CRITICAL'
        elif abs_off >= self.OFFSET_WARNING_THRESHOLD:
            return 'WARNING'
        return 'SAFE'


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)

    detector = LaneDetectorV4(frame_w=1280, frame_h=720)

    if len(sys.argv) > 1:
        cap = cv2.VideoCapture(sys.argv[1])
        while cap.isOpened():
            ok, frame = cap.read()
            if not ok:
                break
            frame = cv2.resize(frame, (1280, 720))
            res = detector.process_frame(frame)
            cv2.imshow("V4 Lane", res['annotated_frame'])
            cv2.imshow("BEV Debug", res['bev_debug'])
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
        cap.release()
        cv2.destroyAllWindows()
    else:
        # Single dummy frame smoke-test
        dummy = np.zeros((720, 1280, 3), dtype=np.uint8)
        res = detector.process_frame(dummy)
        print(f"Smoke-test OK — has_lane={res['has_lane']}  offset={res['lane_offset']:.3f}")
