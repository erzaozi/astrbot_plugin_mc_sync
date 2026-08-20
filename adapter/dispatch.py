import asyncio
from typing import Callable, Awaitable, Any
from astrbot.api.event import MessageChain
from astrbot.api import logger
from . import QueQiaoBridge
from ..utils.config import ConfigManager

async def send_message_by_server(
        server_name: str,
        message_chain: MessageChain,
        send_func: Callable[[str, MessageChain], Awaitable[bool | None]]
) -> bool:
    """
    向指定服务器绑定的所有 umo 并发发送消息。

    Args:
        server_name: 服务器名称
        message_chain: 要发送的消息链
        send_func: 发送函数，签名为 async def send_func(umo: str, msg: MessageChain) -> bool
                   (返回 True 表示成功，False 或 None 表示失败)

    Returns:
        bool: 所有会话都发送成功返回 True，否则 False
    """
    # 获取配置
    config = ConfigManager().config
    sync_list = config.sync_config
    target = next((s for s in sync_list if s.server_name == server_name), None)
    if target is None:
        logger.warning(f"未找到服务器 {server_name} 的同步配置")
        return False

    umo_list = target.umo_list
    if not umo_list:
        logger.warning(f"服务器 {server_name} 没有绑定任何会话")
        return False

    # 并发发送，直接使用传入的 send_func
    tasks = [send_func(umo, message_chain) for umo in umo_list]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 检查结果
    all_success = True
    for umo, result in zip(umo_list, results):
        if isinstance(result, Exception):
            logger.error(f"向 {umo} 发送消息时异常: {result}")
            all_success = False
        elif result is False or result is None:
            logger.error(f"向 {umo} 发送消息失败（返回 False/None）")
            all_success = False
    return all_success

async def send_message_by_umo(
        umo: str,
        message_chain: MessageChain,
        send_func: Callable[..., Awaitable[bool | None]],
        bot: QueQiaoBridge,
) -> bool:
    config = ConfigManager().config
    sync_list = config.sync_config
    cicode_enabled = config.cicode_enabled
    target = [s.server_name for s in sync_list if umo in s.umo_list]
    if target is None:
        return False

    tasks = [send_func(
        bot,
        message_chain,
        server_name,
        cicode_enabled
    ) for server_name in target]
    await asyncio.gather(*tasks, return_exceptions=True)

    return True