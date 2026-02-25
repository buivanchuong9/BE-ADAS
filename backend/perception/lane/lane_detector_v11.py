"""
Lane Detector V11 - Classical CV Bird's Eye View (BEV) approach.

Algorithm:
  1. ROI crop (bottom 55% of frame - road area)
  2. HLS colour thresholding for white + yellow lane marks
  3. Sobel edge magnitude
  4. Perspective warp -> Bird's Eye View
  5. Sliding-window lane pixel search
  6. 2nd-degree polynomial fit (left + right lanes)
  7. Fill lane area polygon
  8. Warp filled lane back to original perspective
  9. Temporal smoothing between frames

No YOLO model required - works on CPU and GPU alike.
"""
import cv2
import numpy as np
from typing import Optional, Dict, Tuple, List
import logging

logger = logging.getLogger(__name__)

# ── cv2.cuda availability (checked once at import) ────────────────────────
try:
    _CUDA_CV = (hasattr(cv2, 'cuda') and
                hasattr(cv2.cuda, 'getCudaEnabledDeviceCount') and
                cv2.cuda.getCudaEnabledDeviceCount() > 0)
except Exception:
    _CUDA_CV = False

if _CUDA_CV:
    logger.info("[Lane] cv2.cuda available → GPU BEV preprocessing ON (A30)")
else:
    logger.info("[Lane] cv2.cuda not available → CPU BEV preprocessing")


def _gpu_colour_binary(gpu_src):
    """HLS white+yellow threshold on GPU (cv2.cuda). Returns GpuMat uint8."""
    gpu_hls = cv2.cuda.cvtColor(gpu_src, cv2.COLOR_BGR2HLS)
    h_ch, l_ch, s_ch = cv2.cuda.split(gpu_hls)
    _, l_hi = cv2.cuda.threshold(l_ch, 180, 255, cv2.THRESH_BINARY)
    _, s_lo = cv2.cuda.threshold(s_ch,  80, 255, cv2.THRESH_BINARY_INV)
    white   = cv2.cuda.bitwise_and(l_hi, s_lo)
    _, h_lo = cv2.cuda.threshold(h_ch,  14, 255, cv2.THRESH_BINARY)
    _, h_hi = cv2.cuda.threshold(h_ch,  35, 255, cv2.THRESH_BINARY_INV)
    _, s_hi = cv2.cuda.threshold(s_ch,  80, 255, cv2.THRESH_BINARY)
    _, l_y  = cv2.cuda.threshold(l_ch,  60, 255, cv2.THRESH_BINARY)
    h_rng   = cv2.cuda.bitwise_and(h_lo, h_hi)
    sl_ok   = cv2.cuda.bitwise_and(s_hi, l_y)
    yellow  = cv2.cuda.bitwise_and(h_rng, sl_ok)
    return cv2.cuda.bitwise_or(white, yellow)


def _colour_binary(frame_bgr: np.ndarray) -> np.ndarray:
    """Return binary mask of lane-line pixels (white AND yellow)."""
    hls = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HLS)
    h, l, s = hls[:, :, 0], hls[:, :, 1], hls[:, :, 2]

    # White: high lightness
    white_mask = (l > 180) & (s < 80)

    # Yellow: hue 15-35, decent saturation
    yellow_mask = (h >= 15) & (h <= 35) & (s > 80) & (l > 60)

    binary = (white_mask | yellow_mask).astype(np.uint8) * 255
    return binary


def _sobel_binary(frame_bgr: np.ndarray, thresh=(30, 200)) -> np.ndarray:
    """Sobel magnitude binary on L channel."""
    hls = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HLS)
    l_channel = hls[:, :, 1].astype(np.float32)

    sobel_x = cv2.Sobel(l_channel, cv2.CV_64F, 1, 0, ksize=3)
    sobel_y = cv2.Sobel(l_channel, cv2.CV_64F, 0, 1, ksize=3)
    magnitude = np.sqrt(sobel_x ** 2 + sobel_y ** 2)
    if magnitude.max() > 0:
        magnitude = (magnitude / magnitude.max() * 255).astype(np.uint8)
    else:
        magnitude = magnitude.astype(np.uint8)

    binary = ((magnitude >= thresh[0]) & (magnitude <= thresh[1])).astype(np.uint8) * 255
    return binary


