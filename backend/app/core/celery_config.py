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

# Redis configuration - AN TOÀN cho SHARED SERVER
# Option A: TCP connection (mặc định) - an toàn cho server dùng chung
# Option B: Unix socket - nhanh hơn nhưng cần config Redis riêng
import os

# Environment variables để control (set trên server)
USE_UNIX_SOCKET = os.getenv('REDIS_USE_UNIX_SOCKET', 'false').lower() == 'true'
REDIS_UNIX_SOCKET = os.getenv('REDIS_UNIX_SOCKET', '/var/run/redis/redis-server.sock')
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', '6379'))

if USE_UNIX_SOCKET and os.path.exists(REDIS_UNIX_SOCKET):
    # Production với Redis riêng: Unix socket (nhanh + tránh TCP Error 22)
    REDIS_BROKER_URL = f'redis+socket://{REDIS_UNIX_SOCKET}?virtual_host=0'
    REDIS_BACKEND_URL = f'redis+socket://{REDIS_UNIX_SOCKET}?virtual_host=1'
    logger.info(f"🔌 Redis Unix socket: {REDIS_UNIX_SOCKET}")
else:
    # Shared server: TCP connection (an toàn, không ảnh hưởng người khác)
    REDIS_BROKER_URL = f'redis://{REDIS_HOST}:{REDIS_PORT}/0'
    REDIS_BACKEND_URL = f'redis://{REDIS_HOST}:{REDIS_PORT}/1'
    logger.info(f"🔌 Redis TCP (shared-safe): {REDIS_HOST}:{REDIS_PORT}")

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
    task_time_limit=1800,              # 30 minutes hard timeout (for long videos)
    task_soft_time_limit=1740,         # 29 minutes soft timeout
    worker_concurrency=1,              # Strict single worker
    
    # Worker settings - AGGRESSIVE POLLING for INSTANT response
    worker_prefetch_multiplier=1,      # Fetch one task at a time (don't prefetch)
    worker_max_tasks_per_child=50,     # Restart worker often to clear GPU memory leaks
    broker_pool_limit=None,            # No limit on broker connections
    broker_heartbeat=10,               # Heartbeat every 10 seconds (faster detection)
    broker_connection_timeout=4,       # Quick connection timeout
    event_queue_expires=60,            # Event queue expires quickly
    
    # CRITICAL: Poll broker VERY frequently for instant task pickup
    worker_send_task_events=True,     # Send task events immediately
    task_send_sent_event=True,        # Send event when task is sent
    
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
    
    # Broker settings - AGGRESSIVE polling
    broker_connection_retry_on_startup=True,
    broker_connection_retry=True,
    broker_connection_max_retries=10,
    broker_transport_options={
        'visibility_timeout': 3600,    # 1 hour visibility
        'fanout_prefix': True,
        'fanout_patterns': True,
        # KHÔNG dùng socket_keepalive → tránh Error 22 + an toàn cho shared server
    },
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
