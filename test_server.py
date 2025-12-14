#!/usr/bin/env python3
"""Quick server test - Verify imports and basic functionality"""
import sys

print("Testing ADAS Backend Server...")
print("=" * 60)

# Test 1: Python version
print(f"Python version: {sys.version}")
assert sys.version_info >= (3, 10), "Python 3.10+ required"
print("✓ Python version OK")

# Test 2: Core imports
try:
    import fastapi
    print(f"✓ FastAPI {fastapi.__version__}")
except ImportError as e:
    print(f"✗ FastAPI import failed: {e}")
    sys.exit(1)

try:
    import uvicorn
    print("✓ Uvicorn OK")
except ImportError as e:
    print(f"✗ Uvicorn import failed: {e}")
    sys.exit(1)

try:
    import cv2
    print(f"✓ OpenCV {cv2.__version__}")
except ImportError as e:
    print(f"✗ OpenCV import failed: {e}")
    sys.exit(1)

try:
    import numpy as np
    print(f"✓ NumPy {np.__version__}")
except ImportError as e:
    print(f"✗ NumPy import failed: {e}")
    sys.exit(1)

try:
    import sqlalchemy
    print(f"✓ SQLAlchemy {sqlalchemy.__version__}")
except ImportError as e:
    print(f"✗ SQLAlchemy import failed: {e}")
    sys.exit(1)

try:
    import pydantic
    print(f"✓ Pydantic {pydantic.__version__}")
except ImportError as e:
    print(f"✗ Pydantic import failed: {e}")
    sys.exit(1)

# Test 3: Database
try:
    from database import engine, Base
    Base.metadata.create_all(bind=engine)
    print("✓ Database initialization OK")
except Exception as e:
    print(f"✗ Database error: {e}")
    sys.exit(1)

# Test 4: Main app import
try:
    from main import app
    print("✓ FastAPI app import OK")
except Exception as e:
    print(f"✗ Main app import failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("=" * 60)
print("All tests passed! Server should start correctly.")
print("=" * 60)
