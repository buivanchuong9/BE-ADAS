#!/usr/bin/env python3
"""
Quick API test script for ADAS Backend
Tests all Phase 1 critical endpoints
"""

import requests
import json
from datetime import datetime

BASE_URL = "https://adas-api.aiotlab.edu.vn"

def print_response(title, response):
    print(f"\n{'='*60}")
    print(f"TEST: {title}")
    print(f"{'='*60}")
    print(f"Status Code: {response.status_code}")
    try:
        data = response.json()
        print(json.dumps(data, indent=2))
    except:
        print(response.text)
    print()

def test_health():
    """Test health endpoint"""
    response = requests.get(f"{BASE_URL}/health")
    print_response("Health Check", response)
    return response.status_code == 200

def test_models_available():
    """Test models available endpoint"""
    response = requests.get(f"{BASE_URL}/api/models/available")
    print_response("GET /api/models/available", response)
    return response.status_code == 200

def test_dataset_list():
    """Test dataset list endpoint"""
    response = requests.get(f"{BASE_URL}/api/dataset")
    print_response("GET /api/dataset", response)
    return response.status_code == 200

def test_detections_recent():
    """Test recent detections endpoint"""
    response = requests.get(f"{BASE_URL}/api/detections/recent?limit=5")
    print_response("GET /api/detections/recent", response)
    return response.status_code == 200

def test_detections_stats():
    """Test detection stats endpoint"""
    response = requests.get(f"{BASE_URL}/api/detections/stats")
    print_response("GET /api/detections/stats", response)
    return response.status_code == 200

def test_stream_start():
    """Test stream start endpoint"""
    payload = {
        "source": "webcam",
        "model_id": "yolo11n"
    }
    response = requests.post(f"{BASE_URL}/api/stream/start", json=payload)
    print_response("POST /api/stream/start", response)
    
    if response.status_code == 200:
        data = response.json()
        session_id = data.get("session_id")
        if session_id:
            # Test polling
            poll_response = requests.get(f"{BASE_URL}/api/stream/poll/{session_id}")
            print_response(f"GET /api/stream/poll/{session_id}", poll_response)
            
            # Stop stream
            stop_payload = {"session_id": session_id}
            stop_response = requests.post(f"{BASE_URL}/api/stream/stop", json=stop_payload)
            print_response("POST /api/stream/stop", stop_response)
    
    return response.status_code == 200

def test_events_list():
    """Test events list endpoint"""
    response = requests.get(f"{BASE_URL}/api/events/list")
    print_response("GET /api/events/list", response)
    return response.status_code == 200

def test_alerts_latest():
    """Test latest alerts endpoint"""
    response = requests.get(f"{BASE_URL}/api/alerts/latest")
    print_response("GET /api/alerts/latest", response)
    return response.status_code == 200

def test_videos_list():
    """Test videos list endpoint"""
    response = requests.get(f"{BASE_URL}/api/videos/list")
    print_response("GET /api/videos/list", response)
    return response.status_code == 200

def test_statistics_summary():
    """Test statistics summary endpoint"""
    response = requests.get(f"{BASE_URL}/api/statistics/summary")
    print_response("GET /api/statistics/summary", response)
    return response.status_code == 200

def run_all_tests():
    """Run all API tests"""
    print(f"\n{'#'*60}")
    print(f"# ADAS Backend API Test Suite")
    print(f"# Base URL: {BASE_URL}")
    print(f"# Time: {datetime.now().isoformat()}")
    print(f"{'#'*60}\n")
    
    tests = [
        ("Health Check", test_health),
        ("Models Available", test_models_available),
        ("Dataset List", test_dataset_list),
        ("Recent Detections", test_detections_recent),
        ("Detection Stats", test_detections_stats),
        ("Stream Start/Poll/Stop", test_stream_start),
        ("Events List", test_events_list),
        ("Latest Alerts", test_alerts_latest),
        ("Videos List", test_videos_list),
        ("Statistics Summary", test_statistics_summary),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            success = test_func()
            results.append((name, "✅ PASS" if success else "❌ FAIL"))
        except Exception as e:
            results.append((name, f"❌ ERROR: {str(e)}"))
    
    # Print summary
    print(f"\n{'='*60}")
    print("TEST SUMMARY")
    print(f"{'='*60}")
    for name, result in results:
        print(f"{name:30} {result}")
    print(f"{'='*60}\n")
    
    passed = sum(1 for _, r in results if "PASS" in r)
    total = len(results)
    print(f"TOTAL: {passed}/{total} tests passed")
    
    return passed == total

if __name__ == "__main__":
    success = run_all_tests()
    exit(0 if success else 1)
