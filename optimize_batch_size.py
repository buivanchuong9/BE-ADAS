#!/usr/bin/env python3
"""
TỐI ƯU BATCH SIZE CHO GPU
=========================
Tự động tìm batch size tối ưu dựa trên VRAM available
"""

import torch

def optimize_batch_size():
    """Find optimal batch size for GPU"""
    
    if not torch.cuda.is_available():
        print("❌ GPU không khả dụng, sử dụng CPU với batch_size=1")
        return 1
    
    # Get GPU memory
    gpu_mem_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
    print(f"🎮 GPU VRAM: {gpu_mem_gb:.1f} GB")
    
    # Estimate optimal batch size based on VRAM
    # YOLOv11n uses ~500MB per batch of 8 frames at 720p
    if gpu_mem_gb >= 24:
        batch_size = 32
        print(f"✅ High-end GPU → batch_size={batch_size}")
    elif gpu_mem_gb >= 16:
        batch_size = 24
        print(f"✅ Mid-high GPU → batch_size={batch_size}")
    elif gpu_mem_gb >= 12:
        batch_size = 16
        print(f"✅ Mid GPU → batch_size={batch_size}")
    elif gpu_mem_gb >= 8:
        batch_size = 12
        print(f"✅ Entry GPU → batch_size={batch_size}")
    elif gpu_mem_gb >= 6:
        batch_size = 8
        print(f"⚠️  Low VRAM → batch_size={batch_size}")
    else:
        batch_size = 4
        print(f"⚠️  Very low VRAM → batch_size={batch_size}")
    
    return batch_size

if __name__ == "__main__":
    print("=" * 60)
    print("🔧 TỐI ƯU BATCH SIZE")
    print("=" * 60)
    
    batch_size = optimize_batch_size()
    
    print(f"\n📝 Khuyến nghị:")
    print(f"   Sửa file: backend/perception/pipeline/video_pipeline_v11.py")
    print(f"   Dòng 62: self.batch_size = {batch_size} if device == \"cuda\" else 1")
    print("\n" + "=" * 60)
