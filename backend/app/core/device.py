"""
DEVICE DETECTION AND MANAGEMENT
================================
Phase 9: Automatic GPU/CPU device selection.

PURPOSE:
Automatically detect available hardware and select optimal device for inference.

FEATURES:
- CUDA GPU detection
- DirectML detection (Windows AMD/Intel GPUs)
- CPU fallback
- Device info logging
- Performance benchmarking

PRIORITY:
1. CUDA GPU (NVIDIA) - Best performance
2. DirectML (Windows AMD/Intel) - Good performance on Windows
3. CPU - Fallback option

Author: Senior ADAS Engineer
Date: 2025-12-26 (Phase 9)
"""

import logging
import platform
from typing import Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class DeviceInfo:
    """Information about selected device."""
    device_type: str  # "cuda", "directml", "cpu"
    device_name: str
    device_id: int
    total_memory: Optional[int] = None  # MB
    available_memory: Optional[int] = None  # MB
    compute_capability: Optional[str] = None


class DeviceDetector:
    """
    Automatic device detection and selection.
    """
    
    def __init__(self):
        self.device_info: Optional[DeviceInfo] = None
        self._detect_device()
    
    def _check_cuda(self) -> Optional[DeviceInfo]:
        """
        Check for CUDA-capable NVIDIA GPU.
        
        Returns:
            DeviceInfo if CUDA available, None otherwise
        """
        try:
            import torch
            
            if torch.cuda.is_available():
                device_id = 0  # Use first GPU
                device_name = torch.cuda.get_device_name(device_id)
                
                # Get memory info
                total_memory = torch.cuda.get_device_properties(device_id).total_memory // (1024 ** 2)
                
                # Get compute capability
                capability = torch.cuda.get_device_capability(device_id)
                compute_capability = f"{capability[0]}.{capability[1]}"
                
                logger.info(f"CUDA GPU detected: {device_name}")
                logger.info(f"  Memory: {total_memory} MB")
                logger.info(f"  Compute Capability: {compute_capability}")
                
                return DeviceInfo(
                    device_type="cuda",
                    device_name=device_name,
                    device_id=device_id,
                    total_memory=total_memory,
                    compute_capability=compute_capability
                )
            else:
                logger.info("CUDA not available")
                return None
                
        except ImportError:
            logger.info("PyTorch not installed - skipping CUDA detection")
            return None
        except Exception as e:
            logger.warning(f"CUDA detection failed: {e}")
            return None
    
    def _check_directml(self) -> Optional[DeviceInfo]:
        """
        Check for DirectML support (Windows AMD/Intel GPUs).
        
        Returns:
            DeviceInfo if DirectML available, None otherwise
        """
        if platform.system() != "Windows":
            return None
        
        try:
            import torch_directml
            
            if torch_directml.is_available():
                device_count = torch_directml.device_count()
                
                if device_count > 0:
                    device_name = torch_directml.device_name(0)
                    
                    logger.info(f"DirectML GPU detected: {device_name}")
                    logger.info(f"  Available devices: {device_count}")
                    
                    return DeviceInfo(
                        device_type="directml",
                        device_name=device_name,
                        device_id=0
                    )
            
            logger.info("DirectML devices not found")
            return None
            
        except ImportError:
            logger.info("torch-directml not installed - skipping DirectML detection")
            return None
        except Exception as e:
            logger.warning(f"DirectML detection failed: {e}")
            return None
    
    def _get_cpu_info(self) -> DeviceInfo:
        """
        Get CPU information as fallback.
        
        Returns:
            DeviceInfo for CPU
        """
        import psutil
        
        cpu_name = platform.processor() or "CPU"
        cpu_count = psutil.cpu_count(logical=False)
        total_memory = psutil.virtual_memory().total // (1024 ** 2)
        
        logger.info(f"Using CPU: {cpu_name}")
        logger.info(f"  Physical cores: {cpu_count}")
        logger.info(f"  Total memory: {total_memory} MB")
        
        return DeviceInfo(
            device_type="cpu",
            device_name=cpu_name,
            device_id=0,
            total_memory=total_memory
        )
    
    def _detect_device(self) -> None:
        """
        Detect best available device.
        Priority: CUDA > DirectML > CPU
        """
        logger.info("=" * 60)
        logger.info("Detecting hardware devices...")
        logger.info("=" * 60)
        
        # Try CUDA first
        cuda_device = self._check_cuda()
        if cuda_device:
            self.device_info = cuda_device
            logger.info(f"✓ Selected device: CUDA GPU ({cuda_device.device_name})")
            return
        
        # Try DirectML on Windows
        directml_device = self._check_directml()
        if directml_device:
            self.device_info = directml_device
            logger.info(f"✓ Selected device: DirectML GPU ({directml_device.device_name})")
            return
        
        # Fallback to CPU
        cpu_device = self._get_cpu_info()
        self.device_info = cpu_device
        logger.warning("⚠ No GPU detected - using CPU (performance may be limited)")
        logger.warning("  For better performance, install CUDA-capable GPU or use Windows with DirectML")
        logger.info(f"✓ Selected device: CPU ({cpu_device.device_name})")
    
    def get_device_string(self) -> str:
        """
        Get device string for framework initialization.
        
        Returns:
            Device string ("cuda", "cuda:0", "cpu", etc.)
        """
        if self.device_info is None:
            return "cpu"
        
        if self.device_info.device_type == "cuda":
            return f"cuda:{self.device_info.device_id}"
        elif self.device_info.device_type == "directml":
            return "dml"  # DirectML device string
        else:
            return "cpu"
    
    def get_device_info(self) -> Dict[str, Any]:
        """
        Get device information as dictionary.
        
        Returns:
            Dict with device information
        """
        if self.device_info is None:
            return {"device_type": "unknown"}
        
        return {
            "device_type": self.device_info.device_type,
            "device_name": self.device_info.device_name,
            "device_id": self.device_info.device_id,
            "total_memory_mb": self.device_info.total_memory,
            "available_memory_mb": self.device_info.available_memory,
            "compute_capability": self.device_info.compute_capability
        }
    
    def is_gpu_available(self) -> bool:
        """Check if GPU is available."""
        return self.device_info and self.device_info.device_type in ["cuda", "directml"]
    
    def get_optimal_batch_size(self) -> int:
        """
        Get optimal batch size based on device.
        
        Returns:
            Recommended batch size
        """
        if not self.device_info:
            return 1
        
        if self.device_info.device_type == "cuda":
            # CUDA GPU - larger batch sizes
            if self.device_info.total_memory and self.device_info.total_memory >= 8000:
                return 8  # High-end GPU
            elif self.device_info.total_memory and self.device_info.total_memory >= 4000:
                return 4  # Mid-range GPU
            else:
                return 2  # Low-end GPU
        elif self.device_info.device_type == "directml":
            return 2  # DirectML - conservative batch size
        else:
            return 1  # CPU - single frame processing


