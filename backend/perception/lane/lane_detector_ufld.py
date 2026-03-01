

import cv2
import numpy as np
import torch
import torch.nn.functional as F
from pathlib import Path
from typing import Optional, Dict, List, Tuple, TYPE_CHECKING
from collections import deque
import logging

# Optional CUDA preprocessor import (for zero-copy mode)
if TYPE_CHECKING:
    from backend.perception.cuda_preprocess import CUDAPreprocessor

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lightweight backbone (ResNet-18 based) for UFLD
# ---------------------------------------------------------------------------

class ResNetBlock(torch.nn.Module):
    """Basic ResNet block (2x conv3x3)."""
    def __init__(self, in_ch: int, out_ch: int, stride: int = 1):
        super().__init__()
        self.conv1 = torch.nn.Conv2d(in_ch, out_ch, 3, stride, 1, bias=False)
        self.bn1 = torch.nn.BatchNorm2d(out_ch)
        self.conv2 = torch.nn.Conv2d(out_ch, out_ch, 3, 1, 1, bias=False)
        self.bn2 = torch.nn.BatchNorm2d(out_ch)
        self.relu = torch.nn.ReLU(inplace=True)
        
        self.downsample = None
        if stride != 1 or in_ch != out_ch:
            self.downsample = torch.nn.Sequential(
                torch.nn.Conv2d(in_ch, out_ch, 1, stride, bias=False),
                torch.nn.BatchNorm2d(out_ch),
            )
    
    def forward(self, x):
        identity = x
        out = self.relu(self.bn1(self.conv1(x)))
        out = self.bn2(self.conv2(out))
        if self.downsample is not None:
            identity = self.downsample(x)
        out += identity
        return self.relu(out)


class UFLDBackbone(torch.nn.Module):
    """
    Lightweight ResNet-18 style backbone for UFLD.
    Output: feature map at 1/32 resolution.
    """
    def __init__(self):
        super().__init__()
        self.stem = torch.nn.Sequential(
            torch.nn.Conv2d(3, 64, 7, 2, 3, bias=False),
            torch.nn.BatchNorm2d(64),
            torch.nn.ReLU(inplace=True),
            torch.nn.MaxPool2d(3, 2, 1),
        )
        self.layer1 = self._make_layer(64, 64, 2, stride=1)
        self.layer2 = self._make_layer(64, 128, 2, stride=2)
        self.layer3 = self._make_layer(128, 256, 2, stride=2)
        self.layer4 = self._make_layer(256, 512, 2, stride=2)
    
    def _make_layer(self, in_ch, out_ch, n_blocks, stride):
        layers = [ResNetBlock(in_ch, out_ch, stride)]
        for _ in range(1, n_blocks):
            layers.append(ResNetBlock(out_ch, out_ch))
        return torch.nn.Sequential(*layers)
    
    def forward(self, x):
        x = self.stem(x)
        x = self.layer1(x)
        x = self.layer2(x)
        x = self.layer3(x)
        x = self.layer4(x)
        return x


class UFLDHead(torch.nn.Module):
    """
    UFLD v2 classification head.
    
    For each of `num_lanes` lanes and `num_rows` row anchors,
    predicts which column (out of `num_cols` grid cells) the lane passes through.
    An extra "no lane" class is appended.
    
    Output shape: (batch, num_lanes, num_rows, num_cols + 1)
    """
    def __init__(
        self,
        num_lanes: int = 4,
        num_rows: int = 72,
        num_cols: int = 200,
        feat_channels: int = 512,
        input_h: int = 320,
        input_w: int = 800,
        use_official_arch: bool = False,
    ):
        super().__init__()
        self.num_lanes = num_lanes
        self.num_rows = num_rows
        self.num_cols = num_cols
        self.use_official_arch = use_official_arch
        
        # Feature map size at 1/32
        feat_h = input_h // 32
        feat_w = input_w // 32
        
        if use_official_arch:
            # Official UFLD v2 architecture: 512 -> 8 channels, then flatten
            # input_dim = 8 * feat_h * feat_w = 8 * 9 * 25 = 1800 (for 288x800)
            # For 320x800: 8 * 10 * 25 = 2000
            self.pool = torch.nn.AdaptiveAvgPool2d((feat_h, feat_w))
            self.reduce = torch.nn.Conv2d(feat_channels, 8, 1, bias=False)
            feat_dim = 8 * feat_h * feat_w
        else:
            # Our original architecture
            feat_dim = feat_channels * feat_h * feat_w
            self.pool = torch.nn.AdaptiveAvgPool2d((feat_h, feat_w))
            self.reduce = None
        
        self.cls = torch.nn.Sequential(
            torch.nn.Linear(feat_dim, 2048),
            torch.nn.ReLU(inplace=True),
            torch.nn.Dropout(0.1),
            torch.nn.Linear(2048, num_lanes * num_rows * (num_cols + 1)),
        )
    
    def forward(self, feat):
        b = feat.shape[0]
        x = self.pool(feat)
        if self.reduce is not None:
            x = self.reduce(x)
        x = x.view(b, -1)
        x = self.cls(x)
        x = x.view(b, self.num_lanes, self.num_rows, self.num_cols + 1)
        return x


