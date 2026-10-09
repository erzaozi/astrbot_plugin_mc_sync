import asyncio
import functools
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

from websockets import ClientConnection, ServerConnection
from websockets.exceptions import ConnectionClosed

from .bus import EventBus
from .deco import create_event_decorator
from .models import ApiName, QueQiaoRequest, QueQiaoResponse
from .utils import ConnectionNameManager


class QueQiaoBridge:
    """鹊桥管理器，管理所有建立的 WS 连接"""

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            type(self)._initialized = True
            self.connections: dict[str, ServerConnection | ClientConnection] = {}
            self.bus: EventBus = EventBus()
            self._connection_to_name: dict[
                ServerConnection | ClientConnection, str
            ] = {}
            self._connection_manager: ConnectionNameManager = ConnectionNameManager()
            self.on_message = create_event_decorator(self.on, "message")
            self.on_notice = create_event_decorator(self.on, "notice")
            self.on_system = create_event_decorator(self.on, "system")
            self.before_message = create_event_decorator(self.before, "message")
            self.before_notice = create_event_decorator(self.before, "notice")
            self.before_system = create_event_decorator(self.before, "system")
            self._pending: dict[str, asyncio.Future[QueQiaoResponse]] = {}
            self.subscribe("callback", self.on_callback)
            self.player_map = {}
            self.connection_status: dict[str, dict] = {}

    async def register(
        self,
        name: str,
        ws: ServerConnection | ClientConnection,
        direction: str = "unknown",
    ) -> bool:
        if await self._connection_manager.register_name(name):
            self.connections[name] = ws
            self._connection_to_name[ws] = name
            self.update_status(name, connected=True, direction=direction, last_error="")
            await self.bus.emit(
                "system",
                {
                    "message": f"服务器 [{name}] 连接注册成功",
                    "server_name": name,
                    "level": "info",
                },
            )
            return True
        else:
            await self.bus.emit(
                "system",
                {
                    "message": f"服务器 [{name}] 已存在，连接注册失败",
                    "server_name": name,
                    "level": "error",
                },
            )
            return False

    async def unregister(self, name: str) -> None:
        ws = self.connections.get(name)
        if ws:
            del self._connection_to_name[ws]  # 移除反向映射
        await self._connection_manager.unregister_name(name)
        self.connections.pop(name, None)
        self.update_status(name, connected=False)
        await self.bus.emit(
            "system",
            {
                "message": f"服务器 [{name}] 连接已注销",
                "server_name": name,
                "level": "info",
            },
        )

    def is_registered(self, name: str) -> bool:
        return name in self.connections

    def get_name_by_connection(
        self, ws: ServerConnection | ClientConnection
    ) -> str | None:
        """通过连接获取名称"""
        return self._connection_to_name.get(ws)

    def get_connection_by_name(
        self, name: str
    ) -> ServerConnection | ClientConnection | None:
        """通过名称获取连接"""
        return self.connections.get(name)

    def update_status(self, name: str, **values) -> None:
        """Update observable connection status for a server.

        Args:
            name: The MC server name.
            **values: Status fields to merge into the current state.
        """
        status = self.connection_status.setdefault(
            name,
            {
                "server_name": name,
                "connected": False,
                "direction": "unknown",
                "attempts": 0,
                "last_error": "",
                "last_connected_at": None,
                "last_event_at": None,
            },
        )
        status.update(values)
        if values.get("connected"):
            status["last_connected_at"] = datetime.now(timezone.utc).isoformat()

    def mark_event(self, name: str) -> None:
        """Record the latest event timestamp for a server.

        Args:
            name: The MC server name.
        """
        self.update_status(name, last_event_at=datetime.now(timezone.utc).isoformat())

    def get_status(self) -> list[dict]:
        """Return a serializable snapshot of all known connections.

        Returns:
            Connection status records sorted by server name.
        """
        return [
            self.connection_status[name].copy()
            for name in sorted(self.connection_status)
        ]

    def on(self, *event_names: str) -> Callable:
        def deco(func: Callable) -> Callable:
            for name in event_names:
                self.subscribe(name, func)
            return func

        return deco

    def before(self, *event_names: str) -> Callable:
        def deco(func: Callable) -> Callable:
            for name in event_names:
                self.hook_before(name, func)
            return func

        return deco

    def subscribe(self, event_name: str, func: Callable) -> None:
        """注册事件处理函数。"""
        self.bus.subscribe(event_name, ensure_async(func))

    def unsubscribe(self, event_name: str, func: Callable) -> None:
        """取消注册事件处理函数。"""
        self.bus.unsubscribe(event_name, func)

    def hook_before(self, event_name: str, func: Callable) -> None:
        """注册事件处理前的钩子函数。"""
        self.bus.hook_before(event_name, ensure_async(func))

    def unhook_before(self, event_name: str, func: Callable) -> None:
        """取消注册事件处理前的钩子函数。"""
        self.bus.unhook_before(event_name, func)

    async def send_api(
        self, server_name: str, api: ApiName, data: dict | None, timeout: float = 30.0
    ) -> QueQiaoResponse:
        ws = self.get_connection_by_name(server_name)
        if not ws:
            raise ConnectionError(f"服务器 `{server_name}` 未连接或连接已断开")
        echo = str(uuid.uuid4())
        payload: QueQiaoRequest = QueQiaoRequest(
            api=api,
            data=data,
            echo=echo,
        )
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[echo] = fut
        try:
            data = payload.model_dump_json(ensure_ascii=False, exclude_none=True)
            await ws.send(data)
            result: QueQiaoResponse = await asyncio.wait_for(fut, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            self._pending.pop(echo, None)
            raise TimeoutError(f"[{server_name}] 请求超时: {api}")
        except Exception as exc:
            self._pending.pop(echo, None)
            if isinstance(exc, (ConnectionError, ConnectionClosed)):
                raise ConnectionError(
                    f"服务器 `{server_name}` 未连接或连接已断开"
                ) from exc
            detail = str(exc).strip() or type(exc).__name__
            raise RuntimeError(f"[{server_name}] 请求失败: {api}: {detail}") from exc

    async def send_api_without_response(
        self, server_name: str, api: ApiName, data: dict | None, timeout: float = 30.0
    ) -> None:
        try:
            await self.send_api(server_name, api, data, timeout)
        except Exception:
            pass

    async def broadcast(self, server_name: str, data: dict | None) -> None:
        ws = self.get_connection_by_name(server_name)
        if not ws:
            raise ConnectionError
        payload: QueQiaoRequest = QueQiaoRequest(
            api=ApiName.BROADCAST,
            data=data,
        )
        try:
            data = payload.model_dump_json(ensure_ascii=False, exclude_none=True)
            await ws.send(data)
        except Exception:
            raise Exception(f"[{server_name}] 请求失败: {ApiName.BROADCAST}")

    async def on_callback(
        self,
        event: QueQiaoResponse,
        server_name: str | None = None,
        **_: object,
    ) -> None:
        echo = event.echo
        fut = self._pending.pop(echo, None)
        if fut and not fut.done():
            fut.set_result(event)
        return

    def cache_player(self, player: tuple[str, str]) -> None:
        """
        players: list[tuple[str, str]] -> [('steve', 'uuid'),]
        """
        name, uuid_str = player
        if not name or not uuid_str:
            return
        if self.player_map.get(uuid_str) is None:
            self.player_map[uuid_str] = name

    def get_player_name_by_uuid(self, uuid_str: str) -> str | None:
        return self.player_map.get(uuid_str)


def ensure_async(func: Callable[..., Any]) -> Callable[..., Awaitable[Any]]:
    if asyncio.iscoroutinefunction(func):
        return func
    else:
        return run_sync(func)


def run_sync(func: Callable[..., Any]) -> Callable[..., Awaitable[Any]]:
    """将同步函数转换为异步函数，在线程池中执行"""

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        return await asyncio.to_thread(func, *args, **kwargs)

    return wrapper
