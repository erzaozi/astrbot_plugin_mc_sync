"""Config 管理器
astr无法实现list嵌套object，因此自己实现
- SyncConfig: 服务器同步配置
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from .path import get_config_path


class PluginConfig(BaseModel):
    sync_config: list[SyncConfig] = Field(
        default_factory=list, description="服务器同步列表配置"
    )


class SyncConfig(BaseModel):
    """单个 MC 服务器同步配置"""

    server_name: str = Field(default_factory=str, description="服务器名")
    umo_list: list[str] = Field(default_factory=list, description="绑定的UMO会话列表")
    forward_session_messages: bool = Field(
        True, description="是否将绑定会话的消息转发到服务器"
    )
    cicode_enabled: bool = Field(True, description="该服务器是否启用 CICode 图片")
    administrators: list[str] = Field(
        default_factory=list, description="服务器管理员 UID 列表"
    )
    forward_player_join: bool = Field(True, description="是否转发玩家加入事件")
    forward_player_quit: bool = Field(True, description="是否转发玩家退出事件")
    forward_player_death: bool = Field(True, description="是否转发玩家死亡事件")
    forward_player_achievement: bool = Field(True, description="是否转发玩家成就事件")
    rcon_enabled: bool = Field(False, description="是否允许 RCON")
    rcon_command_whitelist: list[str] = Field(
        default_factory=list, description="RCON 命令白名单"
    )


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
            with open(self._path, encoding="utf-8") as f:
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
            yaml.safe_dump(
                merged, f, allow_unicode=True, default_flow_style=False, sort_keys=False
            )

    # ---------- Dashboard 集成 ----------

    def dump_model(self) -> dict:
        return {
            **self._plugin_config.model_dump(exclude_defaults=False),
        }

    def apply_model(self, data: dict) -> None:
        self._plugin_config = PluginConfig.model_validate(data)
        self.save()

    def get_server(self, server_name: str) -> SyncConfig | None:
        """Find a server synchronization configuration by name.

        Args:
            server_name: The configured MC server name.

        Returns:
            The matching configuration, or None when it does not exist.
        """
        return next(
            (
                item
                for item in self._plugin_config.sync_config
                if item.server_name == server_name
            ),
            None,
        )

    def ensure_server(self, server_name: str) -> SyncConfig:
        """Create a default synchronization configuration when absent.

        Args:
            server_name: The MC server name.

        Returns:
            The existing or newly created server configuration.
        """
        server = self.get_server(server_name)
        if server is None:
            server = SyncConfig(server_name=server_name)
            self._plugin_config.sync_config.append(server)
        return server

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
