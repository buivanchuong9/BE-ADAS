#!/usr/bin/env python3
"""
Test script cho ADAS Training APIs
"""
import requests
import time
import json

BASE_URL = "http://localhost:8000"


def test_upload_video():
    """Test upload video API"""
    print("\n🔥 TEST 1: Upload Video + Auto-Label")
    print("=" * 60)
    
    # Giả lập upload (cần file video thật)
    # with open('test_video.mp4', 'rb') as f:
    #     response = requests.post(
    #         f'{BASE_URL}/api/upload/video',
    #         files={'file': f},
    #         data={
    #             'description': 'Test video for auto-labeling',
    #             'auto_label': True
    #         }
    #     )
    
    print("⚠️  Cần file video để test. Skip...")
    print("API Endpoint: POST /api/upload/video")
    print("Expected response: {video_id, filename, status: 'processing'}")


def test_dataset_stats():
    """Test dataset statistics"""
    print("\n📊 TEST 2: Dataset Statistics")
    print("=" * 60)
    
    try:
        response = requests.get(f'{BASE_URL}/api/dataset/stats')
        if response.status_code == 200:
            data = response.json()
            print("✅ Dataset Stats:")
            print(json.dumps(data, indent=2))
        else:
            print(f"❌ Error: {response.status_code}")
    except Exception as e:
        print(f"❌ Connection error: {e}")


def test_training_start():
    """Test training API"""
    print("\n🚀 TEST 3: Start Training")
    print("=" * 60)
    
    payload = {
        "model_name": "test_model_v1",
        "base_model": "yolo11n.pt",
        "epochs": 2,  # Chỉ 2 epochs để test nhanh
        "batch_size": 8,
        "img_size": 640
    }
    
    print("Request:")
    print(json.dumps(payload, indent=2))
    
    try:
        response = requests.post(
            f'{BASE_URL}/api/training/start',
            json=payload
        )
        
        if response.status_code == 200:
            data = response.json()
            print("\n✅ Training started:")
            print(json.dumps(data, indent=2))
            return data.get('training_id')
        else:
            print(f"❌ Error: {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"❌ Connection error: {e}")
    
    return None


def test_training_status(training_id):
    """Test training status"""
    if not training_id:
        print("\n⚠️  No training_id to check")
        return
    
    print(f"\n⏳ TEST 4: Training Status ({training_id})")
    print("=" * 60)
    
    try:
        response = requests.get(f'{BASE_URL}/api/training/status/{training_id}')
        if response.status_code == 200:
            data = response.json()
            print("✅ Training Status:")
            print(json.dumps(data, indent=2))
        else:
            print(f"❌ Error: {response.status_code}")
    except Exception as e:
        print(f"❌ Connection error: {e}")


def test_inference_image():
    """Test inference on image"""
    print("\n🎯 TEST 5: Inference Image")
    print("=" * 60)
    
    print("⚠️  Cần file ảnh để test. Skip...")
    print("API Endpoint: POST /api/inference/image")
    print("Expected: {vehicles: [...], lanes: {...}, warnings: [...]}")


def test_api_health():
    """Test if API is running"""
    print("\n❤️  TEST 0: API Health Check")
    print("=" * 60)
    
    try:
        response = requests.get(f'{BASE_URL}/docs')
        if response.status_code == 200:
            print("✅ API is running!")
            print(f"📝 API Docs: {BASE_URL}/docs")
        else:
            print(f"❌ API returned: {response.status_code}")
    except Exception as e:
        print(f"❌ Cannot connect to API: {e}")
        print(f"💡 Make sure API is running: python3 main.py")
        return False
    
    return True


def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("🧪 ADAS TRAINING API TESTS")
    print("=" * 60)
    
    # Check API health
    if not test_api_health():
        return
    
    # Run tests
    test_dataset_stats()
    test_upload_video()
    training_id = test_training_start()
    
    if training_id:
        time.sleep(2)  # Wait a bit
        test_training_status(training_id)
    
    test_inference_image()
    
    print("\n" + "=" * 60)
    print("✅ ALL TESTS COMPLETED")
    print("=" * 60)
    print("\n📚 Full API documentation: http://localhost:8000/docs")


if __name__ == "__main__":
    main()
