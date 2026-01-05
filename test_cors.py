#!/usr/bin/env python3
"""
CORS Preflight Test Script
===========================
Tests OPTIONS and GET requests to verify CORS configuration.

Usage:
    python test_cors.py

Requirements:
    pip install requests
"""

import requests
import json
from typing import Optional

# Configuration
API_BASE_URL = "https://adas-api.aiotlab.edu.vn"
FRONTEND_ORIGIN = "https://your-frontend-domain.com"  # Replace with your actual frontend URL
TEST_ENDPOINT = "/api/auth/me"

# Colors for terminal output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'

def print_header(text: str):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.END}\n")

def print_success(text: str):
    print(f"{Colors.GREEN}✅ {text}{Colors.END}")

def print_error(text: str):
    print(f"{Colors.RED}❌ {text}{Colors.END}")

def print_info(text: str):
    print(f"{Colors.YELLOW}ℹ️  {text}{Colors.END}")

def test_options_preflight():
    """Test OPTIONS preflight request"""
    print_header("Test 1: OPTIONS Preflight Request")
    
    url = f"{API_BASE_URL}{TEST_ENDPOINT}"
    headers = {
        "Origin": FRONTEND_ORIGIN,
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "authorization,content-type"
    }
    
    print_info(f"Sending OPTIONS to: {url}")
    print_info(f"Origin: {FRONTEND_ORIGIN}")
    
    try:
        response = requests.options(url, headers=headers, timeout=10)
        
        print(f"\nStatus Code: {response.status_code}")
        
        # Check CORS headers
        cors_headers = {
            "Access-Control-Allow-Origin": response.headers.get("Access-Control-Allow-Origin"),
            "Access-Control-Allow-Methods": response.headers.get("Access-Control-Allow-Methods"),
            "Access-Control-Allow-Headers": response.headers.get("Access-Control-Allow-Headers"),
            "Access-Control-Allow-Credentials": response.headers.get("Access-Control-Allow-Credentials"),
            "Access-Control-Max-Age": response.headers.get("Access-Control-Max-Age"),
        }
        
        print("\nCORS Headers:")
        for header, value in cors_headers.items():
            if value:
                print(f"  {header}: {value}")
        
        # Validate
        if response.status_code == 200:
            print_success("OPTIONS request successful!")
            
            if cors_headers.get("Access-Control-Allow-Origin"):
                print_success("CORS headers present")
            else:
                print_error("CORS headers missing!")
                
            if cors_headers.get("Access-Control-Allow-Credentials") == "true":
                print_success("Credentials allowed")
            else:
                print_error("Credentials not allowed!")
                
            return True
        else:
            print_error(f"OPTIONS request failed with status {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print_error(f"Request failed: {e}")
        return False

def test_get_without_auth():
    """Test GET request without authentication (should fail with 401)"""
    print_header("Test 2: GET Request Without Authentication")
    
    url = f"{API_BASE_URL}{TEST_ENDPOINT}"
    headers = {
        "Origin": FRONTEND_ORIGIN,
    }
    
    print_info(f"Sending GET to: {url}")
    print_info("No Authorization header (should return 401)")
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        print(f"\nStatus Code: {response.status_code}")
        
        if response.status_code == 401:
            print_success("Correctly rejected unauthenticated request")
            return True
        else:
            print_error(f"Expected 401, got {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print_error(f"Request failed: {e}")
        return False

def test_get_with_auth(token: Optional[str] = None):
    """Test GET request with authentication"""
    print_header("Test 3: GET Request With Authentication")
    
    if not token:
        print_info("No token provided. Skipping authenticated request test.")
        print_info("To test with authentication, run:")
        print_info(f"  python test_cors.py YOUR_SUPABASE_JWT_TOKEN")
        return None
    
    url = f"{API_BASE_URL}{TEST_ENDPOINT}"
    headers = {
        "Origin": FRONTEND_ORIGIN,
        "Authorization": f"Bearer {token}"
    }
    
    print_info(f"Sending GET to: {url}")
    print_info(f"Authorization: Bearer {token[:20]}...")
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        print(f"\nStatus Code: {response.status_code}")
        
        if response.status_code == 200:
            print_success("Authenticated request successful!")
            
            try:
                data = response.json()
                print("\nResponse Data:")
                print(json.dumps(data, indent=2))
                return True
            except:
                print(f"Response: {response.text}")
                return True
        else:
            print_error(f"Request failed with status {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print_error(f"Request failed: {e}")
        return False

def main():
    import sys
    
    print(f"{Colors.BOLD}CORS Preflight Test Suite{Colors.END}")
    print(f"API: {API_BASE_URL}")
    print(f"Origin: {FRONTEND_ORIGIN}")
    
    # Get token from command line if provided
    token = sys.argv[1] if len(sys.argv) > 1 else None
    
    # Run tests
    results = []
    
    results.append(("OPTIONS Preflight", test_options_preflight()))
    results.append(("GET Without Auth", test_get_without_auth()))
    
    if token:
        results.append(("GET With Auth", test_get_with_auth(token)))
    
    # Summary
    print_header("Test Summary")
    
    passed = sum(1 for _, result in results if result is True)
    failed = sum(1 for _, result in results if result is False)
    skipped = sum(1 for _, result in results if result is None)
    
    for test_name, result in results:
        if result is True:
            print_success(f"{test_name}: PASSED")
        elif result is False:
            print_error(f"{test_name}: FAILED")
        else:
            print_info(f"{test_name}: SKIPPED")
    
    print(f"\n{Colors.BOLD}Total: {passed} passed, {failed} failed, {skipped} skipped{Colors.END}\n")
    
    if failed == 0 and passed > 0:
        print_success("All tests passed! CORS is configured correctly. ✨")
        return 0
    elif failed > 0:
        print_error("Some tests failed. Please check the configuration.")
        return 1
    else:
        print_info("No tests completed.")
        return 1

if __name__ == "__main__":
    exit(main())
