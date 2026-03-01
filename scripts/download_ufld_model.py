#!/usr/bin/env python3
"""
Download and prepare UFLD lane detection model weights.

This script downloads the official UFLD v2 TuSimple model and converts it
to a format compatible with our custom UFLDNet architecture.

Usage:
    python scripts/download_ufld_model.py

The script will:
1. Download official UFLD v2 TuSimple weights
2. Convert/remap keys to match our custom ResNet-18 backbone
3. Save to backend/models/ufld_tusimple.pth
"""

import os
import sys
import torch
import torch.nn as nn
import urllib.request
import hashlib
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Official model URLs from UFLD v2 repo (GitHub releases)
UFLD_MODELS = {
    'tusimple_res18': {
        'url': 'https://github.com/cfzd/Ultra-Fast-Lane-Detection-v2/releases/download/v0.1/tusimple_res18.pth',
        'md5': None,  # Will verify download success
        'output': 'backend/models/ufld_tusimple.pth',
    },
    # Alternative: ONNX version (more reliable, no key mapping needed)
    'tusimple_res18_onnx': {
        'url': 'https://huggingface.co/spaces/cfzd/UFLD-v2/resolve/main/tusimple_res18.onnx',
        'output': 'backend/models/ufld_tusimple.onnx',
    },
}


def download_file(url: str, dest: Path, chunk_size: int = 8192) -> bool:
    """Download file with progress."""
    print(f"Downloading: {url}")
    print(f"Destination: {dest}")
    
    dest.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            total = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(dest, 'wb') as f:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        pct = downloaded * 100 // total
                        print(f"\r  Progress: {pct}% ({downloaded}/{total} bytes)", end='')
            
            print()  # Newline after progress
            return True
            
    except Exception as e:
        print(f"Download failed: {e}")
        return False


def convert_official_to_custom(state_dict: dict) -> dict:
    """
    Convert official UFLD v2 state dict to match our custom UFLDNet architecture.
    
    Official model uses standard ResNet-18 backbone with different layer naming.
    Our model uses UFLDBackbone with slightly different structure.
    
    Key mapping:
        Official ResNet-18:          Our UFLDBackbone:
        - model.conv1               -> backbone.stem.0
        - model.bn1                 -> backbone.stem.1
        - model.layer1.0.conv1      -> backbone.layer1.0.conv1
        - ...
    """
    new_state = {}
    
    # Mapping rules for backbone
    mapping = {
        'model.conv1': 'backbone.stem.0',
        'model.bn1': 'backbone.stem.1',
    }
    
    # Layer mappings
    for layer_idx in range(1, 5):
        for block_idx in range(2):
            old_prefix = f'model.layer{layer_idx}.{block_idx}'
            new_prefix = f'backbone.layer{layer_idx}.{block_idx}'
            
            for conv in ['conv1', 'conv2']:
                mapping[f'{old_prefix}.{conv}'] = f'{new_prefix}.{conv}'
            for bn in ['bn1', 'bn2']:
                mapping[f'{old_prefix}.{bn}'] = f'{new_prefix}.{bn}'
            
            # Downsample
            mapping[f'{old_prefix}.downsample.0'] = f'{new_prefix}.downsample.0'
            mapping[f'{old_prefix}.downsample.1'] = f'{new_prefix}.downsample.1'
    
    # Head mapping (if exists)
    head_mapping = {
        'model.cls': 'head.cls',
        'model.pool': 'head.pool',
        'cls': 'head.cls',
        'pool': 'head.pool',
    }
    mapping.update(head_mapping)
    
    converted = 0
    skipped = 0
    
    for old_key, value in state_dict.items():
        new_key = None
        
        # Direct mapping
        for old_prefix, new_prefix in mapping.items():
            if old_key.startswith(old_prefix):
                new_key = old_key.replace(old_prefix, new_prefix, 1)
                break
        
        if new_key:
            new_state[new_key] = value
            converted += 1
        else:
            # Try keeping as-is if it starts with 'backbone' or 'head'
            if old_key.startswith('backbone.') or old_key.startswith('head.'):
                new_state[old_key] = value
                converted += 1
            else:
                print(f"  Skipping: {old_key}")
                skipped += 1
    
    print(f"  Converted: {converted} parameters, Skipped: {skipped}")
    return new_state


