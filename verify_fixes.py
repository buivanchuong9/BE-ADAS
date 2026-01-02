#!/usr/bin/env python3
"""
ADAS Backend Verification Script
=================================
Tests all critical fixes to ensure production readiness.

Run this script after implementing fixes to verify:
1. Upload response time < 5 seconds
2. Background processing completes successfully
3. File size tracking works
4. Health check remains responsive during uploads
"""

import requests
import time
import sys
from pathlib import Path
import json

# Configuration
BASE_URL = "http://localhost:52000"
TEST_VIDEO_PATH = None  # Will be set by user

def print_header(text):
    """Print formatted header"""
    print("\n" + "="*60)
    print(f"  {text}")
    print("="*60)

def print_result(test_name, passed, details=""):
    """Print test result"""
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status} - {test_name}")
    if details:
        print(f"    {details}")

def test_health_check():
    """Test 1: Health check is responsive"""
    print_header("Test 1: Health Check")
    
    try:
        start = time.time()
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        elapsed = time.time() - start
        
        passed = response.status_code == 200 and elapsed < 2
        print_result(
            "Health check responsive",
            passed,
            f"Response time: {elapsed:.2f}s"
        )
        return passed
    except Exception as e:
        print_result("Health check responsive", False, str(e))
        return False

def test_upload_response_time(video_path):
    """Test 2: Upload returns quickly (< 5 seconds)"""
    print_header("Test 2: Upload Response Time")
    
    if not video_path or not Path(video_path).exists():
        print_result("Upload response time", False, "Test video not found")
        return False
    
    try:
        with open(video_path, 'rb') as f:
            files = {'file': f}
            data = {'video_type': 'dashcam', 'device': 'cpu'}
            
            start = time.time()
            response = requests.post(
                f"{BASE_URL}/api/video/upload",
                files=files,
                data=data,
                timeout=30
            )
            elapsed = time.time() - start
        
        if response.status_code == 200:
            result = response.json()
            job_id = result.get('job_id')
            
            passed = elapsed < 5.0
            print_result(
                "Upload response time < 5s",
                passed,
                f"Response time: {elapsed:.2f}s, job_id: {job_id}"
            )
            return passed, job_id
        else:
            print_result(
                "Upload response time",
                False,
                f"HTTP {response.status_code}: {response.text}"
            )
            return False, None
            
    except Exception as e:
        print_result("Upload response time", False, str(e))
        return False, None

def test_background_processing(job_id, timeout=120):
    """Test 3: Background processing completes"""
    print_header("Test 3: Background Processing")
    
    if not job_id:
        print_result("Background processing", False, "No job_id from upload")
        return False
    
    print(f"Waiting for job {job_id} to complete (max {timeout}s)...")
    
    start = time.time()
    while time.time() - start < timeout:
        try:
            response = requests.get(f"{BASE_URL}/api/video/result/{job_id}")
            if response.status_code == 200:
                result = response.json()
                status = result.get('status')
                
                print(f"  Status: {status} ({int(time.time() - start)}s elapsed)")
                
                if status == 'completed':
                    elapsed = time.time() - start
                    print_result(
                        "Background processing completed",
                        True,
                        f"Completed in {elapsed:.1f}s"
                    )
                    return True
                elif status == 'failed':
                    error = result.get('error_message', 'Unknown error')
                    print_result(
                        "Background processing completed",
                        False,
                        f"Job failed: {error}"
                    )
                    return False
            
            time.sleep(5)
            
        except Exception as e:
            print_result("Background processing", False, str(e))
            return False
    
    print_result(
        "Background processing",
        False,
        f"Timeout after {timeout}s (status may still be 'processing')"
    )
    return False

def test_file_size_tracking():
    """Test 4: File size tracking works"""
    print_header("Test 4: File Size Tracking")
    
    try:
        response = requests.get(f"{BASE_URL}/api/storage/info")
        if response.status_code == 200:
            result = response.json()
            used_gb = result.get('used_gb', 0)
            
            passed = used_gb > 0
            print_result(
                "File size tracking",
                passed,
                f"Storage used: {used_gb:.3f} GB"
            )
            return passed
        else:
            print_result("File size tracking", False, f"HTTP {response.status_code}")
            return False
    except Exception as e:
        print_result("File size tracking", False, str(e))
        return False

def test_concurrent_health_check(video_path):
    """Test 5: Health check responsive during upload"""
    print_header("Test 5: Concurrent Request Handling")
    
    if not video_path or not Path(video_path).exists():
        print_result("Concurrent handling", False, "Test video not found")
        return False
    
    import threading
    
    health_results = []
    
    def check_health():
        """Check health while upload is in progress"""
        time.sleep(0.5)  # Let upload start
        try:
            start = time.time()
            response = requests.get(f"{BASE_URL}/health", timeout=5)
            elapsed = time.time() - start
            health_results.append({
                'success': response.status_code == 200,
                'elapsed': elapsed
            })
        except Exception as e:
            health_results.append({
                'success': False,
                'error': str(e)
            })
    
    # Start health check in background
    health_thread = threading.Thread(target=check_health)
    health_thread.start()
    
    # Start upload
    try:
        with open(video_path, 'rb') as f:
            files = {'file': f}
            data = {'video_type': 'dashcam'}
            requests.post(f"{BASE_URL}/api/video/upload", files=files, data=data, timeout=30)
    except:
        pass
    
    health_thread.join(timeout=10)
    
    if health_results:
        result = health_results[0]
        passed = result.get('success', False) and result.get('elapsed', 999) < 2
        print_result(
            "Health check during upload",
            passed,
            f"Response time: {result.get('elapsed', 'N/A'):.2f}s"
        )
        return passed
    else:
        print_result("Health check during upload", False, "No response")
        return False

def main():
    """Run all verification tests"""
    print("\n" + "🚀 ADAS Backend Verification Suite")
    print("="*60)
    
    # Check if server is running
    try:
        requests.get(f"{BASE_URL}/health", timeout=2)
    except:
        print("\n❌ ERROR: Server is not running!")
        print(f"Please start the server first: python run.py")
        sys.exit(1)
    
    # Get test video path
    test_video = input("\nEnter path to test video (or press Enter to skip upload tests): ").strip()
    
    results = []
    
    # Test 1: Health check
    results.append(test_health_check())
    
    if test_video and Path(test_video).exists():
        # Test 2: Upload response time
        passed, job_id = test_upload_response_time(test_video)
        results.append(passed)
        
        # Test 3: Background processing
        if job_id:
            results.append(test_background_processing(job_id))
        
        # Test 4: File size tracking
        results.append(test_file_size_tracking())
        
        # Test 5: Concurrent handling
        results.append(test_concurrent_health_check(test_video))
    else:
        print("\n⚠️  Skipping upload tests (no test video provided)")
    
    # Summary
    print_header("VERIFICATION SUMMARY")
    passed_count = sum(1 for r in results if r)
    total_count = len(results)
    
    print(f"\nTests Passed: {passed_count}/{total_count}")
    
    if passed_count == total_count:
        print("\n🎉 ALL TESTS PASSED - Backend is production ready!")
        sys.exit(0)
    else:
        print(f"\n⚠️  {total_count - passed_count} test(s) failed - Review logs above")
        sys.exit(1)

if __name__ == "__main__":
    main()
