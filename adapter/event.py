from astrbot.api.event import AstrMessageEvent, MessageChain
from .queqiao_manager import QueQiaoBridge
from astrbot.api.message_components import (
    Node,
    Nodes,
    At,
    BaseMessageComponent,
    File,
    Image,
    Plain,
    Record,
    Video,
)

class QueQiaoMessageEvent(AstrMessageEvent):
    def __init__(
        self,
        message_str,
        message_obj,
        platform_meta,
        session_id,
        bot: QueQiaoBridge,
        cicode_enabled: bool = True,
    ) -> None:
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self.cicode_enabled = cicode_enabled
        self.bot = bot

    async def send(self, message_chain: MessageChain) -> None:
        await self.send_message(
            bot=self.bot,
            message_chain=message_chain,
            session_id=self.session_id,
            cicode_enabled=self.cicode_enabled
        )


    @classmethod
    async def send_message(
        cls,
        bot: QueQiaoBridge,
        message_chain: MessageChain,
        session_id: str,
        cicode_enabled: bool = True
    ):
        converted_messages, collected_uuids = cls._convert_astr_message(
            message_chain,
            cicode_enabled,
            bot
        )
        for msg_parts in converted_messages:
            await bot.broadcast(session_id, {
                "message": msg_parts
            })

    @classmethod
    def _convert_astr_message(
            cls,
            message_chain: MessageChain,
            cicode_enabled: bool,
            bot: QueQiaoBridge
    ) -> tuple[list[list[dict]], list[str]]:
        messages: list[list[dict]] = []
        other_segments: list[BaseMessageComponent] = []
        collected_uuids: set[str] = set()

        for seg in message_chain.chain:
            if isinstance(seg, Nodes):
                if other_segments:
                    converted = [
                        cls._from_segment_to_dict(s, cicode_enabled, bot, collected_uuids)
                        for s in other_segments
                    ]
                    converted = [d for d in converted if d is not None]
                    if converted:
                        messages.append(converted)
                    other_segments = []
                for node in seg.nodes:
                    node_dicts = [
                        cls._from_segment_to_dict(comp, cicode_enabled, bot, collected_uuids)
                        for comp in node.content
                    ]
                    node_dicts = [d for d in node_dicts if d is not None]
                    if node_dicts:
                        messages.append(node_dicts)
            elif isinstance(seg, Node):
                if other_segments:
                    converted = [
                        cls._from_segment_to_dict(s, cicode_enabled, bot, collected_uuids)
                        for s in other_segments
                    ]
                    converted = [d for d in converted if d is not None]
                    if converted:
                        messages.append(converted)
                    other_segments = []
                node_dicts = [
                    cls._from_segment_to_dict(comp, cicode_enabled, bot, collected_uuids)
                    for comp in seg.content
                ]
                node_dicts = [d for d in node_dicts if d is not None]
                if node_dicts:
                    messages.append(node_dicts)
            else:
                other_segments.append(seg)

        if other_segments:
            converted = [
                cls._from_segment_to_dict(s, cicode_enabled, bot, collected_uuids)
                for s in other_segments
            ]
            converted = [d for d in converted if d is not None]
            if converted:
                messages.append(converted)

        return messages, list(collected_uuids)

    @classmethod
    def _from_segment_to_dict(
            cls,
            segment: BaseMessageComponent,
            cicode_enabled: bool,
            bot: QueQiaoBridge,
            collected_uuids: set[str]
    ) -> dict | None:
        if isinstance(segment, Plain):
            return {
                "text": segment.text,  # 注意原代码有 "text:" 可能是笔误，我们修正为 "text"
                "color": "white",
            }
        if isinstance(segment, Image):
            url = getattr(segment, 'url', None) or getattr(segment, 'file', None)
            if url:
                if cicode_enabled:
                    return {
                        "text": f"[[CICode, url={url}]]",
                    }
                else:
                    return {
                        "text": "[图片]",
                        "color": "yellow",
                        "bold": True,
                        "hoverEvent": {
                            "action": "show_text",
                            "value": url
                        },
                        "clickEvent": {
                            "action": "open_url",
                            "value": url
                        }
                    }
        if isinstance(segment, At):
            uuid = getattr(segment, 'qq', None)
            if not uuid:
                 return None
            cached_name = bot.get_player_name_by_uuid(uuid)
            if cached_name is not None:
                collected_uuids.add(uuid)
                return {
                    "text": f"@{cached_name}",
                    "color": "gold",
                }
            else:
                name = getattr(segment, 'name', None)
                if name:
                    return {
                        "text": f"@{name}",
                        "color": "white",
                    }
                else:
                    return None
        if isinstance(segment, Record):
            return {
                "text": "[音频]",
                "color": "yellow",
                "bold": True,
                "hoverEvent": {
                    "action": "show_text",
                    "value": segment.text if segment.text else segment.file
                },
                "clickEvent": {
                    "action": "open_url",
                    "value": segment.url
                }
            }
        if isinstance(segment, File):
            return {
                "text": f"[文件:{segment.name}]",
                "color": "yellow",
                "bold": True,
                "hoverEvent": {
                    "action": "show_text",
                    "value": segment.url
                },
                "clickEvent": {
                    "action": "open_url",
                    "value": segment.url
                }
            }
        if isinstance(segment, Video):
            return {
                "text": f"[视频:{segment}]",
                "color": "yellow",
                "bold": True,
                "hoverEvent": {
                    "action": "show_text",
                    "value": segment.url
                },
                "clickEvent": {
                    "action": "open_url",
                    "value": segment.url
                }
            }
        return segment.toDict()
