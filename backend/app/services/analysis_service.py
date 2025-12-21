"""
ANALYSIS SERVICE - Backend Orchestration Layer
==============================================
Manages video analysis jobs and calls AI perception pipeline.

This service:
- Receives requests from REST API
- Calls perception.pipeline.process_video()
- Manages job state
- Returns results to API

NO AI LOGIC HERE - Only orchestration!

Author: Senior ADAS Engineer
Date: 2025-12-21
"""

import os
import uuid
import json
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

# Import AI pipeline (SINGLE ENTRY POINT)
import sys
sys.path.append(str(Path(__file__).parent.parent.parent))
from perception.pipeline.video_pipeline_v11 import process_video

logger = logging.getLogger(__name__)


class AnalysisService:
    """
    Service layer for video analysis orchestration.
    Manages jobs and calls AI pipeline.
    """
    
    def __init__(
        self,
        storage_root: str = None,
        max_workers: int = 2
    ):
        """
        Initialize analysis service.
        
        Args:
            storage_root: Root directory for storage
            max_workers: Max concurrent processing jobs
        """
        # Storage paths
        if storage_root is None:
            storage_root = Path(__file__).parent.parent / "storage"
        
        self.storage_root = Path(storage_root)
        self.raw_dir = self.storage_root / "raw"
        self.result_dir = self.storage_root / "result"
        
        # Create directories
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.result_dir.mkdir(parents=True, exist_ok=True)
        
        # Job state (in-memory for now, could be Redis/DB)
        self.jobs = {}
        
        # Thread pool for background processing
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        
        logger.info(f"AnalysisService initialized")
        logger.info(f"Storage root: {self.storage_root}")
    
    def create_job(
        self, 
        filename: str,
        video_type: str = "dashcam"
    ) -> str:
        """
        Create a new analysis job.
        
        Args:
            filename: Original video filename
            video_type: "dashcam" or "in_cabin"
            
        Returns:
            Job ID
        """
        job_id = str(uuid.uuid4())
        
        # Store job metadata
        self.jobs[job_id] = {
            "job_id": job_id,
            "filename": filename,
            "video_type": video_type,
            "status": "created",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "input_path": None,
            "output_path": None,
            "events": [],
            "stats": {},
            "error": None
        }
        
        logger.info(f"Created job {job_id} for {filename}")
        return job_id
    
    def save_uploaded_video(
        self, 
        job_id: str,
        file_data: bytes
    ) -> str:
        """
        Save uploaded video file.
        
        Args:
            job_id: Job ID
            file_data: Video file bytes
            
        Returns:
            Path to saved file
        """
        if job_id not in self.jobs:
            raise ValueError(f"Job {job_id} not found")
        
        # Generate filename
        filename = self.jobs[job_id]['filename']
        safe_filename = f"{job_id}_{filename}"
        input_path = self.raw_dir / safe_filename
        
        # Save file
        with open(input_path, 'wb') as f:
            f.write(file_data)
        
        # Update job
        self.jobs[job_id]['input_path'] = str(input_path)
        self.jobs[job_id]['status'] = 'uploaded'
        self.jobs[job_id]['updated_at'] = datetime.now().isoformat()
        
        logger.info(f"Saved video for job {job_id} to {input_path}")
        return str(input_path)
    
    def _process_video_task(
        self, 
        job_id: str,
        device: str = "cpu"
    ):
        """
        Background task to process video.
        Calls AI pipeline.
        
        Args:
            job_id: Job ID
            device: "cuda" or "cpu"
        """
        try:
            job = self.jobs[job_id]
            
            # Update status
            job['status'] = 'processing'
            job['updated_at'] = datetime.now().isoformat()
            
            logger.info(f"Starting processing for job {job_id}")
            
            # Prepare paths
            input_path = job['input_path']
            output_filename = f"{job_id}_result.mp4"
            output_path = str(self.result_dir / output_filename)
            
            # Call AI pipeline (SINGLE ENTRY POINT)
            result = process_video(
                input_path=input_path,
                output_path=output_path,
                video_type=job['video_type'],
                device=device
            )
            
            if result['success']:
                # Update job with results
                job['status'] = 'completed'
                job['output_path'] = result['output_path']
                job['events'] = result['events']
                job['stats'] = result['stats']
                job['updated_at'] = datetime.now().isoformat()
                
                logger.info(f"Job {job_id} completed successfully")
                logger.info(f"Detected {len(result['events'])} events")
            else:
                # Processing failed
                job['status'] = 'failed'
                job['error'] = result.get('error', 'Unknown error')
                job['updated_at'] = datetime.now().isoformat()
                
                logger.error(f"Job {job_id} failed: {job['error']}")
        
        except Exception as e:
            logger.error(f"Job {job_id} processing error: {e}", exc_info=True)
            
            # Update job
            self.jobs[job_id]['status'] = 'failed'
            self.jobs[job_id]['error'] = str(e)
            self.jobs[job_id]['updated_at'] = datetime.now().isoformat()
    
    def start_processing(
        self, 
        job_id: str,
        device: str = "cpu"
    ):
        """
        Start video processing in background.
        
        Args:
            job_id: Job ID
            device: "cuda" or "cpu"
        """
        if job_id not in self.jobs:
            raise ValueError(f"Job {job_id} not found")
        
        # Submit to thread pool
        future = self.executor.submit(self._process_video_task, job_id, device)
        
        logger.info(f"Submitted job {job_id} for processing")
    
    def get_job_status(self, job_id: str) -> Optional[Dict]:
        """
        Get job status and results.
        
        Args:
            job_id: Job ID
            
        Returns:
            Job data dict or None if not found
        """
        return self.jobs.get(job_id)
    
    def get_result_url(self, job_id: str, base_url: str = "") -> Optional[str]:
        """
        Get URL to download result video.
        
        Args:
            job_id: Job ID
            base_url: Base URL for API
            
        Returns:
            Download URL or None
        """
        job = self.jobs.get(job_id)
        
        if not job or job['status'] != 'completed':
            return None
        
        # Generate URL
        output_filename = Path(job['output_path']).name
        url = f"{base_url}/api/video/download/{job_id}/{output_filename}"
        
        return url
    
    def cleanup_job(self, job_id: str):
        """
        Clean up job files.
        
        Args:
            job_id: Job ID
        """
        if job_id not in self.jobs:
            return
        
        job = self.jobs[job_id]
        
        # Delete input file
        if job['input_path'] and os.path.exists(job['input_path']):
            os.remove(job['input_path'])
            logger.info(f"Deleted input file for job {job_id}")
        
        # Delete output file
        if job['output_path'] and os.path.exists(job['output_path']):
            os.remove(job['output_path'])
            logger.info(f"Deleted output file for job {job_id}")
        
        # Remove from jobs
        del self.jobs[job_id]
        logger.info(f"Cleaned up job {job_id}")


# Global service instance
_service_instance = None


def get_analysis_service() -> AnalysisService:
    """
    Get singleton analysis service instance.
    
    Returns:
        AnalysisService instance
    """
    global _service_instance
    
    if _service_instance is None:
        _service_instance = AnalysisService()
    
    return _service_instance


if __name__ == "__main__":
    # Test module
    logging.basicConfig(level=logging.INFO)
    
    service = get_analysis_service()
    print(f"Analysis Service initialized")
    print(f"Storage root: {service.storage_root}")
