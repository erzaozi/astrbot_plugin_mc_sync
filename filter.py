from astrbot.core.star.filter.custom_filter import (
    AstrBotConfig,
    AstrMessageEvent,
    CustomFilter,
)

from .utils.config import ConfigManager


class QueQiaoPlatformFilter(CustomFilter):
    """只允许来自 'queqiao' 平台的消息通过"""

    def __init__(self, raise_error: bool = True):
        # 调用父类构造函数，传入 raise_error
        super().__init__(raise_error)

    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        # 返回 True 表示通过，False 表示被过滤
        return event.platform_meta.name == "QueQiao"


class ServerAdminFilter(CustomFilter):
    """Allow framework administrators or administrators of the target server."""

    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        """Check the server argument and compare the sender with its administrators.

        Args:
            event: The command event being evaluated.
            cfg: The AstrBot configuration supplied by the framework.

        Returns:
            True when the sender can administer the target server.
        """
        if event.is_admin():
            return True

        parts = event.get_message_str().strip().split()
        if len(parts) < 3:
            if (
                len(parts) == 2
                and parts[0].lstrip("/#").casefold() == "mc"
                and parts[1].casefold() == "status"
            ):
                return any(
                    event.get_sender_id() in server.administrators
                    for server in ConfigManager().config.sync_config
                )
            return False

        server = ConfigManager().get_server(parts[2])
        return server is not None and event.get_sender_id() in server.administrators
