from pathlib import Path
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

PLUGIN_NAME = "astrbot_plugin_mc_sync"
plugin_data_dir = Path(get_astrbot_data_path()) / "plugin_data" / PLUGIN_NAME

def _get_data_dir() -> Path:
    """获取插件数据目录（延迟初始化）"""
    return plugin_data_dir

def _ensure_dir(path: Path) -> Path:
    """确保目录存在"""
    path.mkdir(parents=True, exist_ok=True)
    return path

def get_config_path() -> Path:
    """获取配置根目录"""
    return _ensure_dir(_get_data_dir() / "config")