from astrbot.api.star import Context, Star
from astrbot.api.event import filter, AstrMessageEvent, MessageChain
from .adapter.event import QueQiaoMessageEvent
from .adapter.dispatch import send_message_by_server, send_message_by_umo
from .adapter.queqiao_manager import QueQiaoBridge
from .utils.config import ConfigManager, SyncConfig
from .filter import QueQiaoPlatformFilter

class QueQiaoPlugin(Star):
    def __init__(self, context: Context):
        from .adapter.adapter_reverse import QueQiaoPlatformReverseAdapter # noqa: F401
        from .adapter.adapter_forward import QueQiaoPlatformForwardAdapter # noqa: F401

        super().__init__(context)
        self.config_manager = ConfigManager()
        self.bot = QueQiaoBridge()

    async def dispatch_msg(self, umo: str, message_chain: MessageChain):
        await self.context.send_message(umo, message_chain)

    async def terminate(self):
        pass

    @filter.command_group('sync')
    def sync(self):
        pass

    @sync.command('on')
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def sync_on(self, event: AstrMessageEvent, server_name: str):
        """绑定当前会话到指定服务器"""
        umo = event.unified_msg_origin
        config = self.config_manager.config  # PluginConfig 实例
        sync_list = config.sync_config

        target = next((s for s in sync_list if s.server_name == server_name), None)

        if target is None:
            new_sync = SyncConfig(server_name=server_name, umo_list=[umo])
            sync_list.append(new_sync)
            self.config_manager.save()
            yield event.plain_result(f"已为服务器 `{server_name}` 创建同步，并绑定当前会话")
        else:
            if umo in target.umo_list:
                yield event.plain_result(f"当前会话已经绑定到服务器 `{server_name}`，无需重复添加")
            else:
                target.umo_list.append(umo)
                self.config_manager.save()
                yield event.plain_result(f"当前会话已绑定到服务器 `{server_name}`")

    @sync.command('off')
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def sync_off(self, event: AstrMessageEvent, server_name: str):
        """解绑当前会话与指定服务器"""
        umo = event.unified_msg_origin
        config = self.config_manager.config
        sync_list = config.sync_config

        target = next((s for s in sync_list if s.server_name == server_name), None)

        if target is None:
            yield event.plain_result(f"未找到服务器 `{server_name}` 的同步配置")
            return

        if umo not in target.umo_list:
            yield event.plain_result(f"ℹ当前会话未绑定到服务器 `{server_name}`，无需解绑")
            return

        target.umo_list.remove(umo)
        self.config_manager.save()
        yield event.plain_result(f"当前会话已从服务器 `{server_name}` 解绑")

    @filter.custom_filter(QueQiaoPlatformFilter)
    async def on_queqiao(self, event: AstrMessageEvent):
        from astrbot.api import logger
        logger.warn(event.get_messages())
        '''只接收 queqiao 的消息，并同步'''
        await send_message_by_server(
            event.session.session_id,
            event.chain_result(event.get_messages()),
            self.context.send_message
        )

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_other_platform(self, event: AstrMessageEvent):
        """处理所有消息，转发到绑定的 MC 服务器"""
        await send_message_by_umo(
            event.unified_msg_origin,
            event.chain_result(event.get_messages()),
            QueQiaoMessageEvent.send_message,
            self.bot
        )