def create_random_weights():
    """Create random weights for our custom UFLDNet (fallback)."""
    from backend.perception.lane.lane_detector_ufld import UFLDNet
    
    print("Creating random weights for UFLDNet...")
    model = UFLDNet(
        num_lanes=4,
        num_rows=72,
        num_cols=200,
        input_h=320,
        input_w=800,
    )
    
    # Initialize with kaiming normal for conv layers
    for m in model.modules():
        if isinstance(m, nn.Conv2d):
            nn.init.kaiming_normal_(m.weight, mode='fan_out', nonlinearity='relu')
        elif isinstance(m, nn.BatchNorm2d):
            nn.init.constant_(m.weight, 1)
            nn.init.constant_(m.bias, 0)
        elif isinstance(m, nn.Linear):
            nn.init.normal_(m.weight, 0, 0.01)
            nn.init.constant_(m.bias, 0)
    
    return model.state_dict()


def main():
    print("=" * 60)
    print("UFLD Lane Detection Model Setup")
    print("=" * 60)
    
    # Prefer ONNX format (most compatible, no key mapping needed)
    output_path_onnx = Path('backend/models/ufld_tusimple.onnx')
    output_path_pth = Path('backend/models/ufld_tusimple.pth')
    
    # Check if already exists
    if output_path_onnx.exists():
        print(f"\n✅ ONNX model already exists: {output_path_onnx}")
        print("   Delete file to re-download.")
        return
    
    if output_path_pth.exists():
        print(f"\n✅ PyTorch model already exists: {output_path_pth}")
        print("   Delete file to re-download.")
        return
    
    # First try ONNX (recommended - more reliable)
    print("\n[1/2] Downloading official UFLD v2 TuSimple ONNX model...")
    onnx_info = UFLD_MODELS['tusimple_res18_onnx']
    
    if download_file(onnx_info['url'], output_path_onnx):
        print(f"\n✅ ONNX model saved successfully!")
        print(f"   Path: {output_path_onnx}")
        print(f"   Size: {output_path_onnx.stat().st_size / 1024 / 1024:.1f} MB")
    else:
        # Fallback to PyTorch model
        print("\n⚠️  ONNX download failed, trying PyTorch model...")
        
        model_info = UFLD_MODELS['tusimple_res18']
        temp_path = Path('/tmp/ufld_official.pth')
        
        if download_file(model_info['url'], temp_path):
            print("\n[2/2] Converting to custom architecture format...")
            
            try:
                official_state = torch.load(temp_path, map_location='cpu', weights_only=False)
                
                # Extract state dict from wrapper
                if isinstance(official_state, dict):
                    if 'model' in official_state:
                        official_state = official_state['model']
                    elif 'state_dict' in official_state:
                        official_state = official_state['state_dict']
                
                print(f"  Official model has {len(official_state)} parameters")
                
                # Convert keys
                converted_state = convert_official_to_custom(official_state)
                
                # Save converted model
                output_path_pth.parent.mkdir(parents=True, exist_ok=True)
                torch.save(converted_state, output_path_pth)
                
                print(f"\n✅ Model saved successfully!")
                print(f"   Path: {output_path_pth}")
                print(f"   Size: {output_path_pth.stat().st_size / 1024 / 1024:.1f} MB")
                
                # Cleanup
                temp_path.unlink(missing_ok=True)
                
            except Exception as e:
                print(f"\n⚠️  Conversion failed: {e}")
                print("   Creating random weights as fallback...")
                
                random_state = create_random_weights()
                output_path_pth.parent.mkdir(parents=True, exist_ok=True)
                torch.save(random_state, output_path_pth)
                
                print(f"\n✅ Random weights saved to {output_path_pth}")
                print("   Note: Model needs training for actual lane detection!")
        else:
            print("\n⚠️  Both downloads failed, creating random weights...")
            
            random_state = create_random_weights()
            output_path_pth.parent.mkdir(parents=True, exist_ok=True)
            torch.save(random_state, output_path_pth)
            
            print(f"\n✅ Random weights saved to {output_path_pth}")
            print("   Note: Model needs training for actual lane detection!")
    
    print("\n" + "=" * 60)
    print("Setup complete! Restart GPU worker to use the new model.")
    print("=" * 60)


if __name__ == '__main__':
    main()
