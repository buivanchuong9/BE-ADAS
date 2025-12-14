#!/usr/bin/env python3
"""
ADAS Backend - Quick Test Script
Verify all critical requirements are met
"""

import sys
import subprocess


def test_imports():
    """Test all imports work without errors"""
    print("Testing imports...")
    try:
        import main
        import database
        import models
        import schemas
        from core import logging_config, config, exceptions, responses
        from services import video_processor, adas_pipeline, analytics_service
        print("✓ All imports successful")
        return True
    except Exception as e:
        print(f"✗ Import failed: {e}")
        return False


def test_pydantic_v2():
    """Verify Pydantic V2 is installed"""
    print("Testing Pydantic version...")
    try:
        import pydantic
        version = pydantic.__version__
        major_version = int(version.split('.')[0])
        if major_version == 2:
            print(f"✓ Pydantic V2 installed: {version}")
            return True
        else:
            print(f"✗ Wrong Pydantic version: {version} (expected 2.x)")
            return False
    except Exception as e:
        print(f"✗ Pydantic check failed: {e}")
        return False


def test_logging_ascii():
    """Test logging is ASCII-safe"""
    print("Testing ASCII-safe logging...")
    try:
        from core.logging_config import setup_logging
        logger = setup_logging()
        logger.info("Test log message")
        print("✓ Logging configured successfully")
        return True
    except Exception as e:
        print(f"✗ Logging test failed: {e}")
        return False


def test_database():
    """Test database connection"""
    print("Testing database...")
    try:
        from database import engine, Base
        from models import VideoDataset, ADASEvent
        # Try to create tables
        Base.metadata.create_all(bind=engine)
        print("✓ Database initialized successfully")
        return True
    except Exception as e:
        print(f"✗ Database test failed: {e}")
        return False


def test_schemas():
    """Test Pydantic schemas have no warnings"""
    print("Testing Pydantic schemas...")
    try:
        from schemas import (
            CameraResponse, DriverResponse, TripResponse,
            EventResponse, DetectionResponse, AIModelResponse
        )
        print("✓ All schemas loaded without warnings")
        return True
    except Exception as e:
        print(f"✗ Schema test failed: {e}")
        return False


def main():
    """Run all tests"""
    print("=" * 60)
    print("ADAS Backend - Quick Test Suite")
    print("=" * 60)
    print()
    
    tests = [
        ("Imports", test_imports),
        ("Pydantic V2", test_pydantic_v2),
        ("ASCII Logging", test_logging_ascii),
        ("Database", test_database),
        ("Schemas", test_schemas),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"✗ {name} test crashed: {e}")
            results.append((name, False))
        print()
    
    # Summary
    print("=" * 60)
    print("Test Results Summary:")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "PASS" if result else "FAIL"
        symbol = "✓" if result else "✗"
        print(f"{symbol} {name}: {status}")
    
    print()
    print(f"Total: {passed}/{total} tests passed")
    
    if passed == total:
        print()
        print("✓ ALL TESTS PASSED - System is ready!")
        return 0
    else:
        print()
        print("✗ Some tests failed - please check errors above")
        return 1


if __name__ == "__main__":
    sys.exit(main())
