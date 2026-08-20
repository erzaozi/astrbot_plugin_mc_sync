import asyncio
from typing import cast

from astrbot.api.platform import register_platform_adapter, PlatformMetadata
from .adapter_base import QueQiaoPlatformBase
from .websocket_server import WebsocketServer
from .models import ServerConfig

@register_platform_adapter(
    "QueQiao-reverse",
    "QueQiao v2 protocol minecraft 适配器。使用反向 websocket。",
    support_streaming_message=False,
    default_config_tmpl={
        "ws_reverse_host": "127.0.0.1",
        "ws_reverse_port": 6177,
        "ws_server_path": "/minecraft/ws",
        "ws_reverse_token": ""
    }
)
class QueQiaoPlatformReverseAdapter(QueQiaoPlatformBase):
    def __init__(
        self,
        platform_config: dict,
        platform_settings: dict,
        event_queue: asyncio.Queue
    ) -> None:
        super().__init__(platform_config, platform_settings, event_queue)
        self.metadata = PlatformMetadata(
            name="QueQiao",
            description="QueQiao v2 protocol minecraft 适配器。使用反向 websocket。",
            id=cast(str, self.config.get("id")),
            support_streaming_message=False,
        )

    def meta(self) -> PlatformMetadata:
        return self.metadata

    def _create_network(self):
        config = ServerConfig(
            ws_host=self.config.get("ws_reverse_host", "127.0.0.1"),
            ws_port=self.config.get("ws_reverse_port", 6177),
            ws_path=self.config.get("ws_server_path", "/minecraft/ws"),
            ws_auth=self.config.get("ws_reverse_token", ""),
        )
        return WebsocketServer(config, self.bot)

    def _should_ignore_event(self, kwargs: dict) -> bool:
        # 反向：只处理反向事件
        if not kwargs.get("is_reverse"):
            return True
        return False