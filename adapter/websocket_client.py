import json
import weakref
import traceback
from typing import Optional, TYPE_CHECKING

import asyncio
from websockets.asyncio.client import ClientConnection, connect as ws_connect
from .models import ClientConfig, ApiName
from .utils import event_parser, handle_event

if TYPE_CHECKING:
    from .queqiao_manager import QueQiaoBridge

class WebsocketClient:
    """单个正向 WebSocket 连接"""

    def __init__(
        self,
        config: ClientConfig,
        bridge: 'QueQiaoBridge',
    ):
        self.server_name: str = config.server_name
        self.ws_url: str = config.ws_url
        self.ws_auth: str = config.ws_auth
        self.ws_max_attempts: int = config.ws_max_attempts

        self._ws: ClientConnection | None = None
        self._running: bool = False
        self._pending: dict[str, asyncio.Future[dict]] = {} # 用于存储 MC 服务器api响应
        self._task: asyncio.Task[None] | None = None

        self._bridge: weakref.ReferenceType['QueQiaoBridge'] = weakref.ref(bridge)  # 防止循环引用


    @property
    def bridge(self) -> Optional['QueQiaoBridge']:
        bridge = self._bridge()
        if bridge is not None:
            return bridge
        return None

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())

    async def _run_loop(self) -> None:
        max_attempts = self.ws_max_attempts
        attempt = 0

        while self._running:
            attempt += 1

            try:
                # 检查服务器名称是否已被占用
                bridge = self.bridge
                if bridge is None:
                    return
                if bridge.is_registered(self.server_name):
                    self._running = False
                    break #直接终止 loop

                headers = {
                    "x-self-name": self.server_name,
                    "x-client-origin": "astrbot"  # 标识来源
                }

                if self.ws_auth:
                    headers["Authorization"] = f"Bearer {self.ws_auth}"

                async with ws_connect(self.ws_url, additional_headers=headers) as ws:
                    self._ws = ws
                    attempt = 0  # 连接成功后重置计数

                    success = await self.bridge.register(self.server_name, ws)
                    if not success:
                        self._running = False # 确保停止
                        break

                    await self.bridge.bus.emit("system", {
                        "message": f"服务器 [{self.server_name}]({self.ws_url}) 正向 WS 连接成功",
                        "server_name": self.server_name,
                        "level": "info"
                    }, server_name=self.server_name, is_reverse=False)

                    async for raw in ws:
                        if not self._running:
                            break
                        try:
                            msg = json.loads(raw)
                            event = event_parser(msg)
                            if event is not None:
                                await handle_event(bridge, event, server_name=self.server_name, is_reverse=False)
                        except json.JSONDecodeError:
                            continue

            except asyncio.CancelledError:
                await self.bridge.bus.emit("system", {
                    "message": f"与服务器 [{self.server_name}] 的连接协程被关闭",
                    "server_name": self.server_name,
                    "level": "error"
                }, server_name=self.server_name, is_reverse=False)
                self._running = False
                break # 协程被关闭，此时需要退出
            except Exception as e :
                await self.bridge.bus.emit("system", {
                    "message": f"与服务器 [{self.server_name}] 的连接出错: {e}\n{traceback.format_exc()}",
                    "server_name": self.server_name,
                    "level": "error"
                }, server_name=self.server_name, is_reverse=False)
                continue
            finally:
                if self.bridge.is_registered(self.server_name):
                    await self.bridge.unregister(self.server_name)

            self._ws = None

            if max_attempts == 0 or 0 < max_attempts <= attempt:
                self._running = False
                break

            await asyncio.sleep(5)

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            finally:
                self._task = None