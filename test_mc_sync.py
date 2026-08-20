"""Unit tests for MC synchronization configuration and routing."""

import asyncio
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from astrbot_plugin_mc_sync.adapter import dispatch
from astrbot_plugin_mc_sync.filter import ServerAdminFilter
from astrbot_plugin_mc_sync.utils.config import PluginConfig, SyncConfig


class McSyncTests(unittest.TestCase):
    """Verify configuration and routing behavior without network dependencies."""

    def test_server_config_has_independent_feature_flags(self):
        """Each server keeps its own CICode, event, and RCON configuration."""
        config = PluginConfig(
            sync_config=[
                SyncConfig(server_name="alpha", cicode_enabled=True, rcon_enabled=True),
                SyncConfig(server_name="beta", cicode_enabled=False, forward_player_death=False),
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

        with patch.object(dispatch, "ConfigManager", return_value=SimpleNamespace(config=config)):
            result = asyncio.run(dispatch.send_message_by_umo("umo", object(), send_func, object()))

        self.assertTrue(result)
        self.assertEqual(sorted(calls), [("alpha", True), ("beta", False)])

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

    def test_plugin_module_imports_with_llm_tool_registration(self):
        """The plugin module must load successfully under AstrBot's decorators."""
        __import__("astrbot_plugin_mc_sync.main")


if __name__ == "__main__":
    unittest.main()
