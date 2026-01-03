"""
ADAS API Testing Script - Complete Test Suite
==============================================
Test all critical endpoints of BE-ADAS system

Author: Senior ADAS Engineer
Date: 2025-01-03
"""

import requests
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional
import hashlib

# Configuration
BASE_URL = "https://adas-api.aiotlab.edu.vn"  # Production
# BASE_URL = "http://localhost:52000"  # Development

class Colors:
    """ANSI color codes for terminal output"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

class ADASAPITester:
    """Complete test suite for ADAS API"""
    
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/')
        self.token: Optional[str] = None
        self.session_id: Optional[str] = None
        self.job_id: Optional[str] = None
        self.video_id: Optional[int] = None
        
    def print_header(self, text: str):
        """Print section header"""
        print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*70}{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.CYAN}{text:^70}{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.CYAN}{'='*70}{Colors.RESET}\n")
    
    def print_test(self, name: str, status: str, details: str = ""):
        """Print test result"""
        if status == "PASS":
            icon = "✅"
            color = Colors.GREEN
        elif status == "FAIL":
            icon = "❌"
            color = Colors.RED
        else:
            icon = "⚠️"
            color = Colors.YELLOW
        
        print(f"{icon} {Colors.BOLD}{name}{Colors.RESET}: {color}{status}{Colors.RESET}")
        if details:
            print(f"   {Colors.BLUE}→{Colors.RESET} {details}")
    
    def test_health(self) -> bool:
        """Test 1: Health Check"""
        self.print_header("TEST 1: HEALTH CHECK")
        
        try:
            response = requests.get(f"{self.base_url}/health", timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                self.print_test("Health Check", "PASS", 
                    f"Status: {data.get('status')}, Version: {data.get('version')}")
                
                # Check Cloudflare
                cf_info = data.get('cloudflare', {})
                if cf_info.get('detected'):
                    self.print_test("Cloudflare Detection", "PASS",
                        f"CF-Ray: {cf_info.get('cf_ray')}")
                else:
                    self.print_test("Cloudflare Detection", "WARN",
                        "Not behind Cloudflare proxy")
                
                return True
            else:
                self.print_test("Health Check", "FAIL", 
                    f"Status code: {response.status_code}")
                return False
                
        except Exception as e:
            self.print_test("Health Check", "FAIL", str(e))
            return False
    
    def test_authentication(self) -> bool:
        """Test 2: Authentication"""
        self.print_header("TEST 2: AUTHENTICATION")
        
        try:
            # Test login
            response = requests.post(
                f"{self.base_url}/api/auth/login",
                json={"username": "admin", "password": "admin123"},
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                self.token = data.get('token')
                user = data.get('user', {})
                
                self.print_test("Login", "PASS",
                    f"User: {user.get('username')}, Role: {user.get('role')}")
                
                # Test get current user
                headers = {"Authorization": f"Bearer {self.token}"}
                response = requests.get(
                    f"{self.base_url}/api/auth/me",
                    headers=headers,
                    timeout=10
                )
                
                if response.status_code == 200:
                    self.print_test("Get Current User", "PASS")
                    return True
                else:
                    self.print_test("Get Current User", "FAIL")
                    return False
            else:
                self.print_test("Login", "FAIL", f"Status: {response.status_code}")
                return False
                
        except Exception as e:
            self.print_test("Authentication", "FAIL", str(e))
            return False
    
    def test_models(self) -> bool:
        """Test 3: AI Models"""
        self.print_header("TEST 3: AI MODELS MANAGEMENT")
        
        try:
            response = requests.get(
                f"{self.base_url}/api/models/available",
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                models = data.get('models', [])
                total = data.get('total_models', 0)
                
                self.print_test("Get Available Models", "PASS",
                    f"Total models: {total}")
                
                # Check essential models
                essential = ['yolo11n', 'mediapipe-face']
                for model_id in essential:
                    model = next((m for m in models if m['id'] == model_id), None)
                    if model:
                        status = "Downloaded" if model.get('downloaded') else "Not Downloaded"
                        self.print_test(f"Model {model_id}", "PASS",
                            f"{model.get('name')} - {status}")
                    else:
                        self.print_test(f"Model {model_id}", "WARN", "Not found")
                
                return True
            else:
                self.print_test("Get Available Models", "FAIL")
                return False
                
        except Exception as e:
            self.print_test("AI Models", "FAIL", str(e))
            return False
    
    def test_video_upload(self, video_path: Optional[str] = None) -> bool:
        """Test 4: Video Upload"""
        self.print_header("TEST 4: VIDEO UPLOAD & PROCESSING")
        
        if not video_path:
            self.print_test("Video Upload", "SKIP", 
                "No video file provided. Use: tester.test_video_upload('/path/to/video.mp4')")
            return True
        
        video_file = Path(video_path)
        if not video_file.exists():
            self.print_test("Video Upload", "FAIL", f"File not found: {video_path}")
            return False
        
        try:
            # Upload video
            with open(video_file, 'rb') as f:
                files = {'file': (video_file.name, f, 'video/mp4')}
                data = {
                    'video_type': 'dashcam',
                    'device': 'cpu'
                }
                
                print(f"{Colors.BLUE}Uploading {video_file.name}...{Colors.RESET}")
                response = requests.post(
                    f"{self.base_url}/api/video/upload",
                    files=files,
                    data=data,
                    timeout=300  # 5 minutes timeout
                )
            
            if response.status_code == 200:
                data = response.json()
                self.job_id = data.get('job_id')
                
                self.print_test("Video Upload", "PASS",
                    f"Job ID: {self.job_id}")
                
                # Poll for result
                return self.test_job_status()
            else:
                self.print_test("Video Upload", "FAIL",
                    f"Status: {response.status_code}, Response: {response.text[:200]}")
                return False
                
        except Exception as e:
            self.print_test("Video Upload", "FAIL", str(e))
            return False
    
    def test_job_status(self) -> bool:
        """Test job status polling"""
        if not self.job_id:
            self.print_test("Job Status", "SKIP", "No job_id available")
            return True
        
        try:
            max_attempts = 60  # 5 minutes max
            attempt = 0
            
            while attempt < max_attempts:
                response = requests.get(
                    f"{self.base_url}/api/video/result/{self.job_id}",
                    timeout=10
                )
                
                if response.status_code == 200:
                    data = response.json()
                    status = data.get('status')
                    progress = data.get('progress', 0)
                    
                    print(f"{Colors.YELLOW}Status: {status}, Progress: {progress}%{Colors.RESET}", end='\r')
                    
                    if status == 'completed':
                        events = data.get('events', [])
                        self.print_test("Video Processing", "PASS",
                            f"Detected {len(events)} events")
                        return True
                    elif status == 'failed':
                        self.print_test("Video Processing", "FAIL",
                            data.get('error', 'Unknown error'))
                        return False
                    
                    time.sleep(5)
                    attempt += 1
                else:
                    self.print_test("Job Status", "FAIL", f"Status: {response.status_code}")
                    return False
            
            self.print_test("Video Processing", "WARN", "Timeout waiting for completion")
            return False
            
        except Exception as e:
            self.print_test("Job Status", "FAIL", str(e))
            return False
    
    def test_streaming(self) -> bool:
        """Test 5: Real-time Streaming"""
        self.print_header("TEST 5: REAL-TIME STREAMING")
        
        try:
            # Start stream
            response = requests.post(
                f"{self.base_url}/api/stream/start",
                json={
                    "source": "webcam",
                    "model_id": "yolo11n"
                },
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                self.session_id = data.get('session_id')
                
                self.print_test("Start Stream", "PASS",
                    f"Session ID: {self.session_id}")
                
                # Poll stream a few times
                for i in range(3):
                    response = requests.get(
                        f"{self.base_url}/api/stream/poll/{self.session_id}",
                        timeout=10
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        detections = data.get('detections', [])
                        fps = data.get('fps', 0)
                        
                        print(f"   Poll {i+1}: {len(detections)} detections, FPS: {fps}")
                        time.sleep(0.2)
                
                self.print_test("Stream Polling", "PASS")
                
                # Stop stream
                response = requests.post(
                    f"{self.base_url}/api/stream/stop",
                    json={"session_id": self.session_id},
                    timeout=10
                )
                
                if response.status_code == 200:
                    self.print_test("Stop Stream", "PASS")
                    return True
                
            return False
            
        except Exception as e:
            self.print_test("Streaming", "FAIL", str(e))
            return False
    
    def test_statistics(self) -> bool:
        """Test 6: Statistics & Analytics"""
        self.print_header("TEST 6: STATISTICS & ANALYTICS")
        
        try:
            # Get summary
            response = requests.get(
                f"{self.base_url}/api/statistics/summary",
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                self.print_test("Statistics Summary", "PASS",
                    f"Videos: {data.get('total_videos')}, "
                    f"Detections: {data.get('total_detections')}, "
                    f"Events: {data.get('total_events')}")
                
                # Get detection stats
                response = requests.get(
                    f"{self.base_url}/api/detections/stats",
                    timeout=10
                )
                
                if response.status_code == 200:
                    data = response.json()
                    self.print_test("Detection Stats", "PASS",
                        f"Total: {data.get('total_detections')}")
                    return True
            
            return False
            
        except Exception as e:
            self.print_test("Statistics", "FAIL", str(e))
            return False
    
    def test_settings(self) -> bool:
        """Test 7: System Settings"""
        self.print_header("TEST 7: SYSTEM SETTINGS")
        
        try:
            # Get settings
            response = requests.get(
                f"{self.base_url}/api/settings",
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                settings = data.get('settings', {})
                
                self.print_test("Get Settings", "PASS",
                    f"Confidence threshold: {settings.get('detection', {}).get('confidence_threshold')}")
                
                # Get cameras
                response = requests.get(
                    f"{self.base_url}/api/settings/cameras",
                    timeout=10
                )
                
                if response.status_code == 200:
                    data = response.json()
                    cameras = data.get('cameras', [])
                    self.print_test("Get Cameras", "PASS",
                        f"Total cameras: {len(cameras)}")
                    return True
            
            return False
            
        except Exception as e:
            self.print_test("Settings", "FAIL", str(e))
            return False
    
    def test_storage(self) -> bool:
        """Test 8: Storage Management"""
        self.print_header("TEST 8: STORAGE MANAGEMENT")
        
        try:
            response = requests.get(
                f"{self.base_url}/api/storage/info",
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                self.print_test("Storage Info", "PASS",
                    f"Used: {data.get('used_gb')}GB / {data.get('total_gb')}GB, "
                    f"Files: {data.get('files_count')}")
                return True
            else:
                self.print_test("Storage Info", "FAIL")
                return False
                
        except Exception as e:
            self.print_test("Storage", "FAIL", str(e))
            return False
    
    def run_all_tests(self, video_path: Optional[str] = None):
        """Run complete test suite"""
        print(f"\n{Colors.BOLD}{Colors.GREEN}{'='*70}{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.GREEN}ADAS API COMPLETE TEST SUITE{Colors.RESET:^70}")
        print(f"{Colors.BOLD}{Colors.GREEN}Base URL: {self.base_url}{Colors.RESET:^70}")
        print(f"{Colors.BOLD}{Colors.GREEN}{'='*70}{Colors.RESET}\n")
        
        results = {
            "Health Check": self.test_health(),
            "Authentication": self.test_authentication(),
            "AI Models": self.test_models(),
            "Video Upload": self.test_video_upload(video_path),
            "Streaming": self.test_streaming(),
            "Statistics": self.test_statistics(),
            "Settings": self.test_settings(),
            "Storage": self.test_storage()
        }
        
        # Summary
        self.print_header("TEST SUMMARY")
        
        passed = sum(1 for v in results.values() if v)
        total = len(results)
        
        for test_name, result in results.items():
            status = "PASS" if result else "FAIL"
            self.print_test(test_name, status)
        
        print(f"\n{Colors.BOLD}Total: {passed}/{total} tests passed{Colors.RESET}")
        
        if passed == total:
            print(f"{Colors.GREEN}{Colors.BOLD}🎉 ALL TESTS PASSED! System is ready for production!{Colors.RESET}\n")
        else:
            print(f"{Colors.YELLOW}{Colors.BOLD}⚠️  Some tests failed. Please check the logs above.{Colors.RESET}\n")


def main():
    """Main test runner"""
    print(f"{Colors.CYAN}ADAS API Testing Script{Colors.RESET}")
    print(f"{Colors.CYAN}{'='*70}{Colors.RESET}\n")
    
    # Initialize tester
    tester = ADASAPITester(BASE_URL)
    
    # Run all tests
    # To test video upload, provide path to video file:
    # tester.run_all_tests(video_path="/path/to/test_video.mp4")
    tester.run_all_tests()
    
    print(f"\n{Colors.BLUE}💡 Tips:{Colors.RESET}")
    print(f"   • To test video upload: tester.run_all_tests(video_path='/path/to/video.mp4')")
    print(f"   • Change BASE_URL to test different environments")
    print(f"   • Check /docs for interactive API documentation\n")


if __name__ == "__main__":
    main()
