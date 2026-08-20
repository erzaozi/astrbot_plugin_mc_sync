import asyncio
import functools
import uuid
from typing import Dict, Callable, Any, Awaitable, Tuple

from websockets import ClientConnection, ServerConnection
from .models import QueQiaoRequest, QueQiaoResponse, ApiName
from .bus import EventBus
from .deco import create_event_decorator
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
        self.connections: Dict[str, ServerConnection | ClientConnection] = {}
        self.bus: EventBus = EventBus() # 仅在反向ws连接时有效
        self._connection_to_name: Dict[ServerConnection | ClientConnection, str] = {}  # 反向映射
        self._connection_manager: ConnectionNameManager = ConnectionNameManager()

        self.on_message = create_event_decorator(self.on, 'message')
        self.on_notice = create_event_decorator(self.on, 'notice')
        self.on_system = create_event_decorator(self.on, 'system')
        self.before_message = create_event_decorator(self.before, 'message')
        self.before_notice = create_event_decorator(self.before, 'notice')
        self.before_system = create_event_decorator(self.before, 'system')
        self._pending: dict[str, asyncio.Future[Tuple[QueQiaoResponse, str]]] = {}
        self.subscribe('callback', self.on_callback)
        self.player_map = {} # uuid -> player_name

    async def register(self, name: str, ws: ServerConnection | ClientConnection) -> bool:
        if await self._connection_manager.register_name(name):
            self.connections[name] = ws
            self._connection_to_name[ws] = name
            await self.bus.emit("system", {
                "message": f"服务器 [{name}] 连接注册成功",
                "server_name": name,
                "level": "info"
            })
            return True
        else:
            await self.bus.emit("system", {
                "message": f"服务器 [{name}] 已存在，连接注册失败",
                "server_name": name,
                "level": "error"
            })
            return False

    async def unregister(self, name: str) -> None:
        ws = self.connections.get(name)
        if ws:
            del self._connection_to_name[ws]  # 移除反向映射
        await self._connection_manager.unregister_name(name)
        del self.connections[name]
        await self.bus.emit("system", {
            "message": f"服务器 [{name}] 连接已注销",
            "server_name": name,
            "level": "info"
        })

    def is_registered(self, name: str) -> bool:
        return name in self.connections

    def get_name_by_connection(self, ws: ServerConnection | ClientConnection) -> str | None:
        """通过连接获取名称"""
        return self._connection_to_name.get(ws)

    def get_connection_by_name(self, name: str) -> ServerConnection | ClientConnection | None:
        """通过名称获取连接"""
        return self.connections.get(name)

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

    async def send_api(self, server_name: str, api: ApiName, data: dict | None, timeout: float = 30.0) -> QueQiaoResponse:
        ws = self.get_connection_by_name(server_name)
        if not ws:
            raise ConnectionError
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
            await self._pending.pop(echo, None)
            raise TimeoutError(f"[{server_name}] 请求超时: {api}")
        except Exception:
            await self._pending.pop(echo, None)
            raise Exception(f"[{server_name}] 请求失败: {api}")

    async def send_api_without_response(self, server_name: str, api: ApiName, data: dict | None, timeout: float = 30.0) -> None:
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

    def on_callback(self, event: QueQiaoResponse, server_name: str) -> None:
        echo = event.get("echo")
        fut = self._pending.pop(echo, None)
        if fut and not fut.done():
            asyncio.get_running_loop().call_soon_threadsafe(fut.set_result, (event, server_name))
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