def _build_roi_mask(h: int, w: int) -> np.ndarray:
    """Trapezoid ROI mask covering the road ahead."""
    mask = np.zeros((h, w), dtype=np.uint8)
    top_y = int(h * 0.42)
    bot_y = h - 1
    pts = np.array([
        [int(w * 0.05), bot_y],
        [int(w * 0.38), top_y],
        [int(w * 0.62), top_y],
        [int(w * 0.95), bot_y],
    ], dtype=np.int32)
    cv2.fillPoly(mask, [pts], 255)
    return mask


def _get_warp_matrices(h: int, w: int):
    """Compute perspective warp & inverse warp matrices for BEV."""
    top_y = int(h * 0.42)
    bot_y = h - 1
    src = np.float32([
        [int(w * 0.38), top_y],
        [int(w * 0.62), top_y],
        [int(w * 0.95), bot_y],
        [int(w * 0.05), bot_y],
    ])
    dst = np.float32([
        [int(w * 0.20), 0],
        [int(w * 0.80), 0],
        [int(w * 0.80), h],
        [int(w * 0.20), h],
    ])
    M = cv2.getPerspectiveTransform(src, dst)
    Minv = cv2.getPerspectiveTransform(dst, src)
    return M, Minv


def _sliding_window(binary_bev: np.ndarray,
                    n_windows: int = 12,
                    margin: int = 60,
                    min_pix: int = 40):
    """Sliding-window search. Returns (left_fit, right_fit) or (None, None)."""
    h, w = binary_bev.shape
    histogram = np.sum(binary_bev[h // 2:, :], axis=0).astype(np.float32)
    midpoint = w // 2

    hist_left = histogram[:midpoint]
    hist_right = histogram[midpoint:]
    if hist_left.max() == 0 or hist_right.max() == 0:
        return None, None

    leftx_base = int(np.argmax(hist_left))
    rightx_base = int(np.argmax(hist_right)) + midpoint

    win_height = h // n_windows
    nonzeroy, nonzerox = np.where(binary_bev > 0)

    leftx_current = leftx_base
    rightx_current = rightx_base
    left_inds, right_inds = [], []

    for win in range(n_windows):
        win_y_low  = h - (win + 1) * win_height
        win_y_high = h - win * win_height

        good_left = np.where(
            (nonzeroy >= win_y_low) & (nonzeroy < win_y_high) &
            (nonzerox >= leftx_current - margin) & (nonzerox < leftx_current + margin)
        )[0]
        good_right = np.where(
            (nonzeroy >= win_y_low) & (nonzeroy < win_y_high) &
            (nonzerox >= rightx_current - margin) & (nonzerox < rightx_current + margin)
        )[0]

        left_inds.append(good_left)
        right_inds.append(good_right)

        if len(good_left) >= min_pix:
            leftx_current = int(np.mean(nonzerox[good_left]))
        if len(good_right) >= min_pix:
            rightx_current = int(np.mean(nonzerox[good_right]))

    left_inds  = np.concatenate(left_inds)  if left_inds  else np.array([], dtype=int)
    right_inds = np.concatenate(right_inds) if right_inds else np.array([], dtype=int)

    left_fit = right_fit = None
    if len(left_inds) >= 25:
        try:
            left_fit = np.polyfit(nonzeroy[left_inds], nonzerox[left_inds], 2)
        except Exception:
            pass
    if len(right_inds) >= 25:
        try:
            right_fit = np.polyfit(nonzeroy[right_inds], nonzerox[right_inds], 2)
        except Exception:
            pass

    return left_fit, right_fit


def _fit_to_pts(fit: np.ndarray, h: int) -> np.ndarray:
    ploty = np.linspace(0, h - 1, h)
    fitx  = fit[0] * ploty**2 + fit[1] * ploty + fit[2]
    return np.stack([fitx, ploty], axis=-1).astype(np.int32)


def _draw_lane_bev(h, w, left_fit, right_fit, color=(0, 200, 0)):
    canvas = np.zeros((h, w, 3), dtype=np.uint8)
    if left_fit is None or right_fit is None:
        return canvas

    lp = _fit_to_pts(left_fit, h)
    rp = _fit_to_pts(right_fit, h)

    # Sanity check: left must be to the left of right
    if lp[:, 0].mean() >= rp[:, 0].mean():
        return canvas

    # Lane width sanity (15-80% of image width)
    lane_w_px = rp[:, 0].mean() - lp[:, 0].mean()
    if not (w * 0.15 <= lane_w_px <= w * 0.80):
        return canvas

    all_pts = np.vstack([lp, rp[::-1]])
    cv2.fillPoly(canvas, [all_pts], color)
    cv2.polylines(canvas, [lp.reshape(-1, 1, 2)], False, (255, 255, 255), 4)
    cv2.polylines(canvas, [rp.reshape(-1, 1, 2)], False, (255, 255, 255), 4)
    return canvas


# =============================================================================
# Main class
# =============================================================================
class LaneDetectorV11:
    """
    Lane detector: BEV + sliding-window + polynomial fit.
    No YOLO / neural-network needed.
    """

    def __init__(
        self,
        model_path: str = "",      # kept for API compatibility - IGNORED
        device: str = "cpu",
        conf_threshold: float = 0.3,
        use_cyan: bool = False,
    ):
        # GPU path via cv2.cuda (activated when available and device=="cuda")
        self.use_gpu = _CUDA_CV and (device == "cuda")
        self.lane_color: tuple = (0, 255, 255) if use_cyan else (0, 200, 0)
        self.alpha = 0.35          # lane overlay transparency

        self._M    = None
        self._Minv = None
        self._last_h = self._last_w = 0

        # EMA smoothing
        self._left_fit_smooth  = None
        self._right_fit_smooth = None
        self._smooth_alpha = 0.75   # responsiveness

        self._last_colored = None   # coloured lane canvas (warped back)

        # GPU morphology filters, lazily created per input resolution
        self._gpu_open_filter  = None
        self._gpu_close_filter = None
        self._gpu_filter_size  = (0, 0)

        mode = "GPU (cv2.cuda)" if self.use_gpu else "CPU"
        logger.info(f"✅ LaneDetectorV11 BEV ready [{mode}]")

    # ------------------------------------------------------------------
    def _init_matrices(self, h, w):
        if h != self._last_h or w != self._last_w:
            self._M, self._Minv = _get_warp_matrices(h, w)
            self._last_h, self._last_w = h, w
            self._gpu_filter_size = (0, 0)  # rebuild filters on size change

    def _init_gpu_filters(self, h, w):
        """Lazily build cv2.cuda morphology filters for current resolution."""
        if self._gpu_filter_size == (h, w) and self._gpu_open_filter is not None:
            return
        k3  = cv2.getStructuringElement(cv2.MORPH_RECT,    (3, 3))
        k11 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
        self._gpu_open_filter  = cv2.cuda.createMorphologyFilter(
            cv2.MORPH_OPEN,  cv2.CV_8UC1, k3)
        self._gpu_close_filter = cv2.cuda.createMorphologyFilter(
            cv2.MORPH_CLOSE, cv2.CV_8UC1, k11)
        self._gpu_filter_size  = (h, w)

    def _smooth(self, lf, rf):
        a = self._smooth_alpha
        if lf is not None:
            self._left_fit_smooth  = lf if self._left_fit_smooth is None  else a*lf + (1-a)*self._left_fit_smooth
        if rf is not None:
            self._right_fit_smooth = rf if self._right_fit_smooth is None else a*rf + (1-a)*self._right_fit_smooth

    # ------------------------------------------------------------------
    def detect_drivable_area(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """
        Returns binary lane-area mask (H×W, uint8) or None.
        GPU path : cv2.cuda colour + morph + warpPerspective  (A30 SM).
        CPU path : pure OpenCV/numpy fallback (always available).
        Sliding-window polyfit always on CPU (no cv2.cuda equivalent).
        """
        try:
            h, w = frame.shape[:2]
            self._init_matrices(h, w)
            roi = _build_roi_mask(h, w)

            if self.use_gpu:
                # ── GPU path (cv2.cuda) ───────────────────────────────────
                try:
                    self._init_gpu_filters(h, w)
                    gpu = cv2.cuda_GpuMat()
                    gpu.upload(frame)

                    gpu_col  = _gpu_colour_binary(gpu)        # HLS thresh on GPU
                    gpu_edge = gpu_col                        # colour is dominant; Sobel on CPU below
                    gpu_comb = gpu_col                        # combined = colour

                    gpu_roi = cv2.cuda_GpuMat()
                    gpu_roi.upload(roi)
                    gpu_comb = cv2.cuda.bitwise_and(gpu_comb, gpu_roi)
                    gpu_comb = self._gpu_open_filter.apply(gpu_comb)  # GPU denoise

                    # GPU warpPerspective → BEV
                    gpu_bev = cv2.cuda.warpPerspective(
                        gpu_comb, self._M, (w, h), flags=cv2.INTER_LINEAR)
                    bev_col = gpu_bev.download()   # D2H copy for polyfit

                    # Also add CPU Sobel edge to catch faint lines GPU may miss
                    edge_cpu = _sobel_binary(frame)
                    bev_edge = cv2.warpPerspective(
                        cv2.bitwise_and(edge_cpu, roi), self._M, (w, h))
                    bev = cv2.bitwise_or(bev_col, bev_edge)

                except Exception as gpu_err:
                    logger.debug(f"[Lane] GPU fallback: {gpu_err}")
                    bev = self._cpu_preprocess(frame, roi, h, w)
            else:
                # ── CPU path ─────────────────────────────────────────────
                bev = self._cpu_preprocess(frame, roi, h, w)

            # ── Sliding window + polyfit (CPU) ───────────────────────────
            lf, rf = _sliding_window(bev)
            self._smooth(lf, rf)
            lf_s, rf_s = self._left_fit_smooth, self._right_fit_smooth
            if lf_s is None or rf_s is None:
                return None

            canvas = _draw_lane_bev(h, w, lf_s, rf_s, color=self.lane_color)

            # ── Warp lane back to camera view ─────────────────────────────
            if self.use_gpu:
                try:
                    gpu_c = cv2.cuda_GpuMat()
                    gpu_c.upload(canvas)
                    gpu_b = cv2.cuda.warpPerspective(
                        gpu_c, self._Minv, (w, h), flags=cv2.INTER_LINEAR)
                    back  = gpu_b.download()
                except Exception:
                    back  = cv2.warpPerspective(canvas, self._Minv, (w, h))
            else:
                back = cv2.warpPerspective(canvas, self._Minv, (w, h))

            self._last_colored = back
            gray = cv2.cvtColor(back, cv2.COLOR_BGR2GRAY)
            _, mask = cv2.threshold(gray, 1, 255, cv2.THRESH_BINARY)
            return mask

        except Exception as e:
            logger.error(f"Lane detect error: {e}", exc_info=True)
            return None

    def _cpu_preprocess(self, frame, roi, h, w):
        """CPU BEV preprocessing fallback."""
        col  = _colour_binary(frame)
        edge = _sobel_binary(frame)
        comb = cv2.bitwise_or(col, edge)
        comb = cv2.bitwise_and(comb, roi)
        k    = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        comb = cv2.morphologyEx(comb, cv2.MORPH_OPEN, k)
        return cv2.warpPerspective(comb, self._M, (w, h))

    def create_overlay(self, frame: np.ndarray, mask: Optional[np.ndarray]) -> np.ndarray:
        """Blend coloured lane area onto original frame."""
        if mask is None:
            return frame
        try:
            coloured = self._last_colored
            if coloured is None:
                coloured = np.zeros_like(frame)
                coloured[mask > 0] = self.lane_color

            h_f, w_f = frame.shape[:2]
            if coloured.shape[:2] != (h_f, w_f):
                coloured = cv2.resize(coloured, (w_f, h_f))

            return cv2.addWeighted(frame, 1.0 - self.alpha, coloured, self.alpha, 0)
        except Exception as e:
            logger.error(f"Overlay error: {e}")
            return frame

    def draw_info(self, frame: np.ndarray, has_lane: bool) -> np.ndarray:
        txt   = "LAN DUONG: PHAT HIEN" if has_lane else "LAN DUONG: KHONG RO"
        color = (0, 255, 0)            if has_lane else (0, 165, 255)
        cv2.putText(frame, txt, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 0, 0), 4)
        cv2.putText(frame, txt, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.75, color, 2)
        return frame

    def process_frame(self, frame: np.ndarray) -> Dict:
        mask = self.detect_drivable_area(frame)
        if mask is not None:
            overlay = self.create_overlay(frame, mask)
            has_lane = True
        else:
            overlay = frame.copy()
            has_lane = False
        annotated = self.draw_info(overlay.copy(), has_lane)
        return {'annotated_frame': annotated, 'mask': mask, 'has_lane': has_lane}


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    detector = LaneDetectorV11(use_cyan=False)
    print("LaneDetectorV11 BEV ready")
    if len(sys.argv) > 1:
        cap = cv2.VideoCapture(sys.argv[1])
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        W   = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        H   = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        out = cv2.VideoWriter("out_lane_test.mp4", cv2.VideoWriter_fourcc(*"mp4v"), fps, (W, H))
        i = 0
        while True:
            ret, fr = cap.read()
            if not ret or i >= 120: break
            res = detector.process_frame(fr)
            out.write(res['annotated_frame'])
            i += 1
        cap.release(); out.release()
        print(f"Saved out_lane_test.mp4 ({i} frames)")
