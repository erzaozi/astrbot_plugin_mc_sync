from __future__ import annotations

import asyncio
import json

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import At, Plain
from astrbot.api.star import Context, Star
from astrbot.api.web import error_response, json_response, request
from astrbot.core.star.filter.command import GreedyStr

from .adapter.dispatch import send_message_by_server, send_message_by_umo
from .adapter.event import QueQiaoMessageEvent
from .adapter.models import ApiName
from .adapter.queqiao_manager import QueQiaoBridge
from .filter import QueQiaoPlatformFilter, ServerAdminFilter
from .utils.config import ConfigManager


class QueQiaoPlugin(Star):
    """Synchronize AstrBot messages and controls with Minecraft servers."""

    def __init__(self, context: Context):
        from .adapter.adapter_forward import QueQiaoPlatformForwardAdapter  # noqa: F401
        from .adapter.adapter_reverse import QueQiaoPlatformReverseAdapter  # noqa: F401

        super().__init__(context)
        self.config_manager = ConfigManager()
        self.bot = QueQiaoBridge()
        context.register_web_api(
            "/astrbot_plugin_mc_sync/config",
            self.web_config,
            ["GET", "POST"],
            "MC sync configuration",
        )
        context.register_web_api(
            "/astrbot_plugin_mc_sync/status",
            self.web_status,
            ["GET"],
            "MC sync connection status",
        )

    async def terminate(self):
        """Stop plugin-owned network resources."""

    @filter.command_group("sync")
    def sync(self):
        """Manage chat bindings and server administrators."""

    @sync.command("on")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def sync_on(self, event: AstrMessageEvent, server_name: str):
        """Bind the current conversation to a Minecraft server.

        Args:
            event: The command event.
            server_name: The configured Minecraft server name.
        """
        server = self.config_manager.ensure_server(server_name)
        if event.unified_msg_origin in server.umo_list:
            yield event.plain_result(f"当前会话已经绑定到服务器 `{server_name}`")
            return
        server.umo_list.append(event.unified_msg_origin)
        self.config_manager.save()
        yield event.plain_result(f"当前会话已绑定到服务器 `{server_name}`")

    @sync.command("off")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def sync_off(self, event: AstrMessageEvent, server_name: str):
        """Unbind the current conversation from a Minecraft server.

        Args:
            event: The command event.
            server_name: The configured Minecraft server name.
        """
        server = self.config_manager.get_server(server_name)
        if server is None or event.unified_msg_origin not in server.umo_list:
            yield event.plain_result(f"当前会话未绑定到服务器 `{server_name}`")
            return
        server.umo_list.remove(event.unified_msg_origin)
        self.config_manager.save()
        yield event.plain_result(f"当前会话已从服务器 `{server_name}` 解绑")

    @sync.command("admin-add")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def admin_add(
        self, event: AstrMessageEvent, server_name: str, user_id: str = ""
    ):
        """Add a server administrator by UID or an At component.

        Args:
            event: The command event.
            server_name: The server receiving the administrator.
            user_id: Optional UID supplied as the command argument.
        """
        admin_id = user_id.strip()
        for component in event.get_messages():
            if isinstance(component, At) and str(component.qq) not in {"all", ""}:
                admin_id = str(component.qq)
                break
        if not admin_id:
            yield event.plain_result("请提供用户 UID 或艾特一名用户")
            return
        server = self.config_manager.ensure_server(server_name)
        if admin_id not in server.administrators:
            server.administrators.append(admin_id)
            self.config_manager.save()
        yield event.plain_result(
            f"已将 `{admin_id}` 添加为 `{server_name}` 的服务器管理员"
        )

    @sync.command("admin-remove")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def admin_remove(
        self, event: AstrMessageEvent, server_name: str, user_id: str
    ):
        """Remove a server administrator by UID.

        Args:
            event: The command event.
            server_name: The server receiving the change.
            user_id: The administrator UID.
        """
        server = self.config_manager.get_server(server_name)
        if server is None or user_id not in server.administrators:
            yield event.plain_result("未找到该服务器管理员")
            return
        server.administrators.remove(user_id)
        self.config_manager.save()
        yield event.plain_result(f"已移除 `{user_id}` 的服务器管理员权限")

    @filter.command_group("mc")
    @filter.custom_filter(ServerAdminFilter)
    def mc(self):
        """Run Minecraft server APIs as a framework or server administrator."""

    @mc.command("status")
    async def mc_status(self, event: AstrMessageEvent, server_name: str = ""):
        """Query one server, or all servers accessible to the requester."""
        yield event.plain_result(await self._query_status(event, server_name))

    @mc.command("broadcast")
    async def mc_broadcast(
        self, event: AstrMessageEvent, server_name: str, message: GreedyStr
    ):
        """Broadcast a message to a selected Minecraft server."""
        result = await self._server_api(
            event, server_name, ApiName.BROADCAST, {"message": message}
        )
        yield event.plain_result(self._format_api_result(result))

    @mc.command("private")
    async def mc_private(
        self,
        event: AstrMessageEvent,
        server_name: str,
        user_id: str,
        message: GreedyStr,
    ):
        """Send a private message to a Minecraft player."""
        result = await self._server_api(
            event,
            server_name,
            ApiName.SEND_PRIVATE_MSG,
            {"user_id": user_id, "message": message},
        )
        yield event.plain_result(self._format_api_result(result))

    @mc.command("title")
    async def mc_title(
        self, event: AstrMessageEvent, server_name: str, message: GreedyStr
    ):
        """Send a title to a selected Minecraft server."""
        result = await self._server_api(
            event, server_name, ApiName.SEND_TITLE, {"message": message}
        )
        yield event.plain_result(self._format_api_result(result))

    @mc.command("actionbar")
    async def mc_actionbar(
        self, event: AstrMessageEvent, server_name: str, message: GreedyStr
    ):
        """Send an action bar message to a selected Minecraft server."""
        result = await self._server_api(
            event, server_name, ApiName.SEND_ACTIONBAR, {"message": message}
        )
        yield event.plain_result(self._format_api_result(result))

    @mc.command("rcon")
    async def mc_rcon(
        self, event: AstrMessageEvent, server_name: str, command: GreedyStr
    ):
        """Execute a permitted RCON command from chat."""
        yield event.plain_result(await self._run_rcon(event, server_name, command))

    @filter.llm_tool(name="mc_get_bound_servers")
    async def llm_mc_get_bound_servers(self, event: AstrMessageEvent) -> str:
        """Get the exact Minecraft server names bound to the current conversation.

        Call this before a Minecraft tool when the target server name is unknown.
        A binding does not grant permission to call server APIs.

        Returns:
            A JSON array of bound server names, or a message when none are bound.
        """
        server_names = [
            server.server_name
            for server in self.config_manager.config.sync_config
            if event.unified_msg_origin in server.umo_list
        ]
        if not server_names:
            return "当前会话未绑定任何 Minecraft 服务器，请先使用 /sync on <服务器名> 绑定。"
        return json.dumps(server_names, ensure_ascii=False)

    @filter.llm_tool(name="mc_status")
    async def llm_mc_status(
        self, event: AstrMessageEvent, server_name: str = ""
    ) -> str:
        """Query Minecraft server status.

        Omit server_name to query every server the requester may administer.
        Use mc_get_bound_servers when an exact server name is needed.

        Args:
            server_name (string): Optional exact configured server name.

        Returns:
            A readable status summary or an error for each selected server.
        """
        return await self._query_status(event, server_name)

    @filter.llm_tool(name="mc_broadcast")
    async def llm_mc_broadcast(
        self, event: AstrMessageEvent, server_name: str, message: str
    ) -> str:
        """Broadcast a message to all players on one Minecraft server.

        Args:
            server_name (string): Exact configured server name.
            message (string): Message to broadcast.

        Returns:
            The server response or an access error.
        """
        return await self._run_llm_server_api(
            event, server_name, ApiName.BROADCAST, {"message": message}
        )

    @filter.llm_tool(name="mc_private")
    async def llm_mc_private(
        self, event: AstrMessageEvent, server_name: str, user_id: str, message: str
    ) -> str:
        """Send a private message to one Minecraft player.

        Args:
            server_name (string): Exact configured server name.
            user_id (string): Target player's user ID.
            message (string): Private message to send.

        Returns:
            The server response or an access error.
        """
        return await self._run_llm_server_api(
            event,
            server_name,
            ApiName.SEND_PRIVATE_MSG,
            {"user_id": user_id, "message": message},
        )

    @filter.llm_tool(name="mc_title")
    async def llm_mc_title(
        self, event: AstrMessageEvent, server_name: str, message: str
    ) -> str:
        """Show a title to players on one Minecraft server.

        Args:
            server_name (string): Exact configured server name.
            message (string): Title text to show.

        Returns:
            The server response or an access error.
        """
        return await self._run_llm_server_api(
            event, server_name, ApiName.SEND_TITLE, {"message": message}
        )

    @filter.llm_tool(name="mc_actionbar")
    async def llm_mc_actionbar(
        self, event: AstrMessageEvent, server_name: str, message: str
    ) -> str:
        """Show an action bar message to players on one Minecraft server.

        Args:
            server_name (string): Exact configured server name.
            message (string): Action bar text to show.

        Returns:
            The server response or an access error.
        """
        return await self._run_llm_server_api(
            event, server_name, ApiName.SEND_ACTIONBAR, {"message": message}
        )

    @filter.llm_tool(name="mc_rcon")
    async def llm_mc_rcon(
        self, event: AstrMessageEvent, server_name: str, command: str
    ) -> str:
        """Execute an RCON command for an explicitly selected server.

        If the server name is unknown, call mc_get_bound_servers first to discover
        the servers bound to the current conversation.

        Args:
            server_name (string): The exact configured server name.
            command (string): The command to execute without a leading slash.

        Returns:
            The command result or a permission error.
        """
        return await self._run_rcon(event, server_name, command)

    @filter.custom_filter(QueQiaoPlatformFilter)
    async def on_queqiao(self, event: AstrMessageEvent):
        """Forward Minecraft-originated messages to bound conversations."""
        source_prefix = self._mc_source_prefix(event)
        message_chain = event.chain_result(
            [Plain(text=source_prefix), *event.get_messages()]
        )
        await send_message_by_server(
            event.session.session_id,
            message_chain,
            self.context.send_message,
        )

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_other_platform(self, event: AstrMessageEvent):
        """Forward non-Minecraft messages to bound Minecraft servers."""
        if self._is_plugin_command(event):
            return
        if event.get_platform_name() == "QueQiao":
            return
        source_prefix = self._external_source_prefix(event)
        message_chain = event.chain_result(
            [Plain(text=source_prefix), *event.get_messages()]
        )
        await send_message_by_umo(
            event.unified_msg_origin,
            message_chain,
            QueQiaoMessageEvent.send_message,
            self.bot,
        )

    @staticmethod
    def _is_plugin_command(event: AstrMessageEvent) -> bool:
        """Keep plugin control commands out of the normal MC chat stream."""
        message = event.get_message_str()
        if not isinstance(message, str):
            return False
        command = message.strip().split(maxsplit=1)
        return bool(command and command[0].casefold() in {"/mc", "/sync"})

    @staticmethod
    def _external_source_prefix(event: AstrMessageEvent) -> str:
        """Build a source platform and sender prefix for MC-bound messages."""
        platform = event.get_platform_name() or "未知平台"
        sender = event.get_sender_name() or event.get_sender_id() or "未知用户"
        return f"[{platform}][{sender}] "

    @staticmethod
    def _mc_source_prefix(event: AstrMessageEvent) -> str:
        """Build a display-only prefix for MC messages sent to other platforms."""
        server = event.get_group_id() or event.get_session_id() or "未知服务器"
        player = event.get_sender_name() or event.get_sender_id() or "未知玩家"
        return f"[{server}][{player}] "

    async def _query_status(
        self, event: AstrMessageEvent, server_name: str = ""
    ) -> str:
        """Query and format one server or every server the sender may administer.

        Args:
            event: The requesting message event.
            server_name: Exact server name, or empty for all accessible servers.

        Returns:
            Readable server status or errors.
        """
        if server_name:
            server_names = [server_name]
        else:
            server_names = [
                server.server_name
                for server in self.config_manager.config.sync_config
                if event.is_admin() or event.get_sender_id() in server.administrators
            ]
        if not server_names:
            return "没有可查询的服务器"

        results = await asyncio.gather(
            *(
                self._server_api(event, name, ApiName.GET_STATUS, {})
                for name in server_names
            ),
            return_exceptions=True,
        )
        messages = []
        for name, result in zip(server_names, results):
            if isinstance(result, Exception):
                detail = str(result).strip() or type(result).__name__
                messages.append(
                    detail
                    if detail.startswith(f"服务器 `{name}`")
                    else f"服务器 `{name}`：{detail}"
                )
            else:
                messages.append(self._format_status_result(name, result))
        return "\n\n".join(messages)

    async def _run_llm_server_api(
        self, event: AstrMessageEvent, server_name: str, api: ApiName, data: dict
    ) -> str:
        """Run an LLM-requested server API with normal administrator checks.

        Args:
            event: The requesting message event.
            server_name: Exact target server name.
            api: API operation to perform.
            data: API request body.

        Returns:
            The server response or a readable error.
        """
        try:
            result = await self._server_api(event, server_name, api, data)
        except Exception as exc:
            detail = str(exc).strip() or type(exc).__name__
            logger.warning(
                "MC API request failed for %s (%s): %s", server_name, api.value, detail
            )
            return f"请求失败：{detail}"
        return self._format_api_result(result)

    async def _server_api(
        self, event: AstrMessageEvent, server_name: str, api: ApiName, data: dict
    ):
        """Send a server API request after checking server access.

        Args:
            event: The command event.
            server_name: The exact target server name.
            api: The QueQiao API to call.
            data: API payload.

        Returns:
            The QueQiao API response.
        """
        server = self.config_manager.get_server(server_name)
        if server is None:
            raise ValueError(f"未找到服务器 `{server_name}`")
        if not event.is_admin() and event.get_sender_id() not in server.administrators:
            raise PermissionError("你不是该服务器管理员")
        return await self.bot.send_api(server_name, api, data)

    async def _run_rcon(
        self, event: AstrMessageEvent, server_name: str, command: str
    ) -> str:
        """Validate and execute one RCON command.

        Args:
            event: The event requesting the command.
            server_name: The exact target server name.
            command: The command text.

        Returns:
            A user-facing result string.
        """
        server = self.config_manager.get_server(server_name)
        if server is None:
            return f"未找到服务器 `{server_name}`"
        if not event.is_admin() and event.get_sender_id() not in server.administrators:
            return "你没有权限执行 RCON"
        command = command.strip().lstrip("/")
        if not command:
            return "RCON 命令不能为空"
        if not server.rcon_enabled:
            return f"服务器 `{server_name}` 未启用 RCON"
        if not any(
            item == "*" or command == item or command.startswith(f"{item} ")
            for item in server.rcon_command_whitelist
        ):
            return "该 RCON 命令不在白名单中"
        try:
            result = await self.bot.send_api(
                server_name, ApiName.SEND_RCON_COMMAND, {"command": command}
            )
        except Exception as exc:
            detail = str(exc).strip()
            if not detail and isinstance(exc, ConnectionError):
                detail = f"服务器 `{server_name}` 未连接或连接已断开"
            detail = detail or type(exc).__name__
            logger.warning("RCON request failed for %s: %s", server_name, detail)
            return f"RCON 执行失败: {detail}"
        return self._format_api_result(result)

    @staticmethod
    def _format_api_result(result) -> str:
        """Format a QueQiao response for chat output."""
        if result is None:
            return "请求已发送"
        success = str(getattr(result, "status", "")).casefold() in {
            "ok",
            "success",
        } or getattr(result, "code", 1) in {0, 200}
        message = str(
            getattr(result, "message", "请求成功" if success else "请求失败")
            or ("请求成功" if success else "请求失败"),
        )
        data = getattr(result, "data", None)
        if success and data not in (None, "", {}, []):
            if isinstance(data, (dict, list)):
                return json.dumps(data, ensure_ascii=False, indent=2)
            return str(data).strip() or message
        return message

    @staticmethod
    def _format_status_result(server_name: str, result) -> str:
        """Summarize the useful fields of a QueQiao get_status response.

        Args:
            server_name: Configured server name.
            result: Parsed QueQiao response.

        Returns:
            Readable status text without large payloads such as the favicon.
        """
        data = getattr(result, "data", None)
        success = str(getattr(result, "status", "")).casefold() in {
            "ok",
            "success",
        } or getattr(result, "code", 1) in {0, 200}
        if not success or not isinstance(data, dict) or not data:
            return f"服务器 `{server_name}`：{QueQiaoPlugin._format_api_result(result)}"

        ping = data.get("server_list_ping") or {}
        players = ping.get("players") or {}
        cpu = data.get("cpu_information") or {}
        memory = data.get("memory_information") or {}
        lines = [f"服务器 `{server_name}`", "状态：查询成功"]
        server_type = data.get("server_type")
        version = data.get("server_version")
        if server_type or version:
            lines.append(
                f"类型与版本：{' '.join(str(item) for item in (server_type, version) if item)}"
            )
        if ping:
            lines.append(
                f"服务器列表查询：{'可用' if ping.get('available') else '不可用'}"
            )
            if ping.get("available"):
                if players.get("online") is not None and players.get("max") is not None:
                    lines.append(
                        f"在线玩家：{int(players['online'])}/{int(players['max'])}"
                    )
            elif ping.get("error") or ping.get("reason"):
                lines.append(f"查询原因：{ping.get('error') or ping.get('reason')}")
        if cpu.get("cpu_cores") is not None:
            lines.append(f"CPU 核心：{cpu['cpu_cores']}")
        system_load = cpu.get("system_load")
        if isinstance(system_load, (int, float)) and 0 <= system_load <= 1:
            lines.append(f"系统 CPU 负载：{system_load * 100:.1f}%")
        for key, label in (("jvm_memory", "JVM 内存"), ("physical_memory", "物理内存")):
            values = memory.get(key) or {}
            used = values.get("used")
            total = values.get("max") if key == "jvm_memory" else values.get("total")
            if isinstance(used, (int, float)) and isinstance(total, (int, float)):
                lines.append(f"{label}：{used / 1024**3:.2f}/{total / 1024**3:.2f} GiB")
        return "\n".join(lines)

    async def web_config(self):
        """Read or replace plugin configuration for the Dashboard page."""
        if request.method.upper() == "GET":
            return json_response(self.config_manager.dump_model())
        payload = await request.json(default={})
        if not isinstance(payload, dict):
            return error_response("配置格式必须是对象")
        try:
            self.config_manager.apply_model(payload)
        except Exception as exc:
            return error_response(f"配置保存失败: {exc}")
        return json_response(self.config_manager.dump_model())

    async def web_status(self):
        """Return connection status for the Dashboard page."""
        return json_response(self.bot.get_status())