class UFLDNet(torch.nn.Module):
    """
    Complete UFLD v2 network: Backbone + Classification Head.
    """
    def __init__(
        self,
        num_lanes: int = 4,
        num_rows: int = 72,
        num_cols: int = 200,
        input_h: int = 320,
        input_w: int = 800,
        use_official_arch: bool = False,
    ):
        super().__init__()
        self.input_h = input_h
        self.input_w = input_w
        self.num_lanes = num_lanes
        self.num_rows = num_rows
        self.num_cols = num_cols
        
        self.backbone = UFLDBackbone()
        self.head = UFLDHead(
            num_lanes=num_lanes,
            num_rows=num_rows,
            num_cols=num_cols,
            feat_channels=512,
            input_h=input_h,
            input_w=input_w,
            use_official_arch=use_official_arch,
        )
    
    def forward(self, x):
        feat = self.backbone(x)
        return self.head(feat)


# ---------------------------------------------------------------------------
# Row anchor positions (normalized y-coordinates)
# TuSimple style: 72 rows from y=0.4 to y=1.0 (bottom 60% of image)
# ---------------------------------------------------------------------------

def _generate_row_anchors(num_rows: int = 72, start: float = 0.4, end: float = 1.0) -> np.ndarray:
    """Generate evenly-spaced row anchor positions in [start, end]."""
    return np.linspace(start, end, num_rows)


# ---------------------------------------------------------------------------
# Lane Smoother (EMA per lane, same as V4)
# ---------------------------------------------------------------------------

class LaneSmoother:
    """Per-lane point smoother with EMA."""
    
    def __init__(self, num_lanes: int = 4, alpha: float = 0.3, max_lost: int = 5):
        self.alpha = alpha
        self.max_lost = max_lost
        self.num_lanes = num_lanes
        self._ema: List[Optional[np.ndarray]] = [None] * num_lanes
        self._lost: List[int] = [0] * num_lanes
    
    def update(self, lane_idx: int, points: Optional[np.ndarray]) -> Optional[np.ndarray]:
        """Update lane with new points (Nx2) or None if not detected."""
        if points is None or len(points) < 2:
            self._lost[lane_idx] += 1
            if self._lost[lane_idx] > self.max_lost:
                self._ema[lane_idx] = None
            return self._ema[lane_idx]
        
        self._lost[lane_idx] = 0
        if self._ema[lane_idx] is None or self._ema[lane_idx].shape != points.shape:
            self._ema[lane_idx] = points.copy()
        else:
            self._ema[lane_idx] = (
                self.alpha * points + (1 - self.alpha) * self._ema[lane_idx]
            )
        return self._ema[lane_idx]
    
    def reset(self):
        self._ema = [None] * self.num_lanes
        self._lost = [0] * self.num_lanes


# ---------------------------------------------------------------------------
# Main UFLD Lane Detector
# ---------------------------------------------------------------------------

