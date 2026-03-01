#!/usr/bin/env python3
"""
OPTIMIZE MODELS - Generate INT8/FP16 TensorRT engines for maximum throughput
=============================================================================

Usage:
    # Generate INT8 engine (fastest, requires calibration)
    python3 scripts/optimize_models.py --model yolo11m --precision int8
    
    # Generate FP16 engine (fast, no calibration needed)
    python3 scripts/optimize_models.py --model yolo11m --precision fp16
    
    # Full optimization: Pruning + INT8 (maximum speed)
    python3 scripts/optimize_models.py --model yolo11x --prune 0.2 --precision int8
    
    # Optimize all models for 'fast' profile
    python3 scripts/optimize_models.py --profile fast

Expected speedups vs FP32 PyTorch:
    - FP16 TensorRT:  2-3x faster
    - INT8 TensorRT:  3-5x faster  
    - Pruned + INT8:  4-6x faster

Author: Senior ADAS Engineer
Date: 2026-03-01
"""

import os
import sys
import argparse
import logging
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.perception.engine.model_optimizer import (
    ModelOptimizer,
    prune_yolo_model,
    quantize_tensorrt_int8,
    quantize_tensorrt_fp16,
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# Model profiles (same as gpu_worker_simple.py)
MODEL_PROFILES = {
    'cloud': {
        'obj_model': 'backend/models/yolo11x.pt',
        'imgsz': 416,
    },
    'fast': {
        'obj_model': 'backend/models/yolo11m.pt',
        'imgsz': 384,
    },
    'edge': {
        'obj_model': 'backend/models/yolov8n.pt',
        'imgsz': 320,
    },
}

# Common model paths
MODEL_PATHS = {
    'yolo11x': 'backend/models/yolo11x.pt',
    'yolo11m': 'backend/models/yolo11m.pt',
    'yolo11s': 'backend/models/yolo11s.pt',
    'yolo11n': 'backend/models/yolo11n.pt',
    'yolov8x': 'backend/models/yolov8x.pt',
    'yolov8m': 'backend/models/yolov8m.pt',
    'yolov8n': 'backend/models/yolov8n.pt',
}

OUTPUT_DIR = 'backend/models/optimized'


def optimize_model(
    model_path: str,
    precision: str = 'fp16',
    prune_ratio: float = 0.0,
    imgsz: int = 640,
    calibration_dir: str = None
):
    """Optimize a single model."""
    
    if not Path(model_path).exists():
        logger.error(f"Model not found: {model_path}")
        return None
    
    optimizer = ModelOptimizer(
        model_path=model_path,
        output_dir=OUTPUT_DIR,
        input_size=(imgsz, imgsz),
        calibration_dir=calibration_dir
    )
    
    if prune_ratio > 0:
        # Full optimization: Prune + Quantize
        return optimizer.optimize_full(
            prune_ratio=prune_ratio,
            quantization=precision
        )
    else:
        # Quantization only
        return optimizer.quantize(precision=precision)


def optimize_profile(profile: str, precision: str = 'fp16'):
    """Optimize all models in a profile."""
    
    if profile not in MODEL_PROFILES:
        logger.error(f"Unknown profile: {profile}")
        return
    
    prof = MODEL_PROFILES[profile]
    model_path = prof['obj_model']
    imgsz = prof['imgsz']
    
    logger.info(f"\n{'='*60}")
    logger.info(f"Optimizing profile '{profile}': {model_path}")
    logger.info(f"{'='*60}")
    
    result = optimize_model(
        model_path=model_path,
        precision=precision,
        imgsz=imgsz
    )
    
    if result:
        logger.info(f"\n✅ Optimized model: {result}")
        logger.info(f"\nTo use this model, run:")
        logger.info(f"  python3 workers/gpu_worker_simple.py --profile turbo")


def main():
    parser = argparse.ArgumentParser(
        description='Optimize YOLO models with Pruning + Quantization',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Quick FP16 optimization (recommended for most cases)
  python3 scripts/optimize_models.py --model yolo11m --precision fp16

  # Maximum throughput (INT8 quantization)
  python3 scripts/optimize_models.py --model yolo11m --precision int8
  
  # Full optimization (Pruning 20% + INT8)
  python3 scripts/optimize_models.py --model yolo11x --prune 0.2 --precision int8
  
  # Optimize entire profile
  python3 scripts/optimize_models.py --profile fast
        """
    )
    
    parser.add_argument('--model', choices=list(MODEL_PATHS.keys()),
                       help='Model name to optimize')
    parser.add_argument('--model-path', help='Custom model path')
    parser.add_argument('--profile', choices=['cloud', 'fast', 'edge'],
                       help='Optimize entire profile')
    parser.add_argument('--precision', choices=['fp16', 'int8'], default='fp16',
                       help='Quantization precision (default: fp16)')
    parser.add_argument('--prune', type=float, default=0.0,
                       help='Pruning ratio 0.0-0.5 (default: 0 = no pruning)')
    parser.add_argument('--imgsz', type=int, default=640,
                       help='Input image size (default: 640)')
    parser.add_argument('--calibration-dir', 
                       help='Directory with calibration images (for INT8)')
    parser.add_argument('--output-dir', default=OUTPUT_DIR,
                       help=f'Output directory (default: {OUTPUT_DIR})')
    
    args = parser.parse_args()
    
    # Create output directory
    Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    global OUTPUT_DIR
    OUTPUT_DIR = args.output_dir
    
    if args.profile:
        # Optimize entire profile
        optimize_profile(args.profile, args.precision)
    elif args.model or args.model_path:
        # Optimize single model
        model_path = args.model_path or MODEL_PATHS.get(args.model)
        
        if not model_path:
            logger.error("Specify --model or --model-path")
            sys.exit(1)
        
        result = optimize_model(
            model_path=model_path,
            precision=args.precision,
            prune_ratio=args.prune,
            imgsz=args.imgsz,
            calibration_dir=args.calibration_dir
        )
        
        if result:
            logger.info(f"\n🎉 Optimized model saved: {result}")
    else:
        parser.print_help()
        print("\n💡 Quick start:")
        print("  python3 scripts/optimize_models.py --model yolo11m --precision fp16")


if __name__ == '__main__':
    main()
