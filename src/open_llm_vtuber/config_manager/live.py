from pydantic import Field
from typing import Dict, ClassVar, List
from .i18n import I18nMixin, Description


class BiliBiliLiveConfig(I18nMixin):
    """Configuration for BiliBili Live platform."""

    room_ids: List[int] = Field([], alias="room_ids")
    sessdata: str = Field("", alias="sessdata")

    DESCRIPTIONS: ClassVar[Dict[str, Description]] = {
        "room_ids": Description(
            en="List of BiliBili live room IDs to monitor", zh="要监控的B站直播间ID列表"
        ),
        "sessdata": Description(
            en="SESSDATA cookie value for authenticated requests (optional)",
            zh="用于认证请求的SESSDATA cookie值（可选）",
        ),
    }


class ChzzkLiveConfig(I18nMixin):
    """Configuration for CHZZK live chat sampling."""

    enabled: bool = Field(False, alias="enabled")
    channel_id: str = Field("", alias="channel_id")
    send_interval_sec: float = Field(20.0, alias="send_interval_sec")
    reconnect_interval_sec: float = Field(15.0, alias="reconnect_interval_sec")
    recent_pool_size: int = Field(15, alias="recent_pool_size")
    min_message_length: int = Field(2, alias="min_message_length")
    max_message_length: int = Field(120, alias="max_message_length")
    ignore_while_conversation_active: bool = Field(
        True, alias="ignore_while_conversation_active"
    )


class LiveConfig(I18nMixin):
    """Configuration for live streaming platforms integration."""

    bilibili_live: BiliBiliLiveConfig = Field(
        BiliBiliLiveConfig(), alias="bilibili_live"
    )
    chzzk_live: ChzzkLiveConfig = Field(ChzzkLiveConfig(), alias="chzzk_live")

    DESCRIPTIONS: ClassVar[Dict[str, Description]] = {
        "bilibili_live": Description(
            en="Configuration for BiliBili Live platform", zh="B站直播平台配置"
        ),
    }