class UFLDLaneDetector:
    """
    Ultra Fast Lane Detection v2 — Production Lane Detector.
    
    Drop-in replacement cho LaneDetectorV4 (cùng interface `process_frame`).
    
    Modes:
        1. 'pretrained' (default): Download/sử dụng TuSimple pretrained weights
        2. 'custom': Load custom .pt/.onnx model
        3. 'untrained': Random weights (cho development/testing)
    
    Usage::
    
        detector = UFLDLaneDetector(device='cuda')
        result = detector.process_frame(frame)
        # result keys: annotated_frame, has_lane, lane_offset, offset_level, ...
    """
    
    # Lane colors (BGR) — left-to-right: Red, Green, Blue, Yellow
    LANE_COLORS = [
        (60, 60, 220),    # Left far  — đỏ
        (60, 220, 60),    # Left near — xanh lá
        (220, 180, 60),   # Right near — xanh dương
        (60, 220, 220),   # Right far  — vàng
    ]
    
    # Corridor fill settings
    CORRIDOR_COLOR_BGR = (0, 200, 60)   # Xanh lá (same as V4)
    CORRIDOR_ALPHA = 0.35
    
    # Lane offset thresholds (same as V4)
    OFFSET_WARNING_THRESHOLD  = 0.35
    OFFSET_CRITICAL_THRESHOLD = 0.60
    
    # Default UFLD configuration
    DEFAULT_NUM_LANES = 4        # TuSimple: 4 lanes
    DEFAULT_NUM_ROWS  = 72       # 72 row anchors
    DEFAULT_NUM_COLS  = 200      # 200 column grid cells
    DEFAULT_INPUT_H   = 320      # Network input height
    DEFAULT_INPUT_W   = 800      # Network input width
    
    def __init__(
        self,
        model_path: Optional[str] = None,
        device: str = "cuda",
        num_lanes: int = DEFAULT_NUM_LANES,
        num_rows: int = DEFAULT_NUM_ROWS,
        num_cols: int = DEFAULT_NUM_COLS,
        input_h: int = DEFAULT_INPUT_H,
        input_w: int = DEFAULT_INPUT_W,
        conf_threshold: float = 0.5,
        smooth_alpha: float = 0.3,
        cuda_preprocessor: Optional["CUDAPreprocessor"] = None,
    ):
        """
        Args:
            model_path: Path to model (.pt/.onnx/.pth). None = untrained (random weights).
            device: 'cuda' or 'cpu'
            num_lanes: Number of lanes to detect (TuSimple=4, CULane=4-6)
            num_rows: Row anchor count
            num_cols: Column grid resolution
            input_h: Network input height
            input_w: Network input width
            conf_threshold: Minimum confidence to count a lane as detected
            smooth_alpha: EMA smoothing factor (lower = smoother)
            cuda_preprocessor: Optional shared CUDAPreprocessor for zero-copy GpuMat reuse
        """
        self.device = device
        self.num_lanes = num_lanes
        self.num_rows = num_rows
        self.num_cols = num_cols
        self.input_h = input_h
        self.input_w = input_w
        self.conf_threshold = conf_threshold
        
        # External CUDA preprocessor for zero-copy mode
        self._cuda_preprocessor = cuda_preprocessor
        
        # Check CUDA
        if device == "cuda" and not torch.cuda.is_available():
            logger.warning("⚠️ CUDA không khả dụng, chuyển sang CPU")
            self.device = "cpu"
        
        if self.device == "cuda":
            torch.set_float32_matmul_precision('high')
            torch.backends.cudnn.benchmark = True
        
        # Row anchors (normalized y positions)
        self.row_anchors = _generate_row_anchors(num_rows)
        
        # Lane smoother
        self._smoother = LaneSmoother(num_lanes, alpha=smooth_alpha)
        
        # Frame counter
        self._frame_count = 0
        
        # Load model
        self.model = None
        self._onnx_session = None
        self._model_format = 'pytorch'  # 'pytorch', 'torchscript', 'onnx'
        
        self._load_model(model_path)
        
        logger.info(
            f"[UFLD] Initialized — {num_lanes} lanes, {num_rows} rows, "
            f"{num_cols} cols, input={input_w}×{input_h}, "
            f"device={self.device}, conf={conf_threshold}"
        )
    
    def _load_model(self, model_path: Optional[str]):
        """Load UFLD model from file or create untrained."""
        if model_path is None:
            # No pretrained model → create untrained network
            logger.info("[UFLD] No model_path provided — using untrained network (for dev/testing)")
            self.model = UFLDNet(
                num_lanes=self.num_lanes,
                num_rows=self.num_rows,
                num_cols=self.num_cols,
                input_h=self.input_h,
                input_w=self.input_w,
            ).to(self.device).eval()
            self._model_format = 'pytorch'
            return
        
        model_file = Path(model_path)
        if not model_file.exists():
            logger.warning(f"[UFLD] Model not found: {model_path} — using untrained network")
            self.model = UFLDNet(
                num_lanes=self.num_lanes,
                num_rows=self.num_rows,
                num_cols=self.num_cols,
                input_h=self.input_h,
                input_w=self.input_w,
            ).to(self.device).eval()
            self._model_format = 'pytorch'
            return
        
        suffix = model_file.suffix.lower()
        
        if suffix == '.onnx':
            self._load_onnx(model_path)
        elif suffix in ('.pt', '.torchscript'):
            self._load_torchscript_or_pth(model_path)
        elif suffix == '.pth':
            self._load_state_dict(model_path)
        else:
            logger.warning(f"[UFLD] Unknown model format: {suffix}, trying TorchScript...")
            self._load_torchscript_or_pth(model_path)
    
    def _load_onnx(self, model_path: str):
        """Load ONNX model via onnxruntime."""
        try:
            import onnxruntime as ort
            providers = ['CUDAExecutionProvider', 'CPUExecutionProvider'] if self.device == 'cuda' else ['CPUExecutionProvider']
            self._onnx_session = ort.InferenceSession(model_path, providers=providers)
            self._model_format = 'onnx'
            logger.info(f"[UFLD] ✅ Loaded ONNX model: {Path(model_path).name}")
        except Exception as e:
            logger.warning(f"[UFLD] ONNX load failed ({e}), falling back to untrained")
            self.model = UFLDNet(
                num_lanes=self.num_lanes, num_rows=self.num_rows,
                num_cols=self.num_cols, input_h=self.input_h, input_w=self.input_w,
            ).to(self.device).eval()
            self._model_format = 'pytorch'
    
    def _load_torchscript_or_pth(self, model_path: str):
        """Load TorchScript or .pt model."""
        try:
            self.model = torch.jit.load(model_path, map_location=self.device)
            self.model.eval()
            self._model_format = 'torchscript'
            logger.info(f"[UFLD] ✅ Loaded TorchScript model: {Path(model_path).name}")
        except Exception:
            # Try as state dict
            self._load_state_dict(model_path)
    
    def _load_state_dict(self, model_path: str):
        """Load PyTorch state dict (.pth) - auto-detect architecture."""
        try:
            state = torch.load(model_path, map_location=self.device, weights_only=False)
            # Handle both raw state dict and wrapped format
            if 'model' in state:
                state = state['model']
            elif 'state_dict' in state:
                state = state['state_dict']
            
            # Detect official UFLD v2 architecture from checkpoint shape
            # Official TuSimple: cls.0.weight = [2048, 1800] → input 288x800, 56 rows, 100 cols
            # Official CULane: different dims
            cls_weight_key = None
            for key in state.keys():
                if 'cls.0.weight' in key or key == 'cls.0.weight':
                    cls_weight_key = key
                    break
            
            if cls_weight_key and state[cls_weight_key].shape[1] == 1800:
                # Official UFLD v2 TuSimple format detected!
                logger.info("[UFLD] Detected official UFLD v2 TuSimple checkpoint")
                # Use official TuSimple settings
                self.input_h = 288
                self.input_w = 800
                self.num_rows = 56
                self.num_cols = 100
                self.num_lanes = 4
                # Update row anchors for TuSimple 56 rows
                self._row_anchors = _generate_row_anchors(self.num_rows, start=0.42, end=1.0)
                
                # Create model with official architecture
                self.model = UFLDNet(
                    num_lanes=self.num_lanes, num_rows=self.num_rows,
                    num_cols=self.num_cols, input_h=self.input_h, input_w=self.input_w,
                    use_official_arch=True,
                ).to(self.device)
                
                # Map official keys to our architecture
                new_state = self._convert_official_state_dict(state)
                self.model.load_state_dict(new_state, strict=False)
                logger.info(f"[UFLD] ✅ Loaded official TuSimple model: {Path(model_path).name}")
            else:
                # Our custom format
                self.model = UFLDNet(
                    num_lanes=self.num_lanes, num_rows=self.num_rows,
                    num_cols=self.num_cols, input_h=self.input_h, input_w=self.input_w,
                ).to(self.device)
                self.model.load_state_dict(state, strict=False)
                logger.info(f"[UFLD] ✅ Loaded custom state dict: {Path(model_path).name}")
            
            self.model.eval()
            self._model_format = 'pytorch'
            
        except Exception as e:
            logger.warning(f"[UFLD] State dict load failed ({e}), using untrained")
            self.model = UFLDNet(
                num_lanes=self.num_lanes, num_rows=self.num_rows,
                num_cols=self.num_cols, input_h=self.input_h, input_w=self.input_w,
            ).to(self.device).eval()
            self._model_format = 'pytorch'
    
    def _convert_official_state_dict(self, state: dict) -> dict:
        """Convert official UFLD v2 state dict to our architecture."""
        new_state = {}
        
        # Official UFLD v2 key mapping:
        # model.features.* -> backbone.*
        # model.pool -> head.pool (we don't use this)
        # model.cls.* -> head.cls.*
        # aux_* -> ignored (auxiliary segmentation head)
        
        key_mapping = {
            'model.features.0': 'backbone.stem.0',  # conv1
            'model.features.1': 'backbone.stem.1',  # bn1
            # layer1: features.4.0, features.4.1
            # layer2: features.5.0, features.5.1
            # layer3: features.6.0, features.6.1  
            # layer4: features.7.0, features.7.1
        }
        
        for old_key, value in state.items():
            new_key = None
            
            # Skip auxiliary head
            if old_key.startswith('aux_'):
                continue
            
            # Direct backbone mapping for ResNet structure
            if old_key.startswith('model.features.'):
                # Parse: model.features.X.Y.layer_name
                parts = old_key.replace('model.features.', '').split('.')
                if len(parts) >= 1:
                    feat_idx = int(parts[0])
                    rest = '.'.join(parts[1:])
                    
                    # Map feature indices to our layer names
                    # features.0 = conv1, features.1 = bn1, features.3 = maxpool
                    # features.4 = layer1, features.5 = layer2, etc.
                    if feat_idx == 0:
                        new_key = f'backbone.stem.0.{rest}' if rest else 'backbone.stem.0.weight'
                    elif feat_idx == 1:
                        new_key = f'backbone.stem.1.{rest}'
                    elif feat_idx >= 4 and feat_idx <= 7:
                        layer_idx = feat_idx - 3  # 4->1, 5->2, 6->3, 7->4
                        new_key = f'backbone.layer{layer_idx}.{rest}'
            
            # Classifier head
            elif old_key.startswith('model.cls.') or old_key.startswith('cls.'):
                suffix = old_key.replace('model.cls.', '').replace('cls.', '')
                new_key = f'head.cls.{suffix}'
            
            # Pool (if exists)
            elif 'pool' in old_key:
                continue  # Skip, we use AdaptiveAvgPool2d
            
            # Reduction conv (if exists)
            elif old_key.startswith('model.reduce') or old_key.startswith('reduce'):
                suffix = old_key.replace('model.reduce.', '').replace('reduce.', '')
                new_key = f'head.reduce.{suffix}' if suffix else 'head.reduce.weight'
            
            if new_key:
                new_state[new_key] = value
            elif not old_key.startswith('aux_'):
                # Keep as-is for any unmatched keys
                new_state[old_key] = value
        
        logger.info(f"[UFLD] Converted {len(new_state)}/{len(state)} keys from official format")
        return new_state
    
    # ------------------------------------------------------------------
    # Preprocessing — GPU-accelerated (cv2.cuda)
    # ------------------------------------------------------------------

    def _preprocess(self, frame: np.ndarray) -> torch.Tensor:
        """
        Preprocess frame for UFLD input — GPU-accelerated.

        Uses external CUDAPreprocessor if provided (zero-copy GpuMat reuse),
        otherwise falls back to internal GPU preprocessing.

        Steps:
            1. Crop bottom 60% of image (lanes are in lower part)
            2. GPU resize to (input_h, input_w)
            3. GPU colour conversion BGR → RGB
            4. Normalize: ImageNet mean/std
            5. Convert to NCHW tensor on CUDA
        """
        # Use shared CUDA preprocessor if available (zero-copy mode)
        if self._cuda_preprocessor is not None:
            return self._cuda_preprocessor.preprocess_lane(
                frame,
                crop_ratio=0.40,
                target_h=self.input_h,
                target_w=self.input_w,
            )
        
        # Fallback: internal preprocessing
        h, w = frame.shape[:2]

        # Crop top 40% (sky/horizon) — keep bottom 60% where lanes are
        crop_y = int(h * 0.40)
        cropped = frame[crop_y:, :, :]

        # --- GPU path: resize + BGR→RGB on GPU, one upload ------------------
        if self.device == "cuda" and hasattr(cv2, "cuda"):
            try:
                gpu_crop = cv2.cuda_GpuMat()
                gpu_crop.upload(cropped)
                gpu_resized = cv2.cuda.resize(
                    gpu_crop,
                    (self.input_w, self.input_h),
                    interpolation=cv2.INTER_LINEAR,
                )
                gpu_rgb = cv2.cuda.cvtColor(gpu_resized, cv2.COLOR_BGR2RGB)
                resized_rgb = gpu_rgb.download()   # pull back once
            except Exception:
                # Shouldn't happen; strict loader ensures cv2.cuda works
                resized = cv2.resize(cropped, (self.input_w, self.input_h),
                                     interpolation=cv2.INTER_LINEAR)
                resized_rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        else:
            resized = cv2.resize(cropped, (self.input_w, self.input_h),
                                 interpolation=cv2.INTER_LINEAR)
            resized_rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)

        # float32 [0,1] + ImageNet normalization
        rgb = resized_rgb.astype(np.float32) / 255.0
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std  = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        rgb = (rgb - mean) / std

        # HWC → CHW → NCHW  (direct to CUDA tensor)
        tensor = torch.from_numpy(rgb.transpose(2, 0, 1)).unsqueeze(0).to(self.device)
        return tensor
    
    def preprocess_from_gpu(self, gpu_frame: "cv2.cuda_GpuMat", frame_shape: Tuple[int, int, int]) -> torch.Tensor:
        """
        Preprocess from already-uploaded GpuMat (zero-copy entry point).
        
        Called by worker when frame is already on GPU.
        Avoids redundant CPU-GPU transfer.
        
        Args:
            gpu_frame: Frame already on GPU (from worker's frame_context)
            frame_shape: Original frame shape (h, w, c)
        
        Returns:
            Preprocessed tensor ready for inference
        """
        if self._cuda_preprocessor is not None:
            return self._cuda_preprocessor.preprocess_lane_from_gpu(
                gpu_frame, frame_shape,
                crop_ratio=0.40,
                target_h=self.input_h,
                target_w=self.input_w,
            )
        else:
            # No preprocessor, download and use regular path
            frame = gpu_frame.download()
            return self._preprocess(frame)
    
    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------
    
    @torch.no_grad()
    def _infer(self, tensor: torch.Tensor) -> np.ndarray:
        """
        Run UFLD inference.
        
        Returns: (num_lanes, num_rows, num_cols+1) numpy array of probabilities
        """
        if self._model_format == 'onnx' and self._onnx_session is not None:
            input_name = self._onnx_session.get_inputs()[0].name
            result = self._onnx_session.run(None, {input_name: tensor.cpu().numpy()})
            logits = result[0]  # (1, num_lanes, num_rows, num_cols+1)
        else:
            logits = self.model(tensor).cpu().numpy()  # (1, num_lanes, num_rows, num_cols+1)
        
        # Softmax over column dimension
        logits = logits[0]  # (num_lanes, num_rows, num_cols+1)
        # Numerical stable softmax
        exp_logits = np.exp(logits - np.max(logits, axis=-1, keepdims=True))
        probs = exp_logits / np.sum(exp_logits, axis=-1, keepdims=True)
        
        return probs
    
    # ------------------------------------------------------------------
    # Post-processing: convert row classification → lane points
    # ------------------------------------------------------------------
    
    def _decode_lanes(
        self, probs: np.ndarray, frame_h: int, frame_w: int
    ) -> List[Optional[np.ndarray]]:
        """
        Decode UFLD predictions to lane point coordinates.
        
        Args:
            probs: (num_lanes, num_rows, num_cols+1) — softmax output
            frame_h: Original frame height
            frame_w: Original frame width
        
        Returns:
            List of lane point arrays, each (N, 2) in original frame coordinates.
            None for lanes not detected.
        """
        crop_y = int(frame_h * 0.40)  # Same crop offset as preprocessing
        lane_h = frame_h - crop_y     # Height of cropped region
        
        lanes = []
        
        for lane_idx in range(self.num_lanes):
            lane_probs = probs[lane_idx]  # (num_rows, num_cols+1)
            
            # For each row: get predicted column (argmax) and confidence
            col_preds = np.argmax(lane_probs, axis=-1)       # (num_rows,)
            max_probs = np.max(lane_probs[:, :-1], axis=-1)  # (num_rows,) — exclude "no lane" class
            
            # Filter rows where lane is detected (not "no lane" class, high confidence)
            valid_mask = (col_preds < self.num_cols) & (max_probs > self.conf_threshold)
            
            if np.sum(valid_mask) < 2:
                lanes.append(None)
                continue
            
            # Convert to pixel coordinates
            valid_rows = np.where(valid_mask)[0]
            valid_cols = col_preds[valid_mask]
            valid_probs = lane_probs[valid_mask]  # (N, num_cols+1)
            
            # Sub-pixel refinement: expected value (weighted average of nearby columns)
            # Instead of hard argmax, compute weighted mean of top-k columns
            refined_cols = []
            for i, row_idx in enumerate(valid_rows):
                row_probs = valid_probs[i, :self.num_cols]  # exclude "no lane"
                col = valid_cols[i]
                # Weighted average in a window of ±5 around predicted column
                lo = max(0, col - 5)
                hi = min(self.num_cols, col + 6)
                window_probs = row_probs[lo:hi]
                window_cols = np.arange(lo, hi)
                if np.sum(window_probs) > 1e-6:
                    refined_col = np.average(window_cols, weights=window_probs)
                else:
                    refined_col = float(col)
                refined_cols.append(refined_col)
            
            # Map to original frame coordinates
            x_coords = np.array(refined_cols) / self.num_cols * frame_w
            y_coords = self.row_anchors[valid_rows] * lane_h + crop_y
            
            points = np.stack([x_coords, y_coords], axis=-1)  # (N, 2)
            
            # Smooth via EMA
            smoothed = self._smoother.update(lane_idx, points)
            lanes.append(smoothed)
        
        return lanes
    
    # ------------------------------------------------------------------
    # Find ego lanes (the two lanes closest to vehicle center)
    # ------------------------------------------------------------------
    
    def _find_ego_lanes(
        self, lanes: List[Optional[np.ndarray]], frame_w: int, frame_h: int
    ) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """
        Identify left and right ego lanes (closest to vehicle center).
        
        Returns: (left_lane_points, right_lane_points) — each (N,2) or None
        """
        center_x = frame_w / 2.0
        eval_y = frame_h * 0.80  # Evaluate near bottom
        
        left_lane = None
        right_lane = None
        left_dist = float('inf')
        right_dist = float('inf')
        
        for lane_pts in lanes:
            if lane_pts is None or len(lane_pts) < 2:
                continue
            
            # Find x at evaluation y (interpolate)
            y_vals = lane_pts[:, 1]
            x_vals = lane_pts[:, 0]
            
            # Find closest row to eval_y
            idx = np.argmin(np.abs(y_vals - eval_y))
            lane_x = x_vals[idx]
            
            diff = lane_x - center_x
            
            if diff < 0 and abs(diff) < left_dist:
                # Left of center
                left_dist = abs(diff)
                left_lane = lane_pts
            elif diff >= 0 and diff < right_dist:
                # Right of center
                right_dist = diff
                right_lane = lane_pts
        
        return left_lane, right_lane
    
    # ------------------------------------------------------------------
    # Lane offset computation (same convention as V4)
    # ------------------------------------------------------------------
    
    def _compute_lane_offset(
        self,
        left_lane: Optional[np.ndarray],
        right_lane: Optional[np.ndarray],
        frame_w: int,
        frame_h: int,
    ) -> Tuple[float, int]:
        """
        Compute normalized lane offset [-1, +1].
        Positive = drifting right, Negative = drifting left.
        """
        if left_lane is None and right_lane is None:
            return 0.0, 0
        
        center_x = frame_w / 2.0
        eval_y = frame_h * 0.80
        
        def _get_x_at_y(pts, y):
            idx = np.argmin(np.abs(pts[:, 1] - y))
            return pts[idx, 0]
        
        if left_lane is not None:
            lx = _get_x_at_y(left_lane, eval_y)
        else:
            rx = _get_x_at_y(right_lane, eval_y)
            lx = rx - frame_w * 0.30  # Assume standard lane width
        
        if right_lane is not None:
            rx = _get_x_at_y(right_lane, eval_y)
        else:
            rx = lx + frame_w * 0.30
        
        lane_center = (lx + rx) / 2.0
        lane_half_w = max((rx - lx) / 2.0, 1.0)
        lane_width_px = int(rx - lx)
        
        offset = (center_x - lane_center) / lane_half_w
        offset = float(np.clip(offset, -2.0, 2.0))
        
        return offset, lane_width_px
    
    def _classify_offset(self, offset: float) -> str:
        """Map raw offset to SAFE / WARNING / CRITICAL."""
        abs_off = abs(offset)
        if abs_off >= self.OFFSET_CRITICAL_THRESHOLD:
            return 'CRITICAL'
        elif abs_off >= self.OFFSET_WARNING_THRESHOLD:
            return 'WARNING'
        return 'SAFE'
    
    # ------------------------------------------------------------------
    # Overlay rendering
    # ------------------------------------------------------------------
    
    def _draw_overlay(
        self,
        frame: np.ndarray,
        lanes: List[Optional[np.ndarray]],
        left_lane: Optional[np.ndarray],
        right_lane: Optional[np.ndarray],
    ) -> np.ndarray:
        """
        Draw lane lines and corridor on frame — GPU blending when available.
        Returns annotated frame (copy).
        """
        annotated = frame.copy()

        # 1. Draw all detected lane lines
        for i, lane_pts in enumerate(lanes):
            if lane_pts is None or len(lane_pts) < 2:
                continue
            color = self.LANE_COLORS[i % len(self.LANE_COLORS)]
            pts = lane_pts.astype(np.int32)
            cv2.polylines(annotated, [pts], isClosed=False, color=color, thickness=3)
            for pt in pts:
                cv2.circle(annotated, tuple(pt), 4, color, -1)

        # 2. Fill corridor between ego lanes — GPU blend
        if (left_lane is not None and right_lane is not None
                and len(left_lane) >= 2 and len(right_lane) >= 2):
            left_sorted = left_lane[np.argsort(left_lane[:, 1])]
            right_sorted = right_lane[np.argsort(right_lane[:, 1])]

            corridor_pts = np.vstack([
                left_sorted,
                right_sorted[::-1],
            ]).astype(np.int32)

            overlay = frame.copy()
            cv2.fillPoly(overlay, [corridor_pts], self.CORRIDOR_COLOR_BGR)

            # GPU-accelerated addWeighted for corridor blending
            if self.device == "cuda" and hasattr(cv2, "cuda"):
                try:
                    gpu_ann = cv2.cuda_GpuMat()
                    gpu_ann.upload(annotated)
                    gpu_ov = cv2.cuda_GpuMat()
                    gpu_ov.upload(overlay)
                    alpha = self.CORRIDOR_ALPHA
                    gpu_blend = cv2.cuda.addWeighted(gpu_ann, 1.0 - alpha, gpu_ov, alpha, 0)
                    annotated = gpu_blend.download()
                except Exception:
                    annotated = cv2.addWeighted(
                        annotated, 1.0 - self.CORRIDOR_ALPHA,
                        overlay, self.CORRIDOR_ALPHA, 0,
                    )
            else:
                annotated = cv2.addWeighted(
                    annotated, 1.0 - self.CORRIDOR_ALPHA,
                    overlay, self.CORRIDOR_ALPHA, 0,
                )

        return annotated
    
    # ------------------------------------------------------------------
    # Main API — compatible with LaneDetectorV4
    # ------------------------------------------------------------------
    
    def process_frame(self, frame: np.ndarray) -> Dict:
        """
        Main processing entry point. Drop-in replacement for LaneDetectorV4.
        
        Returns
        -------
        dict with keys (compatible with LaneDetectorV4):
          annotated_frame : np.ndarray  — original frame with overlay
          bev_debug       : np.ndarray  — not applicable (zeros), kept for compat
          has_lane        : bool
          left_fit        : np.ndarray | None  — left ego lane points (N,2)
          right_fit       : np.ndarray | None  — right ego lane points (N,2)
          lane_offset     : float  — [-1, +1], positive = drifting right
          offset_level    : str    — 'SAFE' | 'WARNING' | 'CRITICAL'
          lane_width_px   : int
          corridor_pts    : np.ndarray | None
          left_lost       : int
          right_lost      : int
          num_lanes_detected : int  — total lanes found (UFLD specific)
          all_lanes       : list  — all detected lane point arrays (UFLD specific)
        """
        self._frame_count += 1
        h, w = frame.shape[:2]
        
        # 1. Preprocess
        tensor = self._preprocess(frame)
        
        # 2. UFLD inference
        probs = self._infer(tensor)
        
        # 3. Decode lanes
        lanes = self._decode_lanes(probs, h, w)
        
        # 4. Find ego lanes (left/right closest to center)
        left_lane, right_lane = self._find_ego_lanes(lanes, w, h)
        
        has_lane = (left_lane is not None) or (right_lane is not None)
        num_detected = sum(1 for l in lanes if l is not None)
        
        # 5. Lane offset
        lane_offset, lane_width_px = self._compute_lane_offset(left_lane, right_lane, w, h)
        offset_level = self._classify_offset(lane_offset)
        
        # 6. Render overlay
        annotated = self._draw_overlay(frame, lanes, left_lane, right_lane)
        
        # 7. Build corridor polygon for downstream (same format as V4)
        corridor_pts = None
        if left_lane is not None and right_lane is not None:
            left_sorted = left_lane[np.argsort(left_lane[:, 1])]
            right_sorted = right_lane[np.argsort(right_lane[:, 1])]
            corridor_pts = np.vstack([left_sorted, right_sorted[::-1]]).astype(np.int32)
        
        # BEV debug placeholder (UFLD doesn't use BEV transform)
        bev_debug = np.zeros((h, w), dtype=np.uint8)
        
        return {
            'annotated_frame': annotated,
            'bev_debug': bev_debug,
            'has_lane': has_lane,
            'left_fit': left_lane,       # NOTE: points (N,2), not polynomial coefficients
            'right_fit': right_lane,
            'lane_offset': lane_offset,
            'offset_level': offset_level,
            'lane_width_px': lane_width_px,
            'corridor_pts': corridor_pts,
            'left_lost': self._smoother._lost[0] if self.num_lanes > 0 else 0,
            'right_lost': self._smoother._lost[1] if self.num_lanes > 1 else 0,
            # UFLD-specific extras
            'num_lanes_detected': num_detected,
            'all_lanes': lanes,
        }
    
    def calibrate(self, src_pts: np.ndarray, dst_pts: np.ndarray) -> None:
        """Not applicable for UFLD (no BEV transform). Reset smoother only."""
        self._smoother.reset()


