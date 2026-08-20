import re
import asyncio
from abc import ABC, abstractmethod

from astrbot.api.platform import Platform, AstrBotMessage, MessageMember, PlatformMetadata, MessageType
from astrbot.api.event import MessageChain
from astrbot.api import logger
from astrbot.core.platform.astr_message_event import MessageSesion
from .queqiao_manager import QueQiaoBridge
from .event import QueQiaoMessageEvent
from ..utils.config import ConfigManager
from .models import (
    PlayerChatEvent,
    PlayerCommandEvent,
    PlayerAchievementEvent,
    PlayerDeathEvent,
    PlayerJoinEvent,
    PlayerQuitEvent,
)
from astrbot.api.message_components import (
    BaseMessageComponent,
    Image,
    Plain,
)

# 定义抽象基类
class QueQiaoPlatformBase(Platform, ABC):
    def __init__(
        self,
        platform_config: dict,
        platform_settings: dict,
        event_queue: asyncio.Queue
    ) -> None:
        super().__init__(platform_config, event_queue)
        self.settings = platform_settings
        self.config = platform_config
        self._is_running = False
        self.bot = QueQiaoBridge()
        # 子类必须实现 _create_network 并在 __init__ 中调用
        self._network = self._create_network()


    def _create_network(self):
        """子类必须实现，返回网络实例 (WebsocketClient 或 WebsocketServer)"""
        raise NotImplementedError

    def _should_ignore_event(self, kwargs: dict) -> bool:
        """子类可重写，返回 True 表示忽略该事件"""
        return False

    async def send_by_session(self, session: MessageSesion, message_chain: MessageChain):
        session_id = session.session_id
        await QueQiaoMessageEvent.send_message(
            bot=self.bot,
            message_chain=message_chain,
            session_id=session_id,
            cicode_enabled=ConfigManager().config.cicode_enabled,
        )
        await super().send_by_session(session, message_chain)

    @abstractmethod
    def meta(self) -> PlatformMetadata:
        raise NotImplementedError

    async def run(self):
        if self._is_running:
            return None
        self._is_running = True

        # 注册事件处理器
        self._register_handlers()

        # 启动网络
        coro = self._network.start()
        return await coro

    def _register_handlers(self):
        """注册所有事件处理器，公共逻辑"""
        @self.bot.before_message()
        async def handle_message_player_cache(event: PlayerChatEvent | PlayerCommandEvent, **kwargs):
            if self._should_ignore_event(kwargs):
                return
            self.bot.cache_player((event.player.get("nickname"), event.player.get("uuid")))

        @self.bot.before_notice()
        async def handle_notice_player_cache(
                event: PlayerJoinEvent | PlayerQuitEvent | PlayerDeathEvent | PlayerAchievementEvent,
                **kwargs
        ):
            if self._should_ignore_event(kwargs):
                return
            self.bot.cache_player((event.player.get("nickname"), event.player.get("uuid")))

        @self.bot.on_message("player_chat")
        async def handle_player_chat(event: PlayerChatEvent, **kwargs):
            if self._should_ignore_event(kwargs):
                return
            abm = self._convert_queqiao_message(
                event={**event.model_dump(exclude_none=True)},
                server_name=kwargs.get("server_name")
            )
            await self.handle_msg(abm)

        @self.bot.on_message("player_command")
        async def handle_player_command(event: PlayerCommandEvent, **kwargs):
            if self._should_ignore_event(kwargs):
                return
            logger.info(
                f"[Server: {kwargs.get('server_name')}]"
                f"{event.player.get('nickname', '未知玩家')}"
                f"({event.player.get('uuid', '未知uuid')}) 使用命令: {event.command}"
            )

        @self.bot.on_notice("player_join")
        async def handle_player_join(event: PlayerJoinEvent, **kwargs):
            if self._should_ignore_event(kwargs):
                return
            logger.info(
                f"[Server: {kwargs.get('server_name')}]"
                f"{event.player.get('nickname', '未知玩家')}"
                f"({event.player.get('uuid', '未知uuid')}) 加入了游戏"
            )

        @self.bot.on_notice("player_quit")
        async def handle_player_quit(event: PlayerQuitEvent, **kwargs):
            if self._should_ignore_event(kwargs):
                return
            logger.info(
                f"[Server: {kwargs.get('server_name')}]"
                f"{event.player.get('nickname', '未知玩家')}"
                f"({event.player.get('uuid', '未知uuid')}) 离开了游戏"
            )

        @self.bot.on_notice("player_death")
        async def handle_player_death(event: PlayerDeathEvent, **kwargs):
            if self._should_ignore_event(kwargs):
                return
            logger.info(
                f"[Server: {kwargs.get('server_name')}]"
                f"{event.player.get('nickname', '未知玩家')}"
                f"({event.player.get('uuid', '未知uuid')}) 死亡:"
                f"{event.death.get('key')}=={event.death.get('args')}=={event.death.get('text')}"
            )

        @self.bot.on_notice("player_achievement")
        async def handle_player_achievement(event: PlayerAchievementEvent, **kwargs):
            if self._should_ignore_event(kwargs):
                return
            logger.info(
                f"[Server: {kwargs.get('server_name')}]"
                f"{event.player.get('nickname', '未知玩家')}"
                f"({event.player.get('uuid', '未知uuid')}) 获得成就:"
                f"{event.achievement.get('key')}=={event.achievement.get('display')}=={event.achievement.get('translate')}"
            )

        @self.bot.on_system()
        async def handle_system(data: dict, **kwargs):
            if self._should_ignore_event(kwargs):
                return
            level = data.get("level")
            message = data.get("message", "未知消息类型")
            if level == "info":
                logger.info(message)
            elif level == "error":
                logger.error(message)
            else:
                logger.warn(message)

    async def terminate(self):
        if self._network:
            await self._network.stop()
        self._is_running = False

    async def handle_msg(self, message: AstrBotMessage):
        self.commit_event(self.create_event(message))

    def create_event(self, message: AstrBotMessage) -> QueQiaoMessageEvent:
        return QueQiaoMessageEvent(
            message_str=message.message_str,
            message_obj=message,
            platform_meta=self.meta(),
            session_id=message.session_id,
            cicode_enabled=ConfigManager().config.cicode_enabled,
            bot=self.bot,
        )

    def _convert_queqiao_message(self, event: dict, **extra_data) -> AstrBotMessage:
        abm = AstrBotMessage()

        abm.type = MessageType.GROUP_MESSAGE
        abm.group_id = extra_data['server_name']
        abm.message_str = event['raw_message'].strip('"')
        abm.sender = MessageMember(user_id=event['player']['uuid'], nickname=event['player']['nickname'])
        abm.message = self._parse_cicode_components(event['raw_message'].strip('"'))
        abm.raw_message = event
        abm.self_id = extra_data['server_name']
        abm.session_id = extra_data['server_name']
        abm.message_id = event['message_id']
        return abm

    @classmethod
    def _parse_cicode_components(cls, raw: str) -> list[BaseMessageComponent]:
        pattern = r'\[\[CICode,([^\]]+)\]\]'
        components = []
        last_end = 0

        for match in re.finditer(pattern, raw):
            start, end = match.start(), match.end()
            params_str = match.group(1)

            params = {}
            for pair in params_str.split(','):
                if '=' in pair:
                    key, value = pair.split('=', 1)
                    params[key.strip()] = value.strip()

            if start > last_end:
                components.append(Plain(text=raw[last_end:start]))

            url = params.get('url')
            if url:
                try:
                    if url.startswith('file://'):
                        local_path = url[7:]
                        img = Image.fromFileSystem(local_path)
                    elif url.startswith('http://') or url.startswith('https://'):
                        img = Image.fromURL(url)
                    else:
                        components.append(Plain(text=raw[start:end]))
                        last_end = end
                        continue
                    components.append(img)
                except Exception:
                    components.append(Plain(text=raw[start:end]))
            else:
                components.append(Plain(text=raw[start:end]))
            last_end = end

        if last_end < len(raw):
            components.append(Plain(text=raw[last_end:]))

        return components