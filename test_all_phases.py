"""
COMPREHENSIVE SYSTEM TEST SUITE
================================
Test all Phase 3-10 implementations.

Run: python test_all_phases.py
"""

import sys
import logging
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def test_imports():
    """Test all critical imports."""
    logger.info("=" * 60)
    logger.info("TEST 1: Checking imports...")
    logger.info("=" * 60)
    
    errors = []
    
    # Phase 3-4 imports
    try:
        from backend.perception.object.object_tracker import ByteTracker, KalmanBoxTracker
        logger.info("✓ ByteTracker import OK")
    except Exception as e:
        errors.append(f"ByteTracker import failed: {e}")
    
    try:
        from backend.app.services.context_engine import ContextEngine
        logger.info("✓ ContextEngine import OK")
    except Exception as e:
        errors.append(f"ContextEngine import failed: {e}")
    
    # Phase 5
    try:
        from backend.app.services.risk_engine import RiskEngine, RiskAlert, AlertType, AlertSeverity
        logger.info("✓ RiskEngine import OK")
    except Exception as e:
        errors.append(f"RiskEngine import failed: {e}")
    
    # Phase 6
    try:
        from backend.app.api.websocket_alerts import ConnectionManager, manager
        logger.info("✓ WebSocket alerts import OK")
    except Exception as e:
        errors.append(f"WebSocket alerts import failed: {e}")
    
    try:
        from backend.app.services.tts_service import VietnameseTTS, get_tts_service
        logger.info("✓ Vietnamese TTS import OK")
    except Exception as e:
        errors.append(f"Vietnamese TTS import failed: {e}")
    
    # Phase 8
    try:
        from backend.app.core.auth import (
            create_access_token, decode_token, hash_password, 
            verify_password, UserRole, TokenData
        )
        logger.info("✓ JWT Auth import OK")
    except Exception as e:
        errors.append(f"JWT Auth import failed: {e}")
    
    try:
        from backend.app.core.errors import (
            ErrorCode, AdasException, create_error_response
        )
        logger.info("✓ Error handling import OK")
    except Exception as e:
        errors.append(f"Error handling import failed: {e}")
    
    # Phase 9
    try:
        from backend.app.core.device import DeviceDetector, get_device
        logger.info("✓ Device detection import OK")
    except Exception as e:
        errors.append(f"Device detection import failed: {e}")
    
    if errors:
        logger.error("\n❌ Import errors found:")
        for err in errors:
            logger.error(f"  - {err}")
        return False
    else:
        logger.info("\n✅ All imports successful!")
        return True


