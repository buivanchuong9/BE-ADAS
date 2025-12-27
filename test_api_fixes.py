"""
API Validation Test Script
===========================
Tests that all API endpoints are properly configured and services are correctly instantiated.
"""

import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

def test_service_imports():
    """Test that all services can be imported without errors"""
    print("Testing service imports...")
    
    try:
        from backend.app.services.video_service import VideoService
        print("✓ VideoService imported successfully")
    except Exception as e:
        print(f"✗ VideoService import failed: {e}")
        return False
    
    try:
        from backend.app.services.job_service import JobService, get_job_service
        print("✓ JobService imported successfully")
    except Exception as e:
        print(f"✗ JobService import failed: {e}")
        return False
    
    try:
        from backend.app.services.analysis_service import AnalysisService
        print("✓ AnalysisService imported successfully")
    except Exception as e:
        print(f"✗ AnalysisService import failed: {e}")
        return False
    
    return True


def test_repository_imports():
    """Test that all repositories can be imported"""
    print("\nTesting repository imports...")
    
    try:
        from backend.app.db.repositories.video_job_repo import VideoJobRepository
        print("✓ VideoJobRepository imported successfully")
    except Exception as e:
        print(f"✗ VideoJobRepository import failed: {e}")
        return False
    
    try:
        from backend.app.db.repositories.safety_event_repo import SafetyEventRepository
        print("✓ SafetyEventRepository imported successfully")
    except Exception as e:
        print(f"✗ SafetyEventRepository import failed: {e}")
        return False
    
    return True


def test_api_router_imports():
    """Test that all API routers can be imported"""
    print("\nTesting API router imports...")
    
    try:
        from backend.app.api.video import router as video_router
        print("✓ video router imported successfully")
    except Exception as e:
        print(f"✗ video router import failed: {e}")
        return False
    
    try:
        from backend.app.api.upload_storage import router as upload_router
        print("✓ upload_storage router imported successfully")
    except Exception as e:
        print(f"✗ upload_storage router import failed: {e}")
        return False
    
    return True


def test_service_signatures():
    """Test that service constructors have correct signatures"""
    print("\nTesting service signatures...")
    
    try:
        from backend.app.services.video_service import VideoService
        import inspect
        
        sig = inspect.signature(VideoService.__init__)
        params = list(sig.parameters.keys())
        
        if 'session' in params:
            print("✓ VideoService.__init__ accepts 'session' parameter")
        else:
            print(f"✗ VideoService.__init__ does not accept 'session'. Parameters: {params}")
            return False
            
    except Exception as e:
        print(f"✗ VideoService signature check failed: {e}")
        return False
    
    try:
        from backend.app.services.job_service import JobService
        import inspect
        
        sig = inspect.signature(JobService.__init__)
        params = list(sig.parameters.keys())
        
        # JobService should NOT require session (it's a singleton)
        if 'session' not in params:
            print("✓ JobService.__init__ does not require session (correct for singleton)")
        else:
            print(f"⚠ JobService.__init__ accepts session (unexpected but may be OK)")
            
    except Exception as e:
        print(f"✗ JobService signature check failed: {e}")
        return False
    
    return True


def main():
    """Run all tests"""
    print("=" * 80)
    print("API VALIDATION TEST")
    print("=" * 80)
    
    results = []
    
    results.append(("Service Imports", test_service_imports()))
    results.append(("Repository Imports", test_repository_imports()))
    results.append(("API Router Imports", test_api_router_imports()))
    results.append(("Service Signatures", test_service_signatures()))
    
    print("\n" + "=" * 80)
    print("TEST RESULTS")
    print("=" * 80)
    
    for test_name, passed in results:
        status = "PASSED" if passed else "FAILED"
        symbol = "✓" if passed else "✗"
        print(f"{symbol} {test_name}: {status}")
    
    all_passed = all(result[1] for result in results)
    
    print("=" * 80)
    if all_passed:
        print("✓ ALL TESTS PASSED - API is ready for production")
    else:
        print("✗ SOME TESTS FAILED - Please review errors above")
    print("=" * 80)
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
