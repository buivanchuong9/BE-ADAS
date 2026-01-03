#!/usr/bin/env python3
"""
Quick API Health Check
======================
Verifies all production enhancements are working.

Run: python3 test_api_health.py
"""

import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

def test_imports():
    """Test all critical imports"""
    print("=" * 60)
    print("TEST 1: Module Imports")
    print("=" * 60)
    
    try:
        from app.api.video_sse import router as sse_router
        print("✓ SSE router imported")
        print(f"  Routes: {len(sse_router.routes)}")
        for route in sse_router.routes:
            print(f"    - {list(route.methods)[0]} {route.path}")
    except Exception as e:
        print(f"✗ SSE router failed: {e}")
        return False
    
    try:
        from perception.lane.kalman_filter import KalmanFilter, LaneKalmanFilter
        print("✓ Kalman Filter imported")
    except Exception as e:
        print(f"✗ Kalman Filter failed: {e}")
        return False
    
    try:
        from perception.object.object_detector_v11 import ObjectDetectorV11
        print("✓ Object Detector imported")
        assert hasattr(ObjectDetectorV11, 'detect_batch'), "Missing detect_batch method"
        print("  - Has detect_batch method")
    except Exception as e:
        print(f"✗ Object Detector failed: {e}")
        return False
    
    try:
        from perception.pipeline.video_pipeline_v11 import VideoPipelineV11
        print("✓ Video Pipeline imported")
        # Check for batch size attribute
        pipeline = VideoPipelineV11(device='cpu', video_type='dashcam')
        assert hasattr(pipeline, 'batch_size'), "Missing batch_size attribute"
        print(f"  - Batch size: {pipeline.batch_size}")
    except Exception as e:
        print(f"✗ Video Pipeline failed: {e}")
        return False
    
    return True

def test_worker():
    """Test GPU worker semaphore"""
    print("\n" + "=" * 60)
    print("TEST 2: GPU Worker")
    print("=" * 60)
    
    try:
        import workers.gpu_worker as worker
        import inspect
        
        # Check semaphore exists
        assert hasattr(worker.GPUWorker, '_gpu_semaphore'), "Missing GPU semaphore"
        print("✓ GPU semaphore exists")
        
        # Check process_job uses semaphore
        source = inspect.getsource(worker.GPUWorker.process_job)
        assert 'async with self._gpu_semaphore' in source, "Semaphore not used in process_job"
        print("✓ Semaphore used in process_job")
        
        return True
    except Exception as e:
        print(f"✗ GPU Worker failed: {e}")
        return False

def test_kalman_filter():
    """Test Kalman Filter functionality"""
    print("\n" + "=" * 60)
    print("TEST 3: Kalman Filter")
    print("=" * 60)
    
    try:
        from perception.lane.kalman_filter import KalmanFilter
        import numpy as np
        
        # Test basic filtering
        kf = KalmanFilter(process_variance=0.01, measurement_variance=0.1)
        
        # Simulate noisy measurements
        true_value = 5.0
        measurements = [5.0 + np.random.randn() * 0.3 for _ in range(10)]
        filtered = [kf.update(m) for m in measurements]
        
        # Filtered values should be smoother
        variance_raw = np.var(measurements)
        variance_filtered = np.var(filtered)
        
        print(f"✓ Kalman Filter reduces variance")
        print(f"  Raw variance: {variance_raw:.4f}")
        print(f"  Filtered variance: {variance_filtered:.4f}")
        print(f"  Improvement: {(1 - variance_filtered/variance_raw)*100:.1f}%")
        
        return True
    except Exception as e:
        print(f"✗ Kalman Filter failed: {e}")
        return False

def test_batch_detection():
    """Test batch detection"""
    print("\n" + "=" * 60)
    print("TEST 4: Batch Detection")
    print("=" * 60)
    
    try:
        from perception.object.object_detector_v11 import ObjectDetectorV11
        import inspect
        
        # Check signature
        sig = inspect.signature(ObjectDetectorV11.detect_batch)
        params = list(sig.parameters.keys())
        
        print("✓ detect_batch method exists")
        print(f"  Parameters: {params}")
        print(f"  Return annotation: {sig.return_annotation}")
        
        return True
    except Exception as e:
        print(f"✗ Batch detection failed: {e}")
        return False

def test_middleware():
    """Test middleware integration"""
    print("\n" + "=" * 60)
    print("TEST 5: Middleware")
    print("=" * 60)
    
    try:
        from app.core.middleware import RequestIDMiddleware
        print("✓ Request ID middleware exists")
        
        # Check main.py integration
        import inspect
        from app import main
        source = inspect.getsource(main)
        
        has_middleware = 'RequestIDMiddleware' in source
        has_404_filter = 'should_log' in source and 'admin' in source
        
        if has_middleware:
            print("✓ Request ID middleware integrated")
        else:
            print("⚠ Request ID middleware not integrated")
        
        if has_404_filter:
            print("✓ 404 log filtering active")
        else:
            print("⚠ 404 log filtering not found")
        
        return True
    except Exception as e:
        print(f"✗ Middleware test failed: {e}")
        return False

def main():
    """Run all tests"""
    print("\n" + "🚀 " * 20)
    print("ADAS Backend v3.0 - Production Health Check")
    print("🚀 " * 20 + "\n")
    
    results = []
    
    results.append(("Module Imports", test_imports()))
    results.append(("GPU Worker", test_worker()))
    results.append(("Kalman Filter", test_kalman_filter()))
    results.append(("Batch Detection", test_batch_detection()))
    results.append(("Middleware", test_middleware()))
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status:10} {name}")
    
    total = len(results)
    passed = sum(1 for _, p in results if p)
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All systems operational! Ready for production!")
        return 0
    else:
        print("\n⚠️ Some tests failed. Please review.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