def test_byte_tracker():
    """Test ByteTrack implementation."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 2: ByteTrack object tracking...")
    logger.info("=" * 60)
    
    try:
        from backend.perception.object.object_tracker import ByteTracker
        import numpy as np
        
        tracker = ByteTracker(track_thresh=0.5, match_thresh=0.8)
        
        # Simulate detections
        detections1 = [
            {'bbox': [100, 100, 200, 200], 'score': 0.9, 'class_id': 2},
            {'bbox': [300, 150, 400, 250], 'score': 0.85, 'class_id': 2}
        ]
        
        tracks1 = tracker.update(detections1)
        assert len(tracks1) == 2, "Should have 2 tracks"
        assert all('id' in t for t in tracks1), "All tracks should have IDs"
        
        # Frame 2 - same objects moved
        detections2 = [
            {'bbox': [105, 105, 205, 205], 'score': 0.9, 'class_id': 2},
            {'bbox': [305, 155, 405, 255], 'score': 0.85, 'class_id': 2}
        ]
        
        tracks2 = tracker.update(detections2)
        assert len(tracks2) == 2, "Should maintain 2 tracks"
        
        # Check ID persistence
        ids1 = {t['id'] for t in tracks1}
        ids2 = {t['id'] for t in tracks2}
        assert ids1 == ids2, "Track IDs should persist across frames"
        
        logger.info("✓ ByteTrack creates persistent IDs")
        logger.info("✓ ByteTrack maintains tracks across frames")
        logger.info("✅ ByteTrack test PASSED")
        return True
        
    except Exception as e:
        logger.error(f"❌ ByteTrack test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_context_engine():
    """Test Context Engine."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 3: Context Engine temporal aggregation...")
    logger.info("=" * 60)
    
    try:
        from backend.app.services.context_engine import ContextEngine
        import numpy as np
        
        engine = ContextEngine(window_seconds=3.0, frame_rate=30)
        
        # Simulate 100 frames
        for i in range(100):
            # Lane detection
            engine.update_lane_context({
                'left_confidence': 0.8 + np.random.normal(0, 0.05),
                'right_confidence': 0.85 + np.random.normal(0, 0.05),
                'offset': np.random.normal(0, 0.1),
                'lane_departure': False
            })
            
            # Object tracking
            engine.update_object_context([
                {'class_name': 'car', 'distance': 20.0, 'ttc': 3.0, 'risk_level': 'CAUTION'}
            ])
            
            # Driver monitoring
            engine.update_driver_context({
                'face_detected': True,
                'smoothed_ear': 0.28,
                'smoothed_mar': 0.4,
                'is_sustained_drowsy': False,
                'head_pose': {'yaw': 5.0, 'pitch': -10.0}
            })
        
        state = engine.get_context_state()
        
        assert 'lane_stability_score' in state, "Should have lane stability"
        assert 'traffic_density_score' in state, "Should have traffic density"
        assert 'driver_alertness_score' in state, "Should have driver alertness"
        assert 0 <= state['lane_stability_score'] <= 1, "Score should be 0-1"
        
        logger.info(f"✓ Lane Stability: {state['lane_stability_score']:.2f}")
        logger.info(f"✓ Traffic Density: {state['traffic_density_score']:.2f}")
        logger.info(f"✓ Driver Alertness: {state['driver_alertness_score']:.2f}")
        logger.info("✅ Context Engine test PASSED")
        return True
        
    except Exception as e:
        logger.error(f"❌ Context Engine test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_risk_engine():
    """Test Risk Assessment Engine."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 4: Risk Engine alert generation...")
    logger.info("=" * 60)
    
    try:
        from backend.app.services.risk_engine import RiskEngine, AlertSeverity
        
        engine = RiskEngine(frame_rate=30, enable_deduplication=True)
        
        # Test Forward Collision Warning
        lane_output = {'offset': 0.3, 'direction': 'CENTER', 'left_confidence': 0.8, 'right_confidence': 0.85}
        
        tracked_objects = [
            {
                'class_name': 'car',
                'distance': 3.0,
                'ttc': 0.4,  # <= 0.5s triggers CRITICAL
                'is_approaching': True,
                'closing_speed': 7.5,
                'risk_level': 'CRITICAL'
            }
        ]
        
        driver_output = {
            'should_alert': False,
            'drowsy_confidence': 0.3,
            'drowsy_reason': 'ALERT',
            'smoothed_ear': 0.28,
            'smoothed_mar': 0.4
        }
        
        context_state = {
            'sustained_lane_departure': False,
            'lane_stability_score': 0.8,
            'driver_alertness_score': 0.9
        }
        
        alerts = engine.assess_all_risks(lane_output, tracked_objects, driver_output, context_state)
        
        assert len(alerts) > 0, "Should generate FCW alert for close vehicle"
        
        fcw_alert = alerts[0]
        assert fcw_alert.alert_type.value == 'FCW', "Should be Forward Collision Warning"
        assert fcw_alert.severity == AlertSeverity.CRITICAL, "Should be CRITICAL severity"
        assert fcw_alert.message_vi is not None, "Should have Vietnamese message"
        
        logger.info(f"✓ Alert Type: {fcw_alert.alert_type.value}")
        logger.info(f"✓ Severity: {fcw_alert.severity.value}")
        logger.info(f"✓ Message: {fcw_alert.message}")
        logger.info(f"✓ Vietnamese: {fcw_alert.message_vi}")
        logger.info(f"✓ Risk Score: {fcw_alert.risk_score:.2f}")
        logger.info("✅ Risk Engine test PASSED")
        return True
        
    except Exception as e:
        logger.error(f"❌ Risk Engine test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_jwt_auth():
    """Test JWT authentication."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 5: JWT Authentication & RBAC...")
    logger.info("=" * 60)
    
    try:
        from backend.app.core.auth import (
            hash_password, verify_password, create_access_token,
            decode_token, UserRole
        )
        
        # Test password hashing
        password = "test123"
        hashed = hash_password(password)
        assert verify_password(password, hashed), "Password verification should work"
        assert not verify_password("wrong", hashed), "Wrong password should fail"
        logger.info("✓ Password hashing works")
        
        # Test token creation
        token = create_access_token(
            user_id="user_001",
            username="admin",
            role=UserRole.ADMIN
        )
        assert isinstance(token, str), "Token should be string"
        assert len(token) > 50, "Token should be long enough"
        logger.info("✓ Token creation works")
        
        # Test token decoding
        token_data = decode_token(token)
        assert token_data.user_id == "user_001", "User ID should match"
        assert token_data.username == "admin", "Username should match"
        assert token_data.role == UserRole.ADMIN, "Role should match"
        logger.info("✓ Token decoding works")
        logger.info("✓ RBAC roles defined")
        logger.info("✅ JWT Auth test PASSED")
        return True
        
    except Exception as e:
        logger.error(f"❌ JWT Auth test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_error_handling():
    """Test error handling system."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 6: Structured error handling...")
    logger.info("=" * 60)
    
    try:
        from backend.app.core.errors import (
            ErrorCode, AdasException, create_error_response, ErrorMessage
        )
        
        # Test error response creation
        error = create_error_response(
            code=ErrorCode.PROC_VIDEO_PROCESSING_FAILED,
            details={'frame': 123},
            request_id='req_001'
        )
        
        assert error['success'] == False, "Error should have success=False"
        assert 'error' in error, "Should have error object"
        assert error['error']['code'] == ErrorCode.PROC_VIDEO_PROCESSING_FAILED.value
        assert 'message_vi' in error['error'], "Should have Vietnamese message"
        logger.info("✓ Error response creation works")
        
        # Test exception
        try:
            raise AdasException(
                code=ErrorCode.AUTH_INVALID_CREDENTIALS,
                status_code=401
            )
        except AdasException as e:
            assert e.code == ErrorCode.AUTH_INVALID_CREDENTIALS
            assert e.status_code == 401
            assert e.message_vi is not None
            logger.info("✓ AdasException works")
        
        # Test bilingual messages
        message_en = ErrorMessage.get(ErrorCode.AUTH_INVALID_CREDENTIALS, 'en')
        message_vi = ErrorMessage.get(ErrorCode.AUTH_INVALID_CREDENTIALS, 'vi')
        assert message_en != message_vi, "Should have different languages"
        logger.info(f"✓ EN: {message_en}")
        logger.info(f"✓ VI: {message_vi}")
        logger.info("✅ Error handling test PASSED")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error handling test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_device_detection():
    """Test device detection."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 7: Device detection...")
    logger.info("=" * 60)
    
    try:
        from backend.app.core.device import DeviceDetector, get_device
        
        detector = DeviceDetector()
        
        assert detector.device_info is not None, "Should detect device"
        assert detector.device_info.device_type in ['cuda', 'directml', 'cpu'], "Should be valid device type"
        
        device_str = detector.get_device_string()
        assert isinstance(device_str, str), "Device string should be string"
        
        info = detector.get_device_info()
        assert 'device_type' in info, "Should have device info"
        
        logger.info(f"✓ Device Type: {detector.device_info.device_type}")
        logger.info(f"✓ Device Name: {detector.device_info.device_name}")
        logger.info(f"✓ Device String: {device_str}")
        logger.info(f"✓ GPU Available: {detector.is_gpu_available()}")
        logger.info(f"✓ Optimal Batch Size: {detector.get_optimal_batch_size()}")
        logger.info("✅ Device detection test PASSED")
        return True
        
    except Exception as e:
        logger.error(f"❌ Device detection test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    logger.info("\n")
    logger.info("╔" + "=" * 58 + "╗")
    logger.info("║" + " " * 10 + "ADAS BACKEND TEST SUITE (Phase 3-10)" + " " * 11 + "║")
    logger.info("╚" + "=" * 58 + "╝")
    logger.info("\n")
    
    results = []
    
    # Run tests
    results.append(("Imports", test_imports()))
    results.append(("ByteTrack", test_byte_tracker()))
    results.append(("Context Engine", test_context_engine()))
    results.append(("Risk Engine", test_risk_engine()))
    results.append(("JWT Auth", test_jwt_auth()))
    results.append(("Error Handling", test_error_handling()))
    results.append(("Device Detection", test_device_detection()))
    
    # Summary
    logger.info("\n")
    logger.info("=" * 60)
    logger.info("TEST SUMMARY")
    logger.info("=" * 60)
    
    passed = 0
    failed = 0
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        logger.info(f"{name:20s} {status}")
        if result:
            passed += 1
        else:
            failed += 1
    
    logger.info("=" * 60)
    logger.info(f"Total: {len(results)} tests")
    logger.info(f"Passed: {passed} ({passed/len(results)*100:.0f}%)")
    logger.info(f"Failed: {failed}")
    logger.info("=" * 60)
    
    if failed == 0:
        logger.info("\n🎉 ALL TESTS PASSED! System ready for deployment.")
        return 0
    else:
        logger.error(f"\n⚠️ {failed} tests failed. Please fix before deployment.")
        return 1


if __name__ == "__main__":
    exit(main())
