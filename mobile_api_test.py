import requests
import time
import os
import json

BASE_URL = "http://localhost:8000"

def test_mobile_flow():
    print(f"🚀 Testing Mobile API Flow at {BASE_URL}")
    
    # 1. Health check
    try:
        resp = requests.get(f"{BASE_URL}/api/mobile/health")
        print(f"✅ Health: {resp.status_code} - {resp.json()}")
    except Exception as e:
        print(f"❌ Server not running? {e}")
        return

    # 2. Upload Video
    # Create dummy video file
    with open("test_video.mp4", "wb") as f:
        f.write(b"dummy video content" * 1024 * 5) # 5MB dummy file
    
    print("\n📤 Uploading video...")
    files = {'file': ('test_video.mp4', open('test_video.mp4', 'rb'), 'video/mp4')}
    data = {'video_type': 'dashcam', 'device': 'cpu'}
    
    start = time.time()
    try:
        resp = requests.post(f"{BASE_URL}/api/mobile/video/upload", files=files, data=data)
        elapsed = time.time() - start
        
        if resp.status_code == 202:
            result = resp.json()
            job_id = result['job_id']
            print(f"✅ Upload Success ({elapsed:.2f}s)!")
            print(f"   Job ID: {job_id}")
            print(f"   Status: {result['status']}")
            print(f"   ETA: {result['estimated_time_seconds']}s")
            
            # 3. Poll Status
            print(f"\n🔄 Polling status for Job {job_id}...")
            for i in range(5):
                try:
                    resp = requests.get(f"{BASE_URL}/api/mobile/video/status/{job_id}")
                    if resp.status_code == 200:
                        status_data = resp.json()
                        print(f"   [{i+1}] Status: {status_data.get('status')} | Progress: {status_data.get('progress_percent')}%")
                        
                        if status_data.get('status') == 'completed':
                            print("   🎉 Processing Complete!")
                            break
                        elif status_data.get('status') == 'failed':
                            print(f"   ❌ Processing Failed: {status_data.get('error')}")
                            break
                    else:
                        print(f"   ⚠️ Poll error: {resp.status_code} - {resp.text}")
                        
                    time.sleep(2)
                except Exception as e:
                    print(f"   ⚠️ Poll error: {e}")
        else:
            print(f"❌ Upload Failed: {resp.status_code} - {resp.text}")
            
    except Exception as e:
        print(f"❌ Upload Exception: {e}")
    finally:
        # Cleanup
        if os.path.exists("test_video.mp4"):
            os.remove("test_video.mp4")

if __name__ == "__main__":
    test_mobile_flow()
