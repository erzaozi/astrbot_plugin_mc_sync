from pydantic import BaseModel, Field
from typing import Any, Optional
from enum import Enum

class ServerConfig(BaseModel):
    """插件服务器配置（鹊桥连接 + 服务器列表）"""
    ws_host: str = Field("0.0.0.0", description="反向 WebSocket 服务器监听地址")
    ws_path: str = Field("/minecraft/ws", description="反向 WebSocket 路由")
    ws_port: int = Field(25566, ge=1, le=65535, description="反向 WebSocket 端口")
    ws_auth: str = Field("", description="反向 WebSocket 鉴权密码")

class ClientConfig(BaseModel):
    """单个 MC 服务器配置。"""
    server_name: str = Field("", description="服务器唯一标识")
    ws_url: str = Field("", description="完整 WebSocket URL")
    ws_auth: str = Field("", description="鉴权密码 (accessToken)")
    ws_max_attempts: int = Field(-1, description="最大重连次数，0=不重连，-1=持续重连")

class ApiName(Enum):
    BROADCAST = "broadcast"
    SEND_PRIVATE_MSG = "send_private_msg"
    SEND_TITLE = "send_title"
    SEND_ACTIONBAR = "send_actionbar"
    SEND_RCON_COMMAND = "send_rcon_command"
    GET_STATUS = "get_status"

class QueQiaoRequest(BaseModel):
    """发送到鹊桥的请求"""
    api: ApiName
    data: Optional[dict] = Field(default_factory=dict, description="请求数据")
    echo: Optional[str] = Field(default="", description="回显标识")

class QueQiaoResponse(BaseModel):
    """鹊桥返回的响应"""
    code: int
    api: str
    post_type: str
    status: str = ""
    message: str = ""
    echo: str = ""
    # API responses may contain structured data or plain text, such as RCON output.
    data: Any = Field(default_factory=dict)

class PlayerChatEvent(BaseModel):
    """玩家加入事件"""
    timestamp: int
    post_type: str = "message"
    event_name: str = "PlayerChatEvent"
    server_name: str
    server_version: str
    server_type: str
    sub_type: str = "player_chat"
    message_id: str
    raw_message: str
    player: dict
    message: str

class PlayerCommandEvent(BaseModel):
    """玩家命令事件"""
    timestamp: int
    post_type: str = "message"
    event_name: str = "PlayerCommandEvent"
    server_name: str
    server_version: str
    server_type: str
    sub_type: str = "player_command"
    message_id: str
    raw_message: str
    player: dict
    command: str

class PlayerJoinEvent(BaseModel):
    """玩家加入事件"""
    timestamp: int
    post_type: str = "notice"
    event_name: str = "PlayerJoinEvent"
    server_name: str
    server_version: str
    server_type: str
    sub_type: str = "player_join"
    player: dict

class PlayerQuitEvent(BaseModel):
    """玩家聊天事件"""
    timestamp: int
    post_type: str = "notice"
    event_name: str = "PlayerQuitEvent"
    server_name: str
    server_version: str
    server_type: str
    sub_type: str = "player_quit"
    player: dict

class PlayerDeathEvent(BaseModel):
    """玩家死亡事件"""
    timestamp: int
    post_type: str = "notice"
    event_name: str = "PlayerDeathEvent"
    server_name: str
    server_version: str
    server_type: str
    sub_type: str = "player_death"
    player: dict
    death: dict

class PlayerAchievementEvent(BaseModel):
    """玩家进度事件"""
    timestamp: int
    post_type: str = "notice"
    event_name: str = "PlayerAchievementEvent"
    server_name: str
    server_version: str
    server_type: str
    sub_type: str = "player_achievement"
    player: dict
    achievement: dict
