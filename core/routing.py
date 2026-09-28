from __future__ import annotations

from dataclasses import dataclass


VOICE_SEND_MODES: tuple[str, ...] = (
    "record_local",
    "record_link",
    "text",
)
FILE_SEND_MODES: tuple[str, ...] = (
    "file_local",
    "file_link",
    "text",
)


@dataclass(frozen=True, slots=True)
class CommandRoute:
    """一次用户命令对应的平台和发送意图。"""

    platform: str | None
    send_modes: tuple[str, ...] | None
    action_name: str


_COMMAND_ROUTES: dict[str, CommandRoute] = {
    "点歌": CommandRoute(None, None, "点歌"),
    "music": CommandRoute(None, None, "点歌"),
    "qq点歌": CommandRoute("qq", None, "点歌"),
    "网易点歌": CommandRoute("netease", None, "点歌"),
    "网易云点歌": CommandRoute("netease", None, "点歌"),
    "下载音乐": CommandRoute(None, FILE_SEND_MODES, "下载"),
    "下载歌曲": CommandRoute(None, FILE_SEND_MODES, "下载"),
    "qq下载": CommandRoute("qq", FILE_SEND_MODES, "下载"),
    "qq音乐下载": CommandRoute("qq", FILE_SEND_MODES, "下载"),
    "网易下载": CommandRoute("netease", FILE_SEND_MODES, "下载"),
    "网易云下载": CommandRoute("netease", FILE_SEND_MODES, "下载"),
}


def resolve_command(command: str, default_platform: str) -> CommandRoute | None:
    """把聊天命令解析为稳定的平台名和一次性发送策略。"""

    route = _COMMAND_ROUTES.get(command.strip().lower())
    if route is None:
        return None
    platform = route.platform or default_platform.strip().lower()
    if platform not in {"qq", "netease"}:
        return None
    return CommandRoute(platform, route.send_modes, route.action_name)


def parse_song_query(raw_query: str) -> tuple[str, int | None]:
    """解析“歌名 [序号]”，不把歌名末尾的非数字误认为序号。"""

    value = raw_query.strip()
    parts = value.rsplit(maxsplit=1)
    if len(parts) == 2 and parts[1].isdigit():
        return parts[0].strip(), int(parts[1])
    return value, None
