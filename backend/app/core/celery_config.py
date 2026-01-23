"""
Celery Configuration Module
============================
Configures Celery for async task processing with Redis broker.

Usage:
    from app.core.celery_config import celery_app
    
Author: ADAS Team
Date: 2026-01-19
"""

from celery import Celery
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

# Redis configuration
REDIS_BROKER_URL = getattr(settings, 'REDIS_URL', 'redis://localhost:6379/0')
REDIS_BACKEND_URL = getattr(settings, 'REDIS_URL', 'redis://localhost:6379/1')

# Initialize Celery app
celery_app = Celery(
    'adas',
    broker=REDIS_BROKER_URL,
    backend=REDIS_BACKEND_URL,
    include=['app.tasks']
)

# Celery configuration
celery_app.conf.update(
    # Task settings
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    
    # Task execution settings
    task_track_started=True,           # Track when task starts
    task_time_limit=600,               # 10 minutes hard timeout (Fail fast)
    task_soft_time_limit=540,          # 9 minutes soft timeout
    worker_concurrency=1,              # Strict single worker
    
    # Worker settings
    worker_prefetch_multiplier=1,      # Fetch one task at a time (don't prefetch)
    worker_max_tasks_per_child=50,     # Restart worker often to clear GPU memory leaks
    
    # Retry settings
    task_acks_late=True,               # Acknowledge task after completion
    task_reject_on_worker_lost=True,   # Reject task if worker dies
    
    # Result backend settings
    result_expires=3600,               # Expire results after 1 hour
    result_backend_transport_options={
        'retry_on_timeout': True,
        'socket_connect_timeout': 5,
        'socket_timeout': 5,
    },
    
    # Broker settings
    broker_connection_retry_on_startup=True,
    broker_connection_retry=True,
    broker_connection_max_retries=10,
)

# Task routes for prioritization (optional)
# Task routes for prioritization (optional)
# celery_app.conf.task_routes = {
#     'app.tasks.process_video_task': {'queue': 'video_processing'},
#     'app.tasks.cleanup_old_files': {'queue': 'maintenance'},
# }

# Set up task logging
@celery_app.task(bind=True)
def debug_task(self):
    """Debug task to test Celery setup."""
    logger.info(f'Request: {self.request!r}')
    return {'status': 'celery is working'}


logger.info(f"✅ Celery app initialized")
logger.info(f"   Broker: {REDIS_BROKER_URL}")
logger.info(f"   Backend: {REDIS_BACKEND_URL}")
