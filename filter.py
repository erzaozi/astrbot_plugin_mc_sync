from astrbot.core.star.filter.custom_filter import CustomFilter, AstrMessageEvent, AstrBotConfig

class QueQiaoPlatformFilter(CustomFilter):
    """只允许来自 'queqiao' 平台的消息通过"""

    def __init__(self, raise_error: bool = True):
        # 调用父类构造函数，传入 raise_error
        super().__init__(raise_error)

    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        # 返回 True 表示通过，False 表示被过滤
        return event.platform_meta.name == 'QueQiao'