# ---------------------------------------------------------------------------
# Export utilities
# ---------------------------------------------------------------------------

def export_ufld_onnx(
    model_path: str,
    output_path: str,
    input_h: int = 320,
    input_w: int = 800,
    num_lanes: int = 4,
    num_rows: int = 72,
    num_cols: int = 200,
):
    """Export UFLD model to ONNX format."""
    net = UFLDNet(num_lanes, num_rows, num_cols, input_h, input_w)
    state = torch.load(model_path, map_location='cpu', weights_only=True)
    if 'model' in state:
        state = state['model']
    elif 'state_dict' in state:
        state = state['state_dict']
    net.load_state_dict(state, strict=False)
    net.eval()
    
    dummy = torch.randn(1, 3, input_h, input_w)
    torch.onnx.export(
        net, dummy, output_path,
        opset_version=17,
        input_names=['input'],
        output_names=['output'],
        dynamic_axes={'input': {0: 'batch'}, 'output': {0: 'batch'}},
    )
    logger.info(f"[UFLD] Exported ONNX: {output_path}")


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format='%(levelname)s | %(message)s')
    
    detector = UFLDLaneDetector(model_path=None, device='cuda')
    
    if len(sys.argv) > 1:
        cap = cv2.VideoCapture(sys.argv[1])
        while cap.isOpened():
            ok, frame = cap.read()
            if not ok:
                break
            frame = cv2.resize(frame, (1280, 720))
            res = detector.process_frame(frame)
            cv2.imshow("UFLD Lane", res['annotated_frame'])
            info = (
                f"Lanes: {res['num_lanes_detected']}  "
                f"Offset: {res['lane_offset']:.2f}  "
                f"Level: {res['offset_level']}"
            )
            print(f"\r{info}", end='', flush=True)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
        cap.release()
        cv2.destroyAllWindows()
    else:
        # Smoke test with dummy frame
        dummy = np.zeros((720, 1280, 3), dtype=np.uint8)
        result = detector.process_frame(dummy)
        print(f"✅ Smoke-test OK — has_lane={result['has_lane']}, "
              f"detected={result['num_lanes_detected']}, "
              f"offset={result['lane_offset']:.3f}")
