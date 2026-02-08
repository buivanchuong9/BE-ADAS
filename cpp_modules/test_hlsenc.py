#!/usr/bin/env python3
"""
Test suite for HLS Encoder C++ module
"""

import sys
from pathlib import Path
import time
import numpy as np
import shutil

# Add build/lib to path
sys.path.insert(0, str(Path(__file__).parent.parent / "build/lib"))

try:
    import hlsenc
    print(f"✅ hlsenc module loaded: v{hlsenc.__version__}")
    print(f"   FFmpeg backend: {hlsenc.FFMPEG_BACKEND}")
except ImportError as e:
    print(f"❌ Failed to import hlsenc: {e}")
    print("   Run ./build_cpp.sh first")
    sys.exit(1)


def test_encoder_init():
    """Test encoder initialization."""
    print("\n[TEST] Encoder initialization...")
    
    output_dir = "/tmp/adas_hls_test"
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    try:
        encoder = hlsenc.HLSEncoder(
            output_dir=output_dir,
            width=1280,
            height=720,
            fps=30.0,
            segment_duration=2.0
        )
        print("✅ Encoder initialized")
        encoder.finalize()
        return True
    except Exception as e:
        print(f"❌ Initialization failed: {e}")
        return False


def test_encode_frames():
    """Test frame encoding."""
    print("\n[TEST] Frame encoding...")
    
    output_dir = "/tmp/adas_hls_test"
    shutil.rmtree(output_dir, ignore_errors=True)
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    width, height = 1280, 720
    fps = 30.0
    
    encoder = hlsenc.HLSEncoder(output_dir, width, height, fps, segment_duration=2.0)
    
    # Encode 90 frames (3 segments @ 30fps with 2s segments)
    num_frames = 90
    
    print(f"  Encoding {num_frames} frames...")
    start = time.perf_counter()
    
    for i in range(num_frames):
        # Create test frame (gradient)
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[:, :] = (i * 2) % 256  # Animated gradient
        
        encoder.encode_frame(frame, pts=i)
        
        if (i + 1) % 30 == 0:
            stats = encoder.get_stats()
            print(f"    Frame {i+1}: {stats.total_segments_written} segments written")
    
    elapsed = time.perf_counter() - start
    
    # Finalize
    encoder.finalize()
    
    stats = encoder.get_stats()
    print(f"\n  Stats:")
    print(f"    Frames encoded: {stats.total_frames_encoded}")
    print(f"    Segments written: {stats.total_segments_written}")
    print(f"    Total time: {elapsed:.2f}s")
    print(f"    FPS: {num_frames / elapsed:.1f}")
    print(f"    Time per frame: {elapsed / num_frames * 1000:.2f}ms")
    
    # Verify output files
    playlist = Path(output_dir) / "playlist.m3u8"
    segments = list(Path(output_dir).glob("segment_*.ts"))
    
    assert playlist.exists(), "Playlist not found"
    assert len(segments) > 0, "No segments found"
    
    print(f"\n  Output:")
    print(f"    Playlist: {playlist}")
    print(f"    Segments: {len(segments)} files")
    
    # Check playlist content
    with open(playlist) as f:
        content = f.read()
        assert "#EXTM3U" in content, "Invalid playlist"
        assert "#EXT-X-ENDLIST" in content, "Playlist not finalized"
        print(f"    Playlist valid ✅")
    
    print("✅ Frame encoding works")
    return True


def test_performance():
    """Benchmark encoding performance."""
    print("\n[TEST] Performance benchmark...")
    
    output_dir = "/tmp/adas_hls_bench"
    shutil.rmtree(output_dir, ignore_errors=True)
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    width, height = 1920, 1080  # Full HD
    fps = 30.0
    num_frames = 180  # 6 seconds
    
    encoder = hlsenc.HLSEncoder(output_dir, width, height, fps, segment_duration=2.0)
    
    print(f"  Resolution: {width}x{height}")
    print(f"  Frames: {num_frames}")
    
    # Warmup
    frame = np.random.randint(0, 256, (height, width, 3), dtype=np.uint8)
    for i in range(10):
        encoder.encode_frame(frame, pts=i)
    
    # Benchmark
    start = time.perf_counter()
    for i in range(10, num_frames):
        encoder.encode_frame(frame, pts=i)
    elapsed = time.perf_counter() - start
    
    encoder.finalize()
    
    fps_actual = (num_frames - 10) / elapsed
    time_per_frame = elapsed / (num_frames - 10) * 1000
    
    print(f"\n  Results:")
    print(f"    Time: {elapsed:.2f}s")
    print(f"    FPS: {fps_actual:.1f}")
    print(f"    Time per frame: {time_per_frame:.2f}ms")
    
    target_time = 3.0  # Target < 3ms per frame
    if time_per_frame < target_time:
        print(f"✅ Performance is EXCELLENT (<{target_time}ms)")
    elif time_per_frame < 5.0:
        print(f"⚠️  Performance is ACCEPTABLE (<5ms)")
    else:
        print(f"❌ Performance is POOR (>{time_per_frame:.1f}ms)")
    
    return time_per_frame < 10.0  # At least must be < 10ms


def run_all_tests():
    """Run all test cases."""
    print("=" * 60)
    print(" HLS ENCODER MODULE TEST SUITE")
    print("=" * 60)
    
    tests = [
        test_encoder_init,
        test_encode_frames,
        test_performance,
    ]
    
    passed = 0
    failed = 0
    
    for test_fn in tests:
        try:
            if test_fn():
                passed += 1
            else:
                failed += 1
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