# Global device detector instance
_device_detector: Optional[DeviceDetector] = None


def get_device_detector() -> DeviceDetector:
    """
    Get global device detector instance (singleton).
    
    Returns:
        DeviceDetector instance
    """
    global _device_detector
    
    if _device_detector is None:
        _device_detector = DeviceDetector()
    
    return _device_detector


def get_device() -> str:
    """
    Get device string for current system.
    
    Returns:
        Device string ("cuda:0", "cpu", etc.)
    """
    detector = get_device_detector()
    return detector.get_device_string()


def is_gpu_available() -> bool:
    """
    Check if GPU is available.
    
    Returns:
        True if GPU available
    """
    detector = get_device_detector()
    return detector.is_gpu_available()


if __name__ == "__main__":
    # Test device detection
    logging.basicConfig(level=logging.INFO)
    
    print("\nDevice Detection Test")
    print("=" * 60)
    
    detector = DeviceDetector()
    
    print("\nDevice Information:")
    info = detector.get_device_info()
    for key, value in info.items():
        print(f"  {key}: {value}")
    
    print(f"\nDevice String: {detector.get_device_string()}")
    print(f"GPU Available: {detector.is_gpu_available()}")
    print(f"Optimal Batch Size: {detector.get_optimal_batch_size()}")
    
    print("\n" + "=" * 60)
    print("✓ Device detection complete")
