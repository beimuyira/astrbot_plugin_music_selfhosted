from __future__ import annotations

import time
from typing import Any, ClassVar

from astrbot.api import logger

from ..config import PluginConfig
from ..model import (
    Platform,
    Song,
    infer_audio_format_from_url,
    normalize_audio_format,
)
from .base import BaseMusicPlayer


NCM_QUALITY_FALLBACKS = {
    "lossless": ["lossless", "exhigh", "higher", "standard"],
    "exhigh": ["exhigh", "higher", "standard"],
    "higher": ["higher", "standard"],
    "standard": ["standard"],
}


class NetEaseMusicPlayer(BaseMusicPlayer):
    """NeteaseCloudMusicApi Enhanced 私有服务适配器。"""

    platform: ClassVar[Platform] = Platform(
        name="netease",
        display_name="网易云音乐",
        keywords=["网易点歌", "网易云点歌"],
    )

    def __init__(self, config: PluginConfig):
        super().__init__(config)
        self.base_url = config.netease_api_base_url.rstrip("/")

    def _params(self, **params: Any) -> dict[str, Any]:
        # Enhanced 默认会缓存 GET 响应两分钟。登录态刚更新时，旧的试听
        # 地址可能继续命中缓存，因此所有请求都带独立时间戳。
        params["timestamp"] = time.time_ns() // 1_000_000
        return params

    def _cookie(self) -> str:
        value = str(self.cfg.netease_cookie or "").strip()
        if value and "=" not in value:
            return f"MUSIC_U={value}"
        return value

    def _headers(self, *, use_plugin_cookie: bool) -> dict[str, str]:
        headers = dict(self.HEADERS)
        cookie = self._cookie()
        if use_plugin_cookie and cookie:
            # Cookie 放在请求头中，避免出现在 URL、反向代理日志和 API 日志里。
            headers["Cookie"] = cookie
        return headers

    def _quality_chain(self) -> list[str]:
        quality = str(self.cfg.netease_quality or "standard").strip().lower()
        if quality not in NCM_QUALITY_FALLBACKS:
            logger.warning(f"未知网易云音质配置 {quality!r}，已回退到 standard")
            quality = "standard"
        if not self.cfg.quality_fallback:
            return [quality]
        return NCM_QUALITY_FALLBACKS[quality]

    @staticmethod
    def _artists(item: dict[str, Any]) -> str:
        raw = item.get("ar") or item.get("artists") or []
        if not isinstance(raw, list):
            return "未知歌手"
        names = [
            str(artist.get("name"))
            for artist in raw
            if isinstance(artist, dict) and artist.get("name")
        ]
        return "、".join(names) or "未知歌手"

    @staticmethod
    def _cover(item: dict[str, Any]) -> str | None:
        album = item.get("al") or item.get("album")
        if not isinstance(album, dict):
            return None
        value = album.get("picUrl") or album.get("pic_url")
        return str(value) if value else None

    async def _search(self, path: str, keyword: str, limit: int) -> Any:
        return await self._request(
            f"{self.base_url}{path}",
            params=self._params(keywords=keyword, limit=limit, type=1, offset=0),
        )

    async def fetch_songs(
        self, keyword: str, limit: int = 5, extra: str | None = None
    ) -> list[Song]:
        result = await self._search("/cloudsearch", keyword, limit)
        raw_songs = (
            result.get("result", {}).get("songs")
            if isinstance(result, dict)
            else None
        )
        if not isinstance(raw_songs, list):
            result = await self._search("/search", keyword, limit)
            raw_songs = (
                result.get("result", {}).get("songs")
                if isinstance(result, dict)
                else None
            )
        if not isinstance(raw_songs, list):
            logger.error(f"网易云搜索返回结构异常: {result}")
            return []

        songs: list[Song] = []
        for item in raw_songs[:limit]:
            if not isinstance(item, dict) or item.get("id") is None:
                continue
            duration = item.get("dt") or item.get("duration")
            songs.append(
                Song(
                    id=item["id"],
                    source="netease",
                    name=str(item.get("name") or "未知歌曲"),
                    artists=self._artists(item),
                    duration=int(duration)
                    if isinstance(duration, (int, float))
                    else None,
                    cover_url=self._cover(item),
                )
            )
        return songs

    async def _fetch_url_with_auth(
        self,
        path: str,
        song: Song,
        *,
        level: str | None,
        use_plugin_cookie: bool,
    ) -> Any:
        params: dict[str, Any] = {"id": song.id}
        if level:
            params["level"] = level
        return await self._request(
            f"{self.base_url}{path}",
            params=self._params(**params),
            headers=self._headers(use_plugin_cookie=use_plugin_cookie),
        )

    @staticmethod
    def _first_info(result: Any) -> dict[str, Any] | None:
        data = result.get("data") if isinstance(result, dict) else None
        first = data[0] if isinstance(data, list) and data else None
        return first if isinstance(first, dict) else None

    @staticmethod
    def _is_trial(info: dict[str, Any]) -> bool:
        trial = info.get("freeTrialInfo")
        if trial is None:
            return False
        if isinstance(trial, str) and trial.strip().lower() in {
            "",
            "null",
            "none",
        }:
            return False
        return True

    @staticmethod
    def _trial_seconds(info: dict[str, Any]) -> int | None:
        trial = info.get("freeTrialInfo")
        if isinstance(trial, dict):
            start = trial.get("start")
            end = trial.get("end")
            if isinstance(start, (int, float)) and isinstance(end, (int, float)):
                return max(0, int(end - start))
        duration = info.get("time")
        if isinstance(duration, (int, float)) and duration > 0:
            return max(1, round(duration / 1000))
        return None

    @staticmethod
    def _log_url_result(
        endpoint: str,
        song: Song,
        info: dict[str, Any] | None,
        *,
        level: str | None,
        use_plugin_cookie: bool,
    ) -> None:
        quality = level or "legacy"
        if info is None:
            logger.info(
                f"网易云取歌响应: id={song.id} endpoint={endpoint} "
                f"quality={quality} "
                f"auth={'plugin-cookie' if use_plugin_cookie else 'api-default'} "
                "data=empty"
            )
            return
        trial = NetEaseMusicPlayer._is_trial(info)
        logger.info(
            f"网易云取歌响应: id={song.id} endpoint={endpoint} "
            f"quality={quality} "
            f"auth={'plugin-cookie' if use_plugin_cookie else 'api-default'} "
            f"code={info.get('code')} fee={info.get('fee')} "
            f"payed={info.get('payed')} time={info.get('time')} "
            f"size={info.get('size')} trial={trial} url={bool(info.get('url'))}"
        )

    @staticmethod
    def _reported_quality(
        info: dict[str, Any], requested: str | None = None
    ) -> str:
        reported = str(info.get("level") or "").strip().lower()
        if reported in NCM_QUALITY_FALLBACKS:
            return reported
        audio_format = normalize_audio_format(
            info.get("type") or info.get("encodeType") or info.get("format")
        )
        if audio_format == "flac":
            return "lossless"
        bitrate = info.get("br")
        if isinstance(bitrate, (int, float)):
            if bitrate >= 320_000:
                return "exhigh"
            if bitrate >= 192_000:
                return "higher"
            if bitrate > 0:
                return "standard"
        if requested:
            return requested
        return "standard"

    async def _login_status(self, *, use_plugin_cookie: bool) -> Any:
        return await self._request(
            f"{self.base_url}/login/status",
            params=self._params(),
            headers=self._headers(use_plugin_cookie=use_plugin_cookie),
        )

    @staticmethod
    def _has_account(result: Any) -> bool:
        data = result.get("data") if isinstance(result, dict) else None
        return isinstance(data, dict) and bool(data.get("account") or data.get("profile"))

    async def check_status(self) -> tuple[bool, str]:
        result = await self._login_status(use_plugin_cookie=False)
        if self._has_account(result):
            return (
                True,
                f"服务正常；登录=API 默认账号；请求音质={self.cfg.netease_quality}",
            )

        if self._cookie():
            cookie_result = await self._login_status(use_plugin_cookie=True)
            if self._has_account(cookie_result):
                return (
                    True,
                    f"服务正常；登录=插件 Cookie；请求音质={self.cfg.netease_quality}",
                )
            if not isinstance(result, dict):
                result = cookie_result

        if isinstance(result, dict):
            return (
                True,
                f"服务正常；未检测到登录账号；请求音质={self.cfg.netease_quality}",
            )
        return False, "私有 API 不可用"

    async def fetch_extra(self, song: Song) -> Song:
        if song.audio_url:
            return song

        quality_chain = self._quality_chain()
        requested_quality = quality_chain[0]
        auth_modes = [False]
        if self._cookie():
            auth_modes.append(True)

        attempts: list[tuple[str, str | None, bool]] = []
        for quality in quality_chain:
            for use_plugin_cookie in auth_modes:
                attempts.append(("/song/url/v1", quality, use_plugin_cookie))
        if self.cfg.quality_fallback:
            # 兼容部分只实现旧 /song/url 的部署。该接口没有 level 参数，
            # 因此仅作为所有明确音质均失败后的最后降级方案。
            for use_plugin_cookie in auth_modes:
                attempts.append(("/song/url", None, use_plugin_cookie))

        trial_info: dict[str, Any] | None = None
        last_info: dict[str, Any] | None = None
        for endpoint, level, use_plugin_cookie in attempts:
            result = await self._fetch_url_with_auth(
                endpoint,
                song,
                level=level,
                use_plugin_cookie=use_plugin_cookie,
            )
            info = self._first_info(result)
            self._log_url_result(
                endpoint,
                song,
                info,
                level=level,
                use_plugin_cookie=use_plugin_cookie,
            )
            if info is None:
                continue
            last_info = info
            if self._is_trial(info):
                trial_info = info
                continue
            if info.get("url"):
                song.audio_url = str(info["url"])
                song.audio_format = (
                    normalize_audio_format(info.get("type"))
                    or normalize_audio_format(info.get("encodeType"))
                    or normalize_audio_format(info.get("format"))
                    or infer_audio_format_from_url(song.audio_url)
                )
                selected_quality = self._reported_quality(info, level)
                song.audio_quality = selected_quality
                if selected_quality != requested_quality:
                    logger.info(
                        f"网易云音质自动降级: id={song.id} "
                        f"requested={requested_quality} selected={selected_quality}"
                    )
                return song

        if trial_info is not None:
            seconds = self._trial_seconds(trial_info)
            duration = f"{seconds} 秒" if seconds else "短时长"
            song.note = (
                f"网易云仅返回{duration}试听地址，已拒绝发送；"
                "请检查 API 容器或插件 Cookie 的会员登录状态"
            )
        elif last_info is not None:
            song.note = (
                "网易云未返回可播放地址"
                f"（code={last_info.get('code')}, fee={last_info.get('fee')}）"
            )
        else:
            song.note = "网易云 API 未返回播放地址，请检查服务和账号 Cookie"
        return song


# 兼容旧代码中的类名。
NetEaseMusicNodeJS = NetEaseMusicPlayer
