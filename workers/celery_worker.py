#!/usr/bin/env python3
"""
Celery Worker - Video Processing
==================================
Standalone Celery worker that processes video tasks from Redis queue.

Usage:
    # Start single worker
    python celery_worker.py
    
    # Start with custom concurrency
    python celery_worker.py --concurrency=4
    
    # Start with Celery Beat scheduler for periodic tasks
    python celery_worker.py --beat

Author: ADAS Team
Date: 2026-01-19
"""

import os
import sys
import logging
import argparse
from pathlib import Path

# Add backend directory to path
BACKEND_DIR = Path(__file__).parent / 'backend'
sys.path.insert(0, str(BACKEND_DIR.parent))

from app.core.celery_config import celery_app

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Start Celery worker."""
    
    parser = argparse.ArgumentParser(
        description='Celery worker for ADAS video processing'
    )
    parser.add_argument(
        '--concurrency',
        type=int,
        default=2,
        help='Number of concurrent worker processes (default: 2)'
    )
    parser.add_argument(
        '--beat',
        action='store_true',
        help='Also run Celery Beat scheduler for periodic tasks'
    )
    parser.add_argument(
        '--loglevel',
        default='info',
        help='Logging level (debug, info, warning, error, critical)'
    )
    parser.add_argument(
        '--queues',
        default='celery,video_processing,maintenance',
        help='Comma-separated list of queues to consume from'
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 80)
    logger.info("🚀 Celery Worker for ADAS Video Processing")
    logger.info("=" * 80)
    logger.info(f"Concurrency: {args.concurrency} workers")
    logger.info(f"Loglevel: {args.loglevel}")
    logger.info(f"Queues: {args.queues}")
    logger.info(f"Beat scheduler: {'enabled' if args.beat else 'disabled'}")
    logger.info("=" * 80)
    
    # Start worker
    argv = [
        'worker',
        f'--concurrency={args.concurrency}',
        f'--loglevel={args.loglevel}',
        f'--queues={args.queues}',
        '--prefetch-multiplier=1',  # Fetch one task at a time
        '--time-limit=3600',         # Hard timeout: 1 hour
        '--soft-time-limit=3500',    # Soft timeout: 58 minutes
        '--max-tasks-per-child=1000', # Restart worker after 1000 tasks
    ]
    
    # Add beat scheduler if requested
    if args.beat:
        argv.append('--beat')
        logger.info("✅ Celery Beat scheduler enabled")
    
    # Start the worker
    try:
        celery_app.start(argv)
    except KeyboardInterrupt:
        logger.info("👋 Celery worker shutdown requested by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Celery worker error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
