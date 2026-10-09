"""Unit tests for MC synchronization configuration and routing."""

import asyncio
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from astrbot_plugin_mc_sync.adapter import dispatch
from astrbot_plugin_mc_sync.adapter.adapter_base import QueQiaoPlatformBase
from astrbot_plugin_mc_sync.adapter.models import QueQiaoResponse
from astrbot_plugin_mc_sync.adapter.queqiao_manager import QueQiaoBridge
from astrbot_plugin_mc_sync.filter import ServerAdminFilter
from astrbot_plugin_mc_sync.utils.config import PluginConfig, SyncConfig


class McSyncTests(unittest.TestCase):
    """Verify configuration and routing behavior without network dependencies."""

    def test_server_config_has_independent_feature_flags(self):
        """Each server keeps its own CICode, event, and RCON configuration."""
        config = PluginConfig(
            sync_config=[
                SyncConfig(server_name="alpha", cicode_enabled=True, rcon_enabled=True),
                SyncConfig(
                    server_name="beta", cicode_enabled=False, forward_player_death=False
                ),
            ],
        )

        self.assertTrue(config.sync_config[0].cicode_enabled)
        self.assertTrue(config.sync_config[0].rcon_enabled)
        self.assertFalse(config.sync_config[1].cicode_enabled)
        self.assertFalse(config.sync_config[1].forward_player_death)

    def test_message_dispatch_uses_each_server_cicode_setting(self):
        """Forwarding one session to two servers preserves per-server CICode settings."""
        config = PluginConfig(
            sync_config=[
                SyncConfig(server_name="alpha", umo_list=["umo"], cicode_enabled=True),
                SyncConfig(server_name="beta", umo_list=["umo"], cicode_enabled=False),
            ],
        )
        calls = []

        async def send_func(bot, chain, server_name, cicode_enabled):
            calls.append((server_name, cicode_enabled))
            return True

        with patch.object(
            dispatch, "ConfigManager", return_value=SimpleNamespace(config=config)
        ):
            result = asyncio.run(
                dispatch.send_message_by_umo("umo", object(), send_func, object())
            )

        self.assertTrue(result)
        self.assertEqual(sorted(calls), [("alpha", True), ("beta", False)])

    def test_session_forwarding_switch_only_controls_outbound_messages(self):
        """Disabled outbound routing leaves server-to-session delivery intact."""
        config = PluginConfig(
            sync_config=[
                SyncConfig(server_name="enabled", umo_list=["umo"]),
                SyncConfig(
                    server_name="disabled",
                    umo_list=["umo"],
                    forward_session_messages=False,
                ),
            ],
        )
        outbound_calls = []
        inbound_calls = []

        async def send_outbound(bot, chain, server_name, cicode_enabled):
            outbound_calls.append(server_name)
            return True

        async def send_inbound(umo, chain):
            inbound_calls.append(umo)
            return True

        with patch.object(
            dispatch, "ConfigManager", return_value=SimpleNamespace(config=config)
        ):
            self.assertTrue(
                asyncio.run(
                    dispatch.send_message_by_umo(
                        "umo", object(), send_outbound, object()
                    )
                )
            )
            self.assertTrue(
                asyncio.run(
                    dispatch.send_message_by_server("disabled", object(), send_inbound)
                )
            )

        self.assertEqual(outbound_calls, ["enabled"])
        self.assertEqual(inbound_calls, ["umo"])

    def test_session_forwarding_defaults_to_enabled_for_existing_config(self):
        """Existing server records preserve their previous forwarding behavior."""
        server = SyncConfig.model_validate(
            {"server_name": "legacy", "umo_list": ["umo"]}
        )
        self.assertTrue(server.forward_session_messages)

    def test_server_admin_filter_accepts_framework_or_server_administrator(self):
        """The command filter grants only framework or matching server administrators."""
        server = SyncConfig(server_name="alpha", administrators=["42"])
        custom_filter = ServerAdminFilter()
        event = SimpleNamespace(
            is_admin=lambda: False,
            get_sender_id=lambda: "42",
            get_message_str=lambda: "mc status alpha",
        )
        denied_event = SimpleNamespace(
            is_admin=lambda: False,
            get_sender_id=lambda: "7",
            get_message_str=lambda: "mc status alpha",
        )

        with patch(
            "astrbot_plugin_mc_sync.filter.ConfigManager",
            return_value=SimpleNamespace(get_server=lambda _: server),
        ):
            self.assertTrue(custom_filter.filter(event, object()))
            self.assertFalse(custom_filter.filter(denied_event, object()))

    def test_status_without_name_allows_server_administrator(self):
        """Server administrators can query their accessible servers together."""
        custom_filter = ServerAdminFilter()
        config = PluginConfig(
            sync_config=[SyncConfig(server_name="alpha", administrators=["42"])]
        )
        event = SimpleNamespace(
            is_admin=lambda: False,
            get_sender_id=lambda: "42",
            get_message_str=lambda: "#mc status",
        )
        with patch(
            "astrbot_plugin_mc_sync.filter.ConfigManager",
            return_value=SimpleNamespace(config=config),
        ):
            self.assertTrue(custom_filter.filter(event, object()))

    def test_plugin_module_imports_with_llm_tool_registration(self):
        """The plugin module must load successfully under AstrBot's decorators."""
        __import__("astrbot_plugin_mc_sync.main")

    def test_rcon_response_accepts_plain_text_data(self):
        """RCON responses may return command output as a string."""
        response = QueQiaoResponse(
            code=0,
            api="send_rcon_command",
            post_type="response",
            data="Gave 64 [Diamond] to ErZaozi\n",
        )
        self.assertIn("Diamond", response.data)

    def test_disconnected_status_returns_message_without_handler_error(self):
        """A disconnected server produces a readable reply to the status command."""
        from astrbot_plugin_mc_sync.main import QueQiaoPlugin

        async def run_status():
            bridge = object.__new__(QueQiaoBridge)
            bridge.connections = {}
            plugin = object.__new__(QueQiaoPlugin)
            plugin.config_manager = SimpleNamespace(
                get_server=lambda name: SyncConfig(server_name=name)
            )
            plugin.bot = bridge
            event = SimpleNamespace(
                is_admin=lambda: True,
                plain_result=lambda message: message,
            )
            return [message async for message in plugin.mc_status(event, "Server")]

        self.assertEqual(
            asyncio.run(run_status()),
            ["服务器 `Server` 未连接或连接已断开"],
        )

    def test_rcon_reports_disconnected_server_when_error_has_no_text(self):
        """An empty transport exception still produces a useful RCON result."""
        from astrbot_plugin_mc_sync.main import QueQiaoPlugin

        async def send_api(*args):
            raise ConnectionError()

        plugin = object.__new__(QueQiaoPlugin)
        plugin.config_manager = SimpleNamespace(
            get_server=lambda name: SyncConfig(
                server_name=name,
                rcon_enabled=True,
                rcon_command_whitelist=["list"],
            )
        )
        plugin.bot = SimpleNamespace(send_api=send_api)
        event = SimpleNamespace(is_admin=lambda: True)

        result = asyncio.run(plugin._run_rcon(event, "Server", "list"))
        self.assertEqual(result, "RCON 执行失败: 服务器 `Server` 未连接或连接已断开")

    def test_connection_lost_during_api_send_has_server_context(self):
        """A closed connection during send is reported as a disconnect."""
        from astrbot_plugin_mc_sync.adapter.models import ApiName

        class DisconnectedSocket:
            async def send(self, payload):
                raise ConnectionError()

        bridge = object.__new__(QueQiaoBridge)
        bridge.connections = {"Server": DisconnectedSocket()}
        bridge._pending = {}

        with self.assertRaisesRegex(ConnectionError, "Server.*连接已断开"):
            asyncio.run(bridge.send_api("Server", ApiName.GET_STATUS, {}))
        self.assertFalse(bridge._pending)

    def test_llm_bound_servers_are_scoped_to_current_conversation(self):
        """Discovery returns all and only servers bound to the requesting session."""
        from astrbot_plugin_mc_sync.main import QueQiaoPlugin

        plugin = object.__new__(QueQiaoPlugin)
        plugin.config_manager = SimpleNamespace(
            config=PluginConfig(
                sync_config=[
                    SyncConfig(server_name="生存服", umo_list=["current"]),
                    SyncConfig(server_name="creative", umo_list=["current", "other"]),
                    SyncConfig(server_name="private", umo_list=["other"]),
                ]
            ),
        )
        for origin, expected in [
            ("current", ["生存服", "creative"]),
            ("other", ["creative", "private"]),
            ("unbound", None),
        ]:
            with self.subTest(origin=origin):
                result = asyncio.run(
                    plugin.llm_mc_get_bound_servers(
                        SimpleNamespace(unified_msg_origin=origin),
                    )
                )
                if expected is None:
                    self.assertIn("未绑定", result)
                else:
                    self.assertEqual(json.loads(result), expected)

    def test_callback_accepts_connection_context_keywords(self):
        """Callback routing metadata must not break response futures."""

        async def run_callback():
            bridge = object.__new__(QueQiaoBridge)
            future = asyncio.get_running_loop().create_future()
            bridge._pending = {"echo-1": future}
            response = QueQiaoResponse(
                code=0,
                api="send_rcon_command",
                post_type="response",
                echo="echo-1",
                data="ok",
            )
            await bridge.on_callback(response, server_name="Server", is_reverse=False)
            return future.result()

        self.assertEqual(asyncio.run(run_callback()).echo, "echo-1")

    def test_notice_text_is_readable_and_does_not_duplicate_player_name(self):
        """Achievement titles are flattened and death names are not duplicated."""
        achievement = {
            "title": {
                "key": "advancements.nether.netherite_armor.title",
                "args": [],
                "text": "Cover Me in Debris",
            },
            "description": {
                "text": "Get a full suit of Netherite armor",
            },
            "frame": "challenge",
        }
        self.assertEqual(
            QueQiaoPlatformBase._read_achievement_title(achievement),
            "Cover Me in Debris",
        )
        self.assertEqual(
            QueQiaoPlatformBase._prefix_player_name("ErZaozi", "ErZaozi was killed"),
            "ErZaozi was killed",
        )
        self.assertEqual(
            QueQiaoPlatformBase._prefix_player_name("ErZaozi", "was killed"),
            "ErZaozi was killed",
        )
        self.assertEqual(
            QueQiaoPlatformBase._without_player_name("ErZaozi", "ErZaozi was killed"),
            "was killed",
        )

    def test_api_result_prefers_success_data_over_generic_message(self):
        """Status and RCON commands should show useful response data."""
        from astrbot_plugin_mc_sync.main import QueQiaoPlugin

        status_result = SimpleNamespace(
            status="ok",
            code=0,
            message="success",
            data={"players": 2, "max_players": 20},
        )
        rcon_result = SimpleNamespace(
            status="ok",
            code=0,
            message="success",
            data="Gave 64 [Diamond] to ErZaozi\n",
        )
        self.assertIn('"players": 2', QueQiaoPlugin._format_api_result(status_result))
        self.assertEqual(
            QueQiaoPlugin._format_api_result(rcon_result),
            "Gave 64 [Diamond] to ErZaozi",
        )

    def test_status_summarizes_success_200_without_favicon(self):
        """A QueQiao HTTP-style success code exposes useful status fields."""
        from astrbot_plugin_mc_sync.main import QueQiaoPlugin

        response = QueQiaoResponse(
            code=200,
            api="get_status",
            post_type="response",
            status="SUCCESS",
            message="success",
            data={
                "server_type": "forge",
                "server_version": "1.21",
                "server_list_ping": {
                    "available": True,
                    "players": {"online": 0.0, "max": 20.0},
                    "favicon": "data:image/png;base64,...",
                },
                "cpu_information": {"cpu_cores": 16},
                "memory_information": {
                    "jvm_memory": {"used": 390560352, "max": 8573157376},
                },
            },
        )
        result = QueQiaoPlugin._format_status_result("Server", response)
        self.assertIn("forge 1.21", result)
        self.assertIn("在线玩家：0/20", result)
        self.assertIn("JVM 内存", result)
        self.assertNotIn("favicon", result)
        self.assertNotIn("success", result)

    def test_status_without_name_queries_only_authorized_servers(self):
        """Bulk status excludes servers outside a server admin's scope."""
        from astrbot_plugin_mc_sync.main import QueQiaoPlugin

        calls = []

        async def send_api(name, api, data):
            calls.append(name)
            return QueQiaoResponse(
                code=200,
                api="get_status",
                post_type="response",
                status="SUCCESS",
                data={"server_version": "1.21"},
            )

        plugin = object.__new__(QueQiaoPlugin)
        config = PluginConfig(
            sync_config=[
                SyncConfig(server_name="alpha", administrators=["42"]),
                SyncConfig(server_name="beta", administrators=["7"]),
            ]
        )
        plugin.config_manager = SimpleNamespace(
            config=config,
            get_server=lambda name: next(
                server for server in config.sync_config if server.server_name == name
            ),
        )
        plugin.bot = SimpleNamespace(send_api=send_api)
        event = SimpleNamespace(
            is_admin=lambda: False,
            get_sender_id=lambda: "42",
            plain_result=lambda message: message,
        )

        async def run_status():
            return [message async for message in plugin.mc_status(event)]

        result = asyncio.run(run_status())[0]
        self.assertEqual(calls, ["alpha"])
        self.assertIn("alpha", result)
        self.assertNotIn("beta", result)

        calls.clear()
        event.is_admin = lambda: True
        all_result = asyncio.run(run_status())[0]
        self.assertEqual(calls, ["alpha", "beta"])
        self.assertIn("alpha", all_result)
        self.assertIn("beta", all_result)

    def test_llm_server_tools_share_command_permissions_and_payloads(self):
        """LLM action tools use the same server checks and API payloads as commands."""
        from astrbot_plugin_mc_sync.adapter.models import ApiName
        from astrbot_plugin_mc_sync.main import QueQiaoPlugin

        calls = []

        async def send_api(name, api, data):
            calls.append((name, api, data))
            return QueQiaoResponse(
                code=200,
                api=api.value,
                post_type="response",
                status="SUCCESS",
                message="success",
            )

        plugin = object.__new__(QueQiaoPlugin)
        plugin.config_manager = SimpleNamespace(
            get_server=lambda name: (
                SyncConfig(server_name=name, administrators=["42"])
                if name == "alpha"
                else None
            ),
        )
        plugin.bot = SimpleNamespace(send_api=send_api)
        allowed = SimpleNamespace(is_admin=lambda: False, get_sender_id=lambda: "42")
        denied = SimpleNamespace(is_admin=lambda: False, get_sender_id=lambda: "7")

        async def run_tools():
            return [
                await plugin.llm_mc_broadcast(allowed, "alpha", "hello"),
                await plugin.llm_mc_private(allowed, "alpha", "player", "secret"),
                await plugin.llm_mc_title(allowed, "alpha", "title"),
                await plugin.llm_mc_actionbar(allowed, "alpha", "bar"),
                await plugin.llm_mc_broadcast(denied, "alpha", "blocked"),
            ]

        results = asyncio.run(run_tools())
        self.assertEqual(results[:4], ["success"] * 4)
        self.assertIn("不是该服务器管理员", results[4])
        self.assertEqual(
            calls,
            [
                ("alpha", ApiName.BROADCAST, {"message": "hello"}),
                (
                    "alpha",
                    ApiName.SEND_PRIVATE_MSG,
                    {"user_id": "player", "message": "secret"},
                ),
                ("alpha", ApiName.SEND_TITLE, {"message": "title"}),
                ("alpha", ApiName.SEND_ACTIONBAR, {"message": "bar"}),
            ],
        )

    def test_llm_status_uses_formatted_status_result(self):
        """The status tool returns the same readable summary as the chat command."""
        from astrbot_plugin_mc_sync.main import QueQiaoPlugin

        async def send_api(name, api, data):
            return QueQiaoResponse(
                code=200,
                api="get_status",
                post_type="response",
                status="SUCCESS",
                data={"server_version": "1.21"},
            )

        plugin = object.__new__(QueQiaoPlugin)
        plugin.config_manager = SimpleNamespace(
            get_server=lambda name: SyncConfig(server_name=name),
        )
        plugin.bot = SimpleNamespace(send_api=send_api)
        event = SimpleNamespace(is_admin=lambda: True)

        result = asyncio.run(plugin.llm_mc_status(event, "alpha"))
        self.assertIn("服务器 `alpha`", result)
        self.assertIn("1.21", result)

    def test_mc_source_prefix_contains_server_and_player(self):
        """MC-originated messages use a consistent server/player prefix."""
        from astrbot_plugin_mc_sync.main import QueQiaoPlugin

        event = SimpleNamespace(
            get_group_id=lambda: "Server",
            get_session_id=lambda: "Server",
            get_sender_name=lambda: "ErZaozi",
            get_sender_id=lambda: "uuid",
        )
        self.assertEqual(
            QueQiaoPlugin._mc_source_prefix(event),
            "[Server][ErZaozi] ",
        )

    def test_mc_framework_message_keeps_raw_command_text(self):
        """Framework parsing receives raw MC text without the display prefix."""

        class TestAdapter(QueQiaoPlatformBase):
            def meta(self):
                return None

        adapter = object.__new__(TestAdapter)
        message = adapter._convert_queqiao_message(
            {
                "raw_message": "#tp一下我",
                "player": {"uuid": "uuid", "nickname": "ErZaozi"},
                "message_id": "message-1",
            },
            server_name="Server",
        )
        self.assertEqual(message.message_str, "#tp一下我")
        self.assertEqual(message.message[0].text, "#tp一下我")

    def test_external_source_prefix_contains_platform_and_sender(self):
        """Messages sent to MC identify their source platform and sender."""
        from astrbot_plugin_mc_sync.main import QueQiaoPlugin

        event = SimpleNamespace(
            get_platform_name=lambda: "aiocqhttp",
            get_sender_name=lambda: "Alice",
            get_sender_id=lambda: "10001",
        )
        self.assertEqual(
            QueQiaoPlugin._external_source_prefix(event),
            "[aiocqhttp][Alice] ",
        )

    def test_plugin_commands_are_not_forwarded_as_chat(self):
        """Control commands must stop at AstrBot and not be sent to Minecraft."""
        from astrbot_plugin_mc_sync.main import QueQiaoPlugin

        self.assertTrue(
            QueQiaoPlugin._is_plugin_command(
                SimpleNamespace(get_message_str=lambda: "/mc broadcast Server hello"),
            ),
        )
        self.assertTrue(
            QueQiaoPlugin._is_plugin_command(
                SimpleNamespace(get_message_str=lambda: "  /sync on Server"),
            ),
        )
        self.assertFalse(
            QueQiaoPlugin._is_plugin_command(
                SimpleNamespace(get_message_str=lambda: "hello /mc"),
            ),
        )


if __name__ == "__main__":
    unittest.main()
