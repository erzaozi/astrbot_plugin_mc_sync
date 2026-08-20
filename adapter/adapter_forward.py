import asyncio
from typing import cast

from astrbot.api.platform import register_platform_adapter, PlatformMetadata
from .adapter_base import QueQiaoPlatformBase
from .websocket_client import WebsocketClient
from .models import ClientConfig

@register_platform_adapter(
    "QueQiao-forward",
    "QueQiao v2 protocol Minecraft adapter, using forward WebSocket.",
    support_streaming_message=False,
    default_config_tmpl={
        "server_name": "Server",
        "ws_url": "ws://127.0.0.1:25555",
        "ws_auth": "",
        "ws_max_attempts": -1,
    }
)
class QueQiaoPlatformForwardAdapter(QueQiaoPlatformBase):
    def __init__(
        self,
        platform_config: dict,
        platform_settings: dict,
        event_queue: asyncio.Queue
    ) -> None:
        super().__init__(platform_config, platform_settings, event_queue)
        # 设置 metadata
        self.metadata = PlatformMetadata(
            name="QueQiao",
            description="QueQiao v2 protocol minecraft 适配器。使用正向 websocket。",
            id=cast(str, self.config.get("id")),
            support_streaming_message=False,
        )

    def meta(self) -> PlatformMetadata:
        return self.metadata

    def _create_network(self):
        config = ClientConfig(
            server_name=self.config.get("server_name"),
            ws_url=self.config.get("ws_url"),
            ws_auth=self.config.get("ws_auth"),
            ws_max_attempts=self.config.get("ws_max_attempts"),
        )
        return WebsocketClient(config, self.bot)

    def _should_ignore_event(self, kwargs: dict) -> bool:
        # 正向：忽略反向事件，且只处理指定服务器
        if kwargs.get("is_reverse"):
            return True
        if kwargs.get("server_name") != self.config.get("server_name"):
            return True
        return False