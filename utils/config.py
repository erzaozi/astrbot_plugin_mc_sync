"""Config 管理器
astr无法实现list嵌套object，因此自己实现
- SyncConfig: 服务器同步配置
"""
from __future__ import annotations
from .path import get_config_path
from pathlib import Path
import yaml
from pydantic import BaseModel, Field

class PluginConfig(BaseModel):
    sync_config: list[SyncConfig] = Field(default_factory=list, description="服务器同步列表配置")
    cicode_enabled: bool = Field(default_factory=bool, description="同步图片是否启用CICode")

class SyncConfig(BaseModel):
    """单个 MC 服务器同步配置"""
    server_name: str = Field(default_factory=str, description="服务器名")
    umo_list: list[str] = Field(default_factory=list, description="绑定的UMO会话列表")

class ConfigManager:
    """配置文件管理器。

    将服务器配置与消息同步配置统一读写到单个 YAML 文件，
    同时暴露 dump_model/apply_model 供 Dashboard 集成。
    """
    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self._path: Path = get_config_path() / "config.yaml"
            self._plugin_config = PluginConfig(sync_config=[])
            self.load()
            type(self)._initialized = True

    # ---------- 文件 I/O ----------

    def load(self) -> ConfigManager:
        if self._path.exists():
            with open(self._path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            self._plugin_config = PluginConfig.model_validate(data)
        else:
            self.save()
        return self

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        merged = {
            **self._plugin_config.model_dump(exclude_defaults=False),
        }
        with open(self._path, "w", encoding="utf-8") as f:
            # 字段顺序：服务器配置在前，消息配置在后
            yaml.safe_dump(merged, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    # ---------- Dashboard 集成 ----------

    def dump_model(self) -> dict:
        return {
            **self._plugin_config.model_dump(exclude_defaults=False),
        }

    def apply_model(self, data: dict) -> None:
        self._plugin_config = PluginConfig.model_validate(data)
        self.save()

    # ---------- 属性 ----------

    @property
    def config(self) -> PluginConfig:
        return self._plugin_config

    @property
    def server_config(self) -> PluginConfig:
        return self._plugin_config

    @property
    def sync_config(self) -> PluginConfig:
        return self._plugin_config