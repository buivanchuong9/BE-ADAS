import os
import logging
import numpy as np
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any
import torch

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Calibration Dataset for INT8 Quantization
# -----------------------------------------------------------------------------

class CalibrationDataset:
    """
    Generates calibration data for INT8 quantization.
    Uses random images or real video frames for accurate calibration.
    """
    
    def __init__(
        self,
        num_samples: int = 100,
        input_size: Tuple[int, int] = (640, 640),
        source_dir: Optional[str] = None
    ):
        """
        Args:
            num_samples: Number of calibration samples
            input_size: Model input size (width, height)
            source_dir: Directory with calibration images (optional)
        """
        self.num_samples = num_samples
        self.input_size = input_size
        self.source_dir = source_dir
        self._images = []
        
    def generate(self) -> List[np.ndarray]:
        """Generate calibration images."""
        if self.source_dir and Path(self.source_dir).exists():
            # Use real images if available
            self._load_from_directory()
        else:
            # Generate synthetic data
            self._generate_synthetic()
        
        return self._images
    
    def _load_from_directory(self):
        """Load images from calibration directory."""
        import cv2
        source_path = Path(self.source_dir)
        image_files = list(source_path.glob("*.jpg")) + list(source_path.glob("*.png"))
        
        for img_file in image_files[:self.num_samples]:
            img = cv2.imread(str(img_file))
            if img is not None:
                img = cv2.resize(img, self.input_size)
                self._images.append(img)
        
        logger.info(f"Loaded {len(self._images)} calibration images from {source_path}")
        
        # Fill remaining with synthetic if needed
        while len(self._images) < self.num_samples:
            self._images.append(self._synthetic_frame())
    
    def _generate_synthetic(self):
        """Generate synthetic calibration data."""
        logger.info(f"Generating {self.num_samples} synthetic calibration images")
        for _ in range(self.num_samples):
            self._images.append(self._synthetic_frame())
    
    def _synthetic_frame(self) -> np.ndarray:
        """Generate a realistic synthetic frame for calibration."""
        h, w = self.input_size
        
        # Create gradient background (simulates road/sky)
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        for i in range(h):
            gray = int(100 + (i / h) * 100)  # Sky to road gradient
            frame[i, :] = [gray, gray, gray]
        
        # Add some noise for texture
        noise = np.random.randint(-20, 20, (h, w, 3), dtype=np.int16)
        frame = np.clip(frame.astype(np.int16) + noise, 0, 255).astype(np.uint8)
        
        # Add random rectangles (simulates vehicles)
        num_rects = np.random.randint(1, 5)
        for _ in range(num_rects):
            x1 = np.random.randint(0, w - 100)
            y1 = np.random.randint(h // 2, h - 50)
            x2 = x1 + np.random.randint(50, 150)
            y2 = y1 + np.random.randint(30, 100)
            color = tuple(np.random.randint(50, 200, 3).tolist())
            frame[y1:y2, x1:x2] = color
        
        # Add lines (simulates lane markings)
        for _ in range(np.random.randint(2, 4)):
            x = np.random.randint(0, w)
            frame[h//2:, max(0, x-2):min(w, x+2)] = [255, 255, 255]
        
        return frame


# -----------------------------------------------------------------------------
# Model Pruning
# -----------------------------------------------------------------------------

def prune_yolo_model(
    model_path: str,
    output_path: str,
    prune_ratio: float = 0.3,
    finetune_epochs: int = 0,
    data_yaml: Optional[str] = None
) -> str:
    """
    Apply structured pruning to YOLO model.
    
    Args:
        model_path: Path to input .pt model
        output_path: Path for pruned model output
        prune_ratio: Ratio of channels to prune (0.0-0.5 recommended)
        finetune_epochs: Epochs to finetune after pruning (0=skip)
        data_yaml: Dataset YAML for finetuning (required if finetune_epochs > 0)
    
    Returns:
        Path to pruned model
    
    Note:
        Higher prune_ratio = faster but less accurate
        Recommended: 0.2-0.3 for good speed/accuracy tradeoff
    """
    from ultralytics import YOLO
    
    logger.info(f"🔪 Pruning model: {model_path}")
    logger.info(f"   Prune ratio: {prune_ratio}")
    
    # Load model
    model = YOLO(model_path)
    
    # Get model info before pruning
    params_before = sum(p.numel() for p in model.model.parameters())
    logger.info(f"   Parameters before: {params_before:,}")
    
    # Apply structured pruning
    try:
        # Use torch pruning for structured channel pruning
        import torch.nn.utils.prune as prune
        
        pruned_count = 0
        for name, module in model.model.named_modules():
            if isinstance(module, torch.nn.Conv2d):
                # L1 structured pruning on output channels
                prune.ln_structured(
                    module, 
                    name='weight', 
                    amount=prune_ratio,
                    n=1,  # L1 norm
                    dim=0  # Output channels
                )
                prune.remove(module, 'weight')
                pruned_count += 1
        
        logger.info(f"   Pruned {pruned_count} Conv2d layers")
        
    except Exception as e:
        logger.warning(f"Structured pruning failed: {e}, using ultralytics pruning")
        # Fallback: Use ultralytics built-in sparse training
        if finetune_epochs > 0 and data_yaml:
            model.train(
                data=data_yaml,
                epochs=finetune_epochs,
                imgsz=640,
                device='cuda' if torch.cuda.is_available() else 'cpu',
                prune=prune_ratio
            )
    
    # Get model info after pruning
    params_after = sum(p.numel() for p in model.model.parameters())
    reduction = (1 - params_after / params_before) * 100
    logger.info(f"   Parameters after: {params_after:,} ({reduction:.1f}% reduction)")
    
    # Save pruned model
    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)
    
    model.save(output_path)
    logger.info(f"✅ Pruned model saved: {output_path}")
    
    return output_path


# -----------------------------------------------------------------------------
# INT8 Quantization via TensorRT
# -----------------------------------------------------------------------------

def quantize_tensorrt_int8(
    model_path: str,
    output_path: str,
    calibration_images: Optional[List[np.ndarray]] = None,
    calibration_dir: Optional[str] = None,
    num_calibration: int = 100,
    input_size: Tuple[int, int] = (640, 640),
    batch_size: int = 1,
    workspace_gb: float = 4.0
) -> str:
    """
    Export YOLO model to TensorRT INT8 with calibration.
    
    Args:
        model_path: Path to .pt model
        output_path: Path for INT8 engine output
        calibration_images: Pre-loaded calibration images
        calibration_dir: Directory with calibration images
        num_calibration: Number of calibration samples
        input_size: Model input size (width, height)
        batch_size: TensorRT batch size
        workspace_gb: TensorRT workspace in GB
    
    Returns:
        Path to INT8 TensorRT engine
    """
    from ultralytics import YOLO
    
    logger.info(f"🔢 INT8 Quantization: {model_path}")
    
    # Generate calibration data
    if calibration_images is None:
        calib_dataset = CalibrationDataset(
            num_samples=num_calibration,
            input_size=input_size,
            source_dir=calibration_dir
        )
        calibration_images = calib_dataset.generate()
    
    logger.info(f"   Calibration samples: {len(calibration_images)}")
    
    # Load model
    model = YOLO(model_path)
    
    # Export to TensorRT INT8
    try:
        engine_path = model.export(
            format='engine',
            device=0,  # CUDA device
            half=False,  # Don't use FP16
            int8=True,  # Enable INT8 quantization
            data=calibration_dir,  # Calibration data directory
            imgsz=input_size[0],
            batch=batch_size,
            workspace=workspace_gb,
            simplify=True,
            dynamic=False
        )
        
        logger.info(f"✅ INT8 TensorRT engine: {engine_path}")
        
        # Rename to desired output path
        if engine_path != output_path:
            import shutil
            shutil.move(engine_path, output_path)
        
        return output_path
        
    except Exception as e:
        logger.error(f"TensorRT INT8 export failed: {e}")
        raise


def quantize_tensorrt_fp16(
    model_path: str,
    output_path: str,
    input_size: Tuple[int, int] = (640, 640),
    batch_size: int = 1,
    workspace_gb: float = 4.0,
    dynamic: bool = False
) -> str:
    """
    Export YOLO model to TensorRT FP16.
    
    Args:
        model_path: Path to .pt model
        output_path: Path for FP16 engine output
        input_size: Model input size (width, height)
        batch_size: TensorRT batch size
        workspace_gb: TensorRT workspace in GB
        dynamic: Enable dynamic batch size
    
    Returns:
        Path to FP16 TensorRT engine
    """
    from ultralytics import YOLO
    
    logger.info(f"⚡ FP16 TensorRT Export: {model_path}")
    
    # Load model
    model = YOLO(model_path)
    
    # Export to TensorRT FP16
    try:
        engine_path = model.export(
            format='engine',
            device=0,
            half=True,  # FP16
            int8=False,
            imgsz=input_size[0],
            batch=batch_size,
            workspace=workspace_gb,
            simplify=True,
            dynamic=dynamic
        )
        
        logger.info(f"✅ FP16 TensorRT engine: {engine_path}")
        
        # Rename to desired output path
        if engine_path != output_path:
            import shutil
            shutil.move(engine_path, output_path)
        
        return output_path
        
    except Exception as e:
        logger.error(f"TensorRT FP16 export failed: {e}")
        raise


# -----------------------------------------------------------------------------
# Dynamic Quantization (PyTorch fallback)
# -----------------------------------------------------------------------------

def quantize_pytorch_dynamic(
    model_path: str,
    output_path: str
) -> str:
    """
    Apply PyTorch dynamic quantization (CPU inference optimization).
    
    Note: This is for CPU fallback only. For GPU, use TensorRT.
    
    Args:
        model_path: Path to .pt model
        output_path: Path for quantized model
    
    Returns:
        Path to quantized model
    """
    from ultralytics import YOLO
    
    logger.info(f"🔢 PyTorch Dynamic Quantization: {model_path}")
    
    # Load model
    model = YOLO(model_path)
    
    # Apply dynamic quantization to linear layers
    quantized_model = torch.quantization.quantize_dynamic(
        model.model,
        {torch.nn.Linear},
        dtype=torch.qint8
    )
    
    # Save quantized model
    torch.save({'model': quantized_model}, output_path)
    logger.info(f"✅ PyTorch quantized model: {output_path}")
    
    return output_path


# -----------------------------------------------------------------------------
# ONNX Export with Optimization
# -----------------------------------------------------------------------------

def export_onnx_optimized(
    model_path: str,
    output_path: str,
    input_size: Tuple[int, int] = (640, 640),
    opset: int = 17,
    simplify: bool = True,
    dynamic: bool = False
) -> str:
    """
    Export YOLO to ONNX with optimizations.
    
    Args:
        model_path: Path to .pt model
        output_path: Path for ONNX output
        input_size: Model input size
        opset: ONNX opset version
        simplify: Simplify ONNX graph
        dynamic: Enable dynamic axes
    
    Returns:
        Path to ONNX model
    """
    from ultralytics import YOLO
    
    logger.info(f"📦 ONNX Export: {model_path}")
    
    model = YOLO(model_path)
    
    onnx_path = model.export(
        format='onnx',
        imgsz=input_size[0],
        opset=opset,
        simplify=simplify,
        dynamic=dynamic,
        half=False
    )
    
    logger.info(f"✅ ONNX model: {onnx_path}")
    
    # Rename if needed
    if onnx_path != output_path:
        import shutil
        shutil.move(onnx_path, output_path)
    
    return output_path


# -----------------------------------------------------------------------------
# Combined Optimization Pipeline
# -----------------------------------------------------------------------------

class ModelOptimizer:
    """
    Complete model optimization pipeline.
    
    Supports:
    - Pruning (structured channel pruning)
    - INT8 Quantization (TensorRT with calibration)
    - FP16 Quantization (TensorRT)
    - ONNX export
    
    Usage:
        optimizer = ModelOptimizer(
            model_path="yolo11x.pt",
            output_dir="./optimized_models"
        )
        
        # Full optimization (Pruning + INT8)
        engine = optimizer.optimize_full(
            prune_ratio=0.2,
            quantization='int8'
        )
        
        # Or just quantization
        engine = optimizer.quantize(precision='int8')
    """
    
    def __init__(
        self,
        model_path: str,
        output_dir: str = "./optimized_models",
        input_size: Tuple[int, int] = (640, 640),
        calibration_dir: Optional[str] = None
    ):
        """
        Args:
            model_path: Path to source .pt model
            output_dir: Directory for optimized outputs
            input_size: Model input size (width, height)
            calibration_dir: Directory with calibration images
        """
        self.model_path = Path(model_path)
        self.output_dir = Path(output_dir)
        self.input_size = input_size
        self.calibration_dir = calibration_dir
        
        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Model name without extension
        self.model_name = self.model_path.stem
        
        logger.info(f"ModelOptimizer initialized:")
        logger.info(f"  Source: {self.model_path}")
        logger.info(f"  Output: {self.output_dir}")
        logger.info(f"  Input size: {self.input_size}")
    
    def prune(
        self,
        prune_ratio: float = 0.3,
        finetune_epochs: int = 0,
        data_yaml: Optional[str] = None
    ) -> str:
        """
        Apply structured pruning.
        
        Args:
            prune_ratio: Channel prune ratio (0.0-0.5)
            finetune_epochs: Fine-tuning epochs after pruning
            data_yaml: Dataset YAML for fine-tuning
        
        Returns:
            Path to pruned model
        """
        output_path = self.output_dir / f"{self.model_name}_pruned_{int(prune_ratio*100)}pct.pt"
        
        return prune_yolo_model(
            model_path=str(self.model_path),
            output_path=str(output_path),
            prune_ratio=prune_ratio,
            finetune_epochs=finetune_epochs,
            data_yaml=data_yaml
        )
    
    def quantize(
        self,
        precision: str = 'int8',
        source_model: Optional[str] = None,
        num_calibration: int = 100
    ) -> str:
        """
        Quantize model to INT8 or FP16.
        
        Args:
            precision: 'int8' or 'fp16'
            source_model: Source model path (default: self.model_path)
            num_calibration: Calibration samples for INT8
        
        Returns:
            Path to quantized engine
        """
        source = source_model or str(self.model_path)
        
        if precision == 'int8':
            output_path = self.output_dir / f"{self.model_name}_int8.engine"
            return quantize_tensorrt_int8(
                model_path=source,
                output_path=str(output_path),
                calibration_dir=self.calibration_dir,
                num_calibration=num_calibration,
                input_size=self.input_size
            )
        elif precision == 'fp16':
            output_path = self.output_dir / f"{self.model_name}_fp16.engine"
            return quantize_tensorrt_fp16(
                model_path=source,
                output_path=str(output_path),
                input_size=self.input_size
            )
        else:
            raise ValueError(f"Unknown precision: {precision}")
    
    def export_onnx(
        self,
        source_model: Optional[str] = None,
        simplify: bool = True
    ) -> str:
        """
        Export to ONNX format.
        
        Args:
            source_model: Source model path
            simplify: Simplify ONNX graph
        
        Returns:
            Path to ONNX model
        """
        source = source_model or str(self.model_path)
        output_path = self.output_dir / f"{self.model_name}.onnx"
        
        return export_onnx_optimized(
            model_path=source,
            output_path=str(output_path),
            input_size=self.input_size,
            simplify=simplify
        )
    
    def optimize_full(
        self,
        prune_ratio: float = 0.2,
        quantization: str = 'int8',
        finetune_epochs: int = 0,
        data_yaml: Optional[str] = None
    ) -> str:
        """
        Full optimization pipeline: Prune → Quantize.
        
        Args:
            prune_ratio: Channel prune ratio
            quantization: Target precision ('int8', 'fp16')
            finetune_epochs: Fine-tuning epochs after pruning
            data_yaml: Dataset YAML for fine-tuning
        
        Returns:
            Path to final optimized engine
        """
        logger.info("=" * 60)
        logger.info("🚀 FULL OPTIMIZATION PIPELINE")
        logger.info("=" * 60)
        
        # Step 1: Pruning
        logger.info(f"\n📌 Step 1/2: Pruning ({prune_ratio*100:.0f}%)")
        pruned_model = self.prune(
            prune_ratio=prune_ratio,
            finetune_epochs=finetune_epochs,
            data_yaml=data_yaml
        )
        
        # Step 2: Quantization
        logger.info(f"\n📌 Step 2/2: Quantization ({quantization.upper()})")
        final_engine = self.quantize(
            precision=quantization,
            source_model=pruned_model
        )
        
        logger.info("=" * 60)
        logger.info(f"✅ OPTIMIZATION COMPLETE: {final_engine}")
        logger.info("=" * 60)
        
        return final_engine


# -----------------------------------------------------------------------------
# CLI Interface
# -----------------------------------------------------------------------------

def main():
    """Command-line interface for model optimization."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='YOLO Model Optimizer - Pruning + Quantization'
    )
    parser.add_argument('model', help='Path to .pt model')
    parser.add_argument('--output-dir', default='./optimized_models',
                       help='Output directory')
    parser.add_argument('--prune', type=float, default=0.0,
                       help='Prune ratio (0.0-0.5, default: 0 = no pruning)')
    parser.add_argument('--quantize', choices=['fp16', 'int8', 'none'],
                       default='fp16', help='Quantization type')
    parser.add_argument('--calibration-dir', help='Calibration images directory')
    parser.add_argument('--imgsz', type=int, default=640, help='Input size')
    parser.add_argument('--onnx', action='store_true', help='Also export ONNX')
    
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Create optimizer
    optimizer = ModelOptimizer(
        model_path=args.model,
        output_dir=args.output_dir,
        input_size=(args.imgsz, args.imgsz),
        calibration_dir=args.calibration_dir
    )
    
    if args.prune > 0:
        # Full pipeline: Prune + Quantize
        if args.quantize != 'none':
            result = optimizer.optimize_full(
                prune_ratio=args.prune,
                quantization=args.quantize
            )
        else:
            result = optimizer.prune(prune_ratio=args.prune)
    elif args.quantize != 'none':
        # Quantization only
        result = optimizer.quantize(precision=args.quantize)
    else:
        logger.warning("No optimization requested. Use --prune or --quantize")
        return
    
    # Optional ONNX export
    if args.onnx:
        optimizer.export_onnx()
    
    print(f"\n🎉 Optimized model: {result}")


if __name__ == '__main__':
    main()
