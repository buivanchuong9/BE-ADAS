"""
COMPREHENSIVE API ERROR CHECK
==============================
Test all critical endpoints for common errors
"""

import sys
import traceback
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

def check_imports():
    """Check all critical imports"""
    print("=" * 80)
    print("CHECKING IMPORTS")
    print("=" * 80)
    
    errors = []
    
    # Check service imports
    try:
        from backend.app.services.video_service import VideoService
        print("✓ VideoService imported")
    except Exception as e:
        errors.append(("VideoService", str(e)))
        print(f"✗ VideoService: {e}")
    
    try:
        from backend.app.services.job_service import JobService, get_job_service
        print("✓ JobService imported")
    except Exception as e:
        errors.append(("JobService", str(e)))
        print(f"✗ JobService: {e}")
    
    # Check API routers
    try:
        from backend.app.api.video import router
        print("✓ video router imported")
    except Exception as e:
        errors.append(("video router", str(e)))
        print(f"✗ video router: {e}")
        traceback.print_exc()
    
    try:
        from backend.app.api.upload_storage import router
        print("✓ upload_storage router imported")
    except Exception as e:
        errors.append(("upload_storage router", str(e)))
        print(f"✗ upload_storage router: {e}")
    
    # Check repositories
    try:
        from backend.app.db.repositories.video_job_repo import VideoJobRepository
        print("✓ VideoJobRepository imported")
    except Exception as e:
        errors.append(("VideoJobRepository", str(e)))
        print(f"✗ VideoJobRepository: {e}")
    
    # Check exceptions
    try:
        from backend.app.core.exceptions import ValidationError
        print("✓ ValidationError imported")
    except Exception as e:
        errors.append(("ValidationError", str(e)))
        print(f"✗ ValidationError: {e}")
    
    return errors


def check_method_signatures():
    """Check critical method signatures"""
    print("\n" + "=" * 80)
    print("CHECKING METHOD SIGNATURES")
    print("=" * 80)
    
    try:
        from backend.app.services.video_service import VideoService
        import inspect
        
        # Check __init__
        sig = inspect.signature(VideoService.__init__)
        params = list(sig.parameters.keys())
        print(f"VideoService.__init__ parameters: {params}")
        
        if 'session' in params:
            print("✓ VideoService.__init__ accepts 'session'")
        else:
            print("✗ VideoService.__init__ missing 'session'")
        
        # Check validate_video
        sig = inspect.signature(VideoService.validate_video)
        params = list(sig.parameters.keys())
        print(f"VideoService.validate_video parameters: {params}")
        
        if 'file' in params:
            print("✓ VideoService.validate_video accepts 'file'")
        else:
            print("✗ VideoService.validate_video missing 'file'")
        
        # Check create_job
        sig = inspect.signature(VideoService.create_job)
        params = list(sig.parameters.keys())
        print(f"VideoService.create_job parameters: {params}")
        
        if 'session' not in params:
            print("✓ VideoService.create_job does NOT require session param (uses self.session)")
        else:
            print("⚠ VideoService.create_job has session param (should use self.session)")
        
        # Check save_uploaded_video
        sig = inspect.signature(VideoService.save_uploaded_video)
        params = list(sig.parameters.keys())
        print(f"VideoService.save_uploaded_video parameters: {params}")
        
        if 'file' in params and 'session' not in params:
            print("✓ VideoService.save_uploaded_video signature correct")
        else:
            print("✗ VideoService.save_uploaded_video signature incorrect")
            
    except Exception as e:
        print(f"✗ Error checking VideoService: {e}")
        traceback.print_exc()
        return False
    
    return True


def check_potential_runtime_errors():
    """Check for potential runtime errors"""
    print("\n" + "=" * 80)
    print("CHECKING POTENTIAL RUNTIME ERRORS")
    print("=" * 80)
    
    issues = []
    
    # Check for UploadFile.seek usage
    try:
        with open('backend/app/services/video_service.py', 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Check for problematic seek patterns
        if 'file.seek(0, 2)' in content:
            issues.append("❌ CRITICAL: file.seek(0, 2) found - FastAPI UploadFile.seek() only takes offset!")
        elif 'await file.seek(0)' in content:
            print("✓ file.seek(0) usage correct (single parameter)")
        
        # Check for file.read() usage
        if 'await file.read()' in content:
            print("✓ file.read() used for getting content")
        
        # Check for file.size usage
        if 'file.size' in content:
            print("✓ file.size attribute checked")
            
    except Exception as e:
        issues.append(f"Error reading video_service.py: {e}")
    
    # Check API endpoint exception handling
    try:
        with open('backend/app/api/video.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        if 'except ValidationError' in content:
            print("✓ ValidationError exception handling present")
        else:
            issues.append("⚠ No ValidationError exception handling in video.py")
        
        if 'except HTTPException' in content:
            print("✓ HTTPException re-raising present")
        else:
            issues.append("⚠ No HTTPException re-raising in video.py")
            
    except Exception as e:
        issues.append(f"Error reading video.py: {e}")
    
    return issues


def main():
    print("=" * 80)
    print("COMPREHENSIVE API ERROR CHECK")
    print("=" * 80)
    print()
    
    import_errors = check_imports()
    signature_ok = check_method_signatures()
    runtime_issues = check_potential_runtime_errors()
    
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    
    if import_errors:
        print(f"\n❌ IMPORT ERRORS ({len(import_errors)}):")
        for name, error in import_errors:
            print(f"  - {name}: {error}")
    else:
        print("\n✓ All imports successful")
    
    if not signature_ok:
        print("\n❌ METHOD SIGNATURE ERRORS")
    else:
        print("\n✓ All method signatures correct")
    
    if runtime_issues:
        print(f"\n❌ POTENTIAL RUNTIME ISSUES ({len(runtime_issues)}):")
        for issue in runtime_issues:
            print(f"  - {issue}")
    else:
        print("\n✓ No potential runtime issues detected")
    
    all_ok = not import_errors and signature_ok and not runtime_issues
    
    print("\n" + "=" * 80)
    if all_ok:
        print("✅ ALL CHECKS PASSED - API READY")
    else:
        print("❌ ISSUES DETECTED - REVIEW ERRORS ABOVE")
    print("=" * 80)
    
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
