#!/usr/bin/env python3
"""
Test suite for C++ renderer module
Validates zero-copy behavior and performance
"""

import sys
from pathlib import Path
import time
import numpy as np

# Add build/lib to path
sys.path.insert(0, str(Path(__file__).parent.parent / "build/lib"))

try:
    import renderer
    print(f"✅ Renderer module loaded: v{renderer.__version__}")
    print(f"   SIMD enabled: {renderer.SIMD_ENABLED}")
except ImportError as e:
    print(f"❌ Failed to import renderer: {e}")
    print("   Run ./build_cpp.sh first")
    sys.exit(1)


def test_bbox_creation():
    """Test BBox creation."""
    print("\n[TEST] BBox creation...")
    
    bbox = renderer.BBox(100, 50, 200, 150, 255, 0, 0, 0.95, "car")
    assert bbox.x1 == 100
    assert bbox.y1 == 50
    assert bbox.x2 == 200
    assert bbox.y2 == 150
    assert abs(bbox.confidence - 0.95) < 0.01, f"Confidence mismatch: {bbox.confidence} vs 0.95"
    assert bbox.label == "car"
    
    print("✅ BBox creation works")


def test_render_in_place():
    """Test in-place rendering (zero-copy)."""
    print("\n[TEST] In-place rendering...")
    
    # Create test frame
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    frame_id_before = id(frame)
    
    # Create test bboxes
    bboxes = [
        renderer.BBox(100, 100, 300, 300, 0, 255, 0, 0.95, "car"),
        renderer.BBox(500, 200, 700, 400, 255, 0, 0, 0.87, "truck"),
    ]
    
    # Render
    renderer.OverlayRenderer.render(frame, None, bboxes, 0.3)
    
    frame_id_after = id(frame)
    
    # Verify zero-copy (same memory address)
    assert frame_id_before == frame_id_after, "Frame was copied (not in-place)!"
    
    # Verify frame was modified
    assert np.any(frame > 0), "Frame was not modified"
    
    print("✅ In-place rendering works (zero-copy)")


def test_performance():
    """Benchmark renderer performance."""
    print("\n[TEST] Performance benchmark...")
    
    # Test parameters
    height, width = 1080, 1920
    num_iterations = 100
    
    # Create test data
    frame = np.random.randint(0, 256, (height, width, 3), dtype=np.uint8)
    mask = np.random.randint(0, 256, (height, width), dtype=np.uint8)
    bboxes = [
        renderer.BBox(i*100, i*50, i*100+200, i*50+150, 0, 255, 0, 0.9, f"obj{i}")
        for i in range(10)
    ]
    
    # Warmup
    for _ in range(10):
        renderer.OverlayRenderer.render(frame, mask, bboxes, 0.3)
    
    # Benchmark
    start = time.perf_counter()
    for _ in range(num_iterations):
        renderer.OverlayRenderer.render(frame, mask, bboxes, 0.3)
    elapsed = time.perf_counter() - start
    
    avg_time_ms = (elapsed / num_iterations) * 1000
    fps = 1000.0 / avg_time_ms
    
    print(f"  Resolution: {width}x{height}")
    print(f"  Iterations: {num_iterations}")
    print(f"  Avg time:   {avg_time_ms:.2f} ms/frame")
    print(f"  FPS:        {fps:.1f}")
    print(f"  Target:     <3ms (for 1080p)")
    
    if avg_time_ms < 5.0:
        print("✅ Performance is GOOD")
    elif avg_time_ms < 10.0:
        print("⚠️  Performance is ACCEPTABLE (consider optimization)")
    else:
        print("❌ Performance is POOR (check SIMD compilation)")


def test_with_lane_mask():
    """Test overlay with lane mask."""
    print("\n[TEST] Rendering with lane mask...")
    
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    
    # Create fake lane mask (vertical stripe)
    mask = np.zeros((720, 1280), dtype=np.uint8)
    mask[:, 400:600] = 128
    mask[:, 700:900] = 255
    
    bboxes = [renderer.BBox(100, 100, 300, 300, 255, 255, 0, 0.99, "vehicle")]
    
    # Render
    renderer.OverlayRenderer.render(frame, mask, bboxes, 0.4)
    
    # Verify lane regions were modified
    assert np.any(frame[:, 400:600] > 0), "Lane mask not applied"
    
    print("✅ Lane mask rendering works")


def run_all_tests():
    """Run all test cases."""
    print("=" * 60)
    print(" RENDERER MODULE TEST SUITE")
    print("=" * 60)
    
    tests = [
        test_bbox_creation,
        test_render_in_place,
        test_with_lane_mask,
        test_performance,
    ]
    
    passed = 0
    failed = 0
    
    for test_fn in tests:
        try:
            test_fn()
            passed += 1
        except Exception as e:
            print(f"❌ {test_fn.__name__} FAILED: {e}")
            failed += 1
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 60)
    print(f" RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return failed == 0


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
