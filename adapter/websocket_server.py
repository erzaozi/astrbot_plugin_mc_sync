import json
import weakref
from typing import TYPE_CHECKING, Optional

from websockets.asyncio.server import Server, serve as ws_serve, ServerConnection
from .models import ServerConfig
from websockets.exceptions import ConnectionClosed
from .utils import event_parser, handle_event

if TYPE_CHECKING:
    from .queqiao_manager import QueQiaoBridge


class WebsocketServer:
    """反向 WebSocket 服务器"""

    def __init__(
        self,
        config: ServerConfig,
        bridge: 'QueQiaoBridge',
    ):
        self.host: str = config.ws_host
        self.port: int = config.ws_port
        self.path: str = config.ws_path
        self.auth: str = config.ws_auth

        self._server: Optional[Server] = None
        self._bridge: weakref.ReferenceType['QueQiaoBridge'] = weakref.ref(bridge)  # 防止循环引用

    @property
    def bridge(self) -> Optional['QueQiaoBridge']:
        bridge = self._bridge()
        if bridge is not None:
            return bridge
        return None

    async def start(self) -> None:
        async def _on_connect(ws: ServerConnection) -> None:
            if ws.request.path != self.path:
                await ws.close(1008, "路由不匹配")
                return
            headers = ws.request.headers
            # 获取服务器名称（必填）
            server_name = headers.get("x-self-name")
            if not server_name:
                await ws.close(4001, "headers 缺少 x-self-name")
                return

            # 等待鉴权
            if self.auth:
                auth_header = headers.get("Authorization", "")
                if auth_header.startswith("Bearer "):
                    token = auth_header[7:]
                else:
                    token = auth_header
                if token != self.auth:
                    await ws.close(4001, "Authorization 鉴权失败")
                    return

            # 检查服务器名称是否已被占用
            bridge = self.bridge
            if bridge is None:
                await ws.close(1011, "QueQiao 内部错误")
                return
            if not await bridge.register(server_name, ws):
                await ws.close(4001, f"服务器名称 [{server_name}] 已被占用")
                return

            try:
                await self.bridge.bus.emit("system", {
                    "message": f"服务器 [{server_name}]({":".join([str(i) for i in ws.remote_address])}) 反向 WS 连接成功",
                    "server_name": server_name,
                    "level": "info"
                }, server_name=server_name, is_reverse=True)
                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                        event = event_parser(msg)
                        if event is not None:
                            await handle_event(bridge, event, server_name=server_name, is_reverse=True)
                    except json.JSONDecodeError:
                        continue

            except ConnectionClosed:
                await self.bridge.bus.emit("system", {
                    "message": f"与服务器 [{server_name}] 的连接被关闭",
                    "server_name": server_name,
                    "level": "error"
                }, server_name=server_name, is_reverse=True)
                pass
            finally:
                await ws.close()
                await self.bridge.unregister(server_name)

        self._server = await ws_serve(
            _on_connect,
            self.host,
            self.port,
        )

    async def stop(self) -> None:
        if self._server:
            self._server.close(True)
            await self._server.wait_closed()
            self._server = None