"""Video pipeline module for ADAS system."""

from .video_pipeline_v11 import ADASPipeline, process_video

# Backward compatibility alias
VideoPipelineV11 = ADASPipeline

# Export for external use
__all__ = ["ADASPipeline", "VideoPipelineV11", "process_video"]

