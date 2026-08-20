from typing import Dict, Any, TYPE_CHECKING, Set
from pydantic import BaseModel
import asyncio
from .models import (QueQiaoResponse,
                     PlayerChatEvent,
                     PlayerCommandEvent,
                     PlayerAchievementEvent,
                     PlayerDeathEvent,
                     PlayerJoinEvent,
                     PlayerQuitEvent)
if TYPE_CHECKING:
    from .queqiao_manager import QueQiaoBridge


# 全局连接管理
class ConnectionNameManager:
    """管理所有连接的 server_name 唯一性"""
    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            type(self)._initialized = True
        self._active_names: Set[str] = set()
        self._lock = asyncio.Lock()

    async def register_name(self, server_name: str) -> bool:
        """注册服务器名称，返回是否成功（名称未被占用）"""
        async with self._lock:
            if server_name in self._active_names:
                return False
            self._active_names.add(server_name)
            return True

    async def unregister_name(self, server_name: str) -> None:
        """注销服务器名称"""
        async with self._lock:
            self._active_names.discard(server_name)

    def is_name_active(self, server_name: str) -> bool:
        """检查名称是否已被使用"""
        return server_name in self._active_names

def event_parser(data: Dict[str, Any]) -> BaseModel | None:
    event_map = {
        "PlayerChatEvent": PlayerChatEvent,
        "PlayerCommandEvent": PlayerCommandEvent,
        "PlayerJoinEvent": PlayerJoinEvent,
        "PlayerQuitEvent": PlayerQuitEvent,
        "PlayerDeathEvent": PlayerDeathEvent,
        "PlayerAchievementEvent": PlayerAchievementEvent,
    }

    event_name = data.get("event_name")

    if event_name is not None and event_name in event_map:
        event_class = event_map[event_name]
        return event_class(**data)
    else:
        echo = data.get("echo")
        if echo is not None:
            return QueQiaoResponse(**data)
        else:
            return None

async def handle_event(bridge: 'QueQiaoBridge', event: BaseModel, **kwargs: Any):
    if hasattr(event, 'echo') and event.echo:
        await bridge.bus.emit("callback", event, **kwargs)
        return
    if hasattr(event, 'post_type') and hasattr(event, 'sub_type'):
        event_name = f"{event.post_type}.{event.sub_type}"
        await bridge.bus.emit(event_name, event, **kwargs)