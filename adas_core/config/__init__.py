"""
Configuration Loader - YAML-based configuration management
Supports environment-specific configs (dev/test/prod)
"""

import yaml
from pathlib import Path
from typing import Dict, Any, Optional
import os
from dataclasses import dataclass, field


@dataclass
class ADASConfig:
    """
    Structured ADAS configuration
    
    Automatically loaded from YAML files with validation
    Supports environment overrides
    """
    # System
    system_name: str = "ADAS Platform"
    system_version: str = "4.0.0"
    environment: str = "production"
    debug_mode: bool = False
    target_fps: int = 30
    max_latency_ms: int = 50
    
    # Sensors
    sensors: Dict[str, Any] = field(default_factory=dict)
    
    # Perception
    perception: Dict[str, Any] = field(default_factory=dict)
    
    # Planning
    planning: Dict[str, Any] = field(default_factory=dict)
    
    # Control
    control: Dict[str, Any] = field(default_factory=dict)
    
    # Safety
    safety: Dict[str, Any] = field(default_factory=dict)
    
    # Tracking
    tracking: Dict[str, Any] = field(default_factory=dict)
    
    # Paths
    paths: Dict[str, str] = field(default_factory=dict)
    
    # Database
    database: Dict[str, Any] = field(default_factory=dict)
    
    # API
    api: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def from_yaml(cls, config_path: str) -> 'ADASConfig':
        """
        Load configuration from YAML file
        
        Args:
            config_path: Path to YAML config file
            
        Returns:
            ADASConfig instance
        """
        config_file = Path(config_path)
        
        if not config_file.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")
        
        with open(config_file, 'r') as f:
            data = yaml.safe_load(f)
        
        return cls.from_dict(data)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ADASConfig':
        """Create config from dictionary"""
        system = data.get('system', {})
        
        return cls(
            system_name=system.get('name', 'ADAS Platform'),
            system_version=system.get('version', '4.0.0'),
            environment=system.get('environment', 'production'),
            debug_mode=system.get('debug_mode', False),
            target_fps=system.get('target_fps', 30),
            max_latency_ms=system.get('max_latency_ms', 50),
            
            sensors=data.get('sensors', {}),
            perception=data.get('perception', {}),
            planning=data.get('planning', {}),
            control=data.get('control', {}),
            safety=data.get('safety', {}),
            tracking=data.get('tracking', {}),
            paths=data.get('paths', {}),
            database=data.get('database', {}),
            api=data.get('api', {}),
        )
    
    def get_sensor_config(self, sensor_name: str) -> Optional[Dict[str, Any]]:
        """Get configuration for specific sensor"""
        return self.sensors.get(sensor_name)
    
    def get_perception_config(self, module_name: str) -> Optional[Dict[str, Any]]:
        """Get configuration for perception module"""
        return self.perception.get(module_name)
    
    def is_module_enabled(self, module_name: str) -> bool:
        """Check if a module is enabled"""
        # Check in all config sections
        for section in [self.sensors, self.perception, self.planning, self.control]:
            if module_name in section:
                return section[module_name].get('enabled', False)
        return False


class ConfigManager:
    """
    Configuration manager with environment support
    
    Loads base config + environment-specific overrides
    Supports hot-reload for development
    """
    
    def __init__(self, config_dir: str = "adas_core/config"):
        """
        Initialize config manager
        
        Args:
            config_dir: Directory containing config files
        """
        self.config_dir = Path(config_dir)
        self.base_config_path = self.config_dir / "adas_config.yaml"
        
        # Load configuration
        self.config = self._load_config()
    
    def _load_config(self) -> ADASConfig:
        """
        Load configuration with environment overrides
        
        Loading order:
        1. Base config (adas_config.yaml)
        2. Environment config (adas_config_{env}.yaml) if exists
        3. Environment variables override
        """
        # Load base config
        if not self.base_config_path.exists():
            raise FileNotFoundError(f"Base config not found: {self.base_config_path}")
        
        config = ADASConfig.from_yaml(str(self.base_config_path))
        
        # Load environment-specific overrides
        env = os.getenv('ADAS_ENV', config.environment)
        env_config_path = self.config_dir / f"adas_config_{env}.yaml"
        
        if env_config_path.exists():
            env_config = ADASConfig.from_yaml(str(env_config_path))
            config = self._merge_configs(config, env_config)
        
        # Apply environment variable overrides
        config = self._apply_env_overrides(config)
        
        return config
    
    def _merge_configs(self, base: ADASConfig, override: ADASConfig) -> ADASConfig:
        """Merge override config into base config"""
        # Simple implementation: Override non-empty fields
        # In production, use deep merge
        for field_name in ['sensors', 'perception', 'planning', 'control', 'safety']:
            base_dict = getattr(base, field_name)
            override_dict = getattr(override, field_name)
            base_dict.update(override_dict)
        
        return base
    
    def _apply_env_overrides(self, config: ADASConfig) -> ADASConfig:
        """Apply environment variable overrides"""
        # Example: ADAS_DEBUG_MODE=true
        if os.getenv('ADAS_DEBUG_MODE'):
            config.debug_mode = os.getenv('ADAS_DEBUG_MODE', '').lower() == 'true'
        
        # Example: ADAS_TARGET_FPS=60
        if os.getenv('ADAS_TARGET_FPS'):
            config.target_fps = int(os.getenv('ADAS_TARGET_FPS', '30'))
        
        return config
    
    def get_config(self) -> ADASConfig:
        """Get current configuration"""
        return self.config
    
    def reload(self) -> None:
        """Reload configuration from disk"""
        self.config = self._load_config()


# Global config instance (singleton)
_config_manager: Optional[ConfigManager] = None


def get_config() -> ADASConfig:
    """
    Get global ADAS configuration
    
    Returns:
        ADASConfig instance
        
    Usage:
        from adas_core.config import get_config
        config = get_config()
        camera_config = config.get_sensor_config('camera_front')
    """
    global _config_manager
    
    if _config_manager is None:
        _config_manager = ConfigManager()
    
    return _config_manager.get_config()


def reload_config() -> None:
    """Reload configuration from disk"""
    global _config_manager
    
    if _config_manager:
        _config_manager.reload()
