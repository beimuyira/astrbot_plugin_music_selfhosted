from dataclasses import dataclass
from pathlib import PurePosixPath
from urllib.parse import unquote, urlparse

_AUDIO_FORMAT_ALIASES = {
    "aac": "aac",
    "flac": "flac",
    "m4a": "m4a",
    "mp3": "mp3",
    "mpeg": "mp3",
    "mp4": "mp4",
    "oga": "ogg",
    "ogg": "ogg",
    "opus": "opus",
    "wav": "wav",
    "wave": "wav",
    "x-flac": "flac",
    "x-m4a": "m4a",
    "x-wav": "wav",
}


def normalize_audio_format(value: object) -> str | None:
    """把 API 字段、扩展名或 MIME 子类型规范成安全的音频后缀。"""
    if not isinstance(value, str):
        return None
    candidate = value.strip().lower().lstrip(".")
    if "/" in candidate:
        candidate = candidate.split("/", 1)[1]
    candidate = candidate.split(";", 1)[0]
    return _AUDIO_FORMAT_ALIASES.get(candidate)


def infer_audio_format_from_url(url: str | None) -> str | None:
    if not url:
        return None
    path = unquote(urlparse(url).path)
    return normalize_audio_format(PurePosixPath(path).suffix)


def infer_audio_format_from_content_type(value: str | None) -> str | None:
    if not value:
        return None
    media_type = value.split(";", 1)[0].strip().lower()
    aliases = {
        "application/ogg": "ogg",
        "audio/mp4": "m4a",
        "video/mp4": "mp4",
    }
    return aliases.get(media_type) or normalize_audio_format(media_type)


@dataclass(slots=True)
class Song:
    id: str | int
    """歌曲ID"""

    source: str | None = None
    """歌曲来源平台标识"""

    mid: str | None = None
    """平台使用的媒体 MID（QQ 音乐）"""

    media_mid: str | None = None
    """音频文件 MID（QQ 音乐）"""

    song_type: int | None = None
    """平台歌曲类型（QQ 音乐）"""

    name: str | None = None
    """歌曲原始名称"""

    artists: str | None = None
    """歌手/艺人"""

    duration: int | None = None
    """时长（毫秒）"""

    title: str | None = None
    """可补充的显示名称"""

    author: str | None = None
    """可补充的作者/歌手名"""

    cover_url: str | None = None
    """封面图 URL"""

    audio_url: str | None = None
    """音频播放 URL"""

    audio_format: str | None = None
    """API 返回或从音频地址识别出的真实编码格式。"""

    audio_quality: str | None = None
    """实际取得的音质级别，可能低于配置的请求音质。"""

    path: str | None = None
    """音频文件路径(预留给持久化)"""

    lyrics: str | None = None
    """歌词"""

    comments: list | None = None
    """评论列表"""

    note: str | None = None
    """备注，例如来源或额外信息"""

    def to_lines(self) -> str:
        """将 Song 信息整理成多行文本"""
        lines = [
            f"ID: {self.id}",
            f"名称: {self.name or self.title or '未知'}",
            f"艺人: {self.artists or self.author or '未知'}",
        ]
        if self.duration:
            mins, secs = divmod(self.duration // 1000, 60)
            lines.append(f"时长: {mins}:{secs:02d}")
        if self.audio_url:
            lines.append(f"播放链接: {self.audio_url}")
        if self.cover_url:
            lines.append(f"封面: {self.cover_url}")
        if self.note:
            lines.append(f"备注: {self.note}")
        return "\n".join(lines)



@dataclass(slots=True)
class Platform:
    """平台信息"""

    name: str
    """ 平台名称 """
    display_name: str
    """ 平台显示名称 """
    keywords: list[str]
    """ 平台关键词 """
