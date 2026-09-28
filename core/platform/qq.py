from __future__ import annotations

from typing import Any, ClassVar
from urllib.parse import quote, urljoin

from astrbot.api import logger

from ..config import PluginConfig
from ..model import (
    Platform,
    Song,
    infer_audio_format_from_url,
    normalize_audio_format,
)
from .base import BaseMusicPlayer


# L-1124/QQMusicApi v0.7 Web 路由的公开 file_type 整数映射。
# 这里只暴露普通、可直接播放的常用格式，不包含加密和铃声类型。
QQ_QUALITY_FILE_TYPES = {
    "master": 1,
    "atmos_2": 2,
    "atmos_51": 3,
    "atmos_71": 4,
    "dolby": 5,
    "flac": 7,
    "ogg_640": 8,
    "ogg_320": 9,
    "mp3_320": 12,
    "mp3_128": 13,
    "aac_192": 14,
}

QQ_QUALITY_FORMATS = {
    "master": "flac",
    "atmos_2": "flac",
    "atmos_51": "flac",
    "atmos_71": "ogg",
    "dolby": "mp4",
    "flac": "flac",
    "ogg_640": "ogg",
    "ogg_320": "ogg",
    "mp3_320": "mp3",
    "mp3_128": "mp3",
    "aac_192": "m4a",
}

QQ_QUALITY_FALLBACKS = {
    "master": ["master", "flac", "mp3_320", "mp3_128"],
    "atmos_2": ["atmos_2", "flac", "mp3_320", "mp3_128"],
    "atmos_51": ["atmos_51", "flac", "mp3_320", "mp3_128"],
    "atmos_71": ["atmos_71", "ogg_320", "mp3_320", "mp3_128"],
    "dolby": ["dolby", "flac", "mp3_320", "mp3_128"],
    "flac": ["flac", "mp3_320", "mp3_128"],
    "ogg_640": ["ogg_640", "ogg_320", "mp3_320", "mp3_128"],
    "ogg_320": ["ogg_320", "mp3_320", "mp3_128"],
    "mp3_320": ["mp3_320", "mp3_128"],
    "mp3_128": ["mp3_128"],
    "aac_192": ["aac_192", "mp3_128"],
}

# QQMusicApi 搜索结果只提供专辑 PMid 时，QQ 官方图片资源使用此模板。
QQ_ALBUM_COVER_TEMPLATE = (
    "https://y.gtimg.cn/music/photo_new/T002R500x500M000{album_mid}.jpg"
)


class QQMusicPlayer(BaseMusicPlayer):
    """L-1124/QQMusicApi Web 服务适配器。"""

    platform: ClassVar[Platform] = Platform(
        name="qq",
        display_name="QQ音乐",
        keywords=["qq点歌", "QQ点歌"],
    )

    def __init__(self, config: PluginConfig):
        super().__init__(config)
        self.base_url = config.qq_api_base_url.rstrip("/")
        self._cdn_base_url: str | None = None

    @property
    def _headers(self) -> dict[str, str]:
        headers = dict(self.HEADERS)
        if self.cfg.qq_cookie.strip():
            headers["Cookie"] = self.cfg.qq_cookie.strip()
        return headers

    @staticmethod
    def _unwrap(result: Any) -> dict[str, Any] | None:
        if not isinstance(result, dict):
            return None
        if "code" not in result:
            return result
        if result.get("code") != 0:
            return None
        data = result.get("data")
        return data if isinstance(data, dict) else None

    @staticmethod
    def _artist_names(raw: Any) -> str:
        if not isinstance(raw, list):
            return "未知歌手"
        names = [str(item.get("name")) for item in raw if isinstance(item, dict) and item.get("name")]
        return "、".join(names) or "未知歌手"

    @staticmethod
    def _cover_url(item: dict[str, Any]) -> str | None:
        album = item.get("album")
        candidates: list[Any] = [
            item.get("picUrl"),
            item.get("picurl"),
            item.get("cover_url"),
        ]
        if isinstance(album, dict):
            candidates.extend(
                [album.get("picUrl"), album.get("picurl"), album.get("cover_url")]
            )
        for value in candidates:
            if isinstance(value, str) and value.startswith(("http://", "https://")):
                return value
        if isinstance(album, dict):
            album_mid = album.get("pmid") or album.get("mid")
            if album_mid:
                return QQ_ALBUM_COVER_TEMPLATE.format(album_mid=album_mid)
        return None

    def _quality_chain(self) -> list[str]:
        quality = str(self.cfg.qq_quality or "mp3_128").strip().lower()
        if quality not in QQ_QUALITY_FILE_TYPES:
            logger.warning(f"未知 QQ 音质配置 {quality!r}，已回退到 mp3_128")
            quality = "mp3_128"
        if not self.cfg.quality_fallback:
            return [quality]
        return QQ_QUALITY_FALLBACKS[quality]

    async def fetch_songs(
        self, keyword: str, limit: int = 5, extra: str | None = None
    ) -> list[Song]:
        result = await self._request(
            f"{self.base_url}/search/search_by_type",
            params={"keyword": keyword, "search_type": 0, "num": limit, "page": 1},
            headers=self._headers,
        )
        payload = self._unwrap(result)
        raw_songs = payload.get("song", []) if payload else []
        if not isinstance(raw_songs, list):
            logger.error(f"QQ 音乐搜索返回结构异常: {result}")
            return []

        songs: list[Song] = []
        for item in raw_songs[:limit]:
            if not isinstance(item, dict):
                continue
            mid = item.get("mid")
            song_id = item.get("id")
            if not mid or song_id is None:
                continue
            file_info = item.get("file") if isinstance(item.get("file"), dict) else {}
            interval = item.get("interval")
            duration = interval * 1000 if isinstance(interval, (int, float)) else None
            songs.append(
                Song(
                    id=song_id,
                    source="qq",
                    mid=str(mid),
                    media_mid=str(file_info.get("media_mid") or "") or None,
                    song_type=item.get("type") if isinstance(item.get("type"), int) else None,
                    name=str(item.get("name") or item.get("title") or "未知歌曲"),
                    artists=self._artist_names(item.get("singer")),
                    duration=int(duration) if duration is not None else None,
                    cover_url=self._cover_url(item),
                )
            )
        return songs

    async def check_status(self) -> tuple[bool, str]:
        result = await self._request(
            f"{self.base_url}/song/get_cdn_dispatch", headers=self._headers
        )
        payload = self._unwrap(result)
        sip = payload.get("sip") if payload else None
        if not isinstance(sip, list) or not any(
            isinstance(url, str) and url.startswith(("http://", "https://"))
            for url in sip
        ):
            return False, "私有 API 或 QQ 音乐上游不可用"
        auth = "插件 Cookie" if self.cfg.qq_cookie.strip() else "API 默认账号"
        return True, f"服务与上游正常；认证={auth}；请求音质={self.cfg.qq_quality}"

    async def _get_cdn_base_url(self) -> str | None:
        if self._cdn_base_url:
            return self._cdn_base_url
        result = await self._request(
            f"{self.base_url}/song/get_cdn_dispatch", headers=self._headers
        )
        payload = self._unwrap(result)
        sip = payload.get("sip", []) if payload else []
        if isinstance(sip, list):
            for url in sip:
                if isinstance(url, str) and url.startswith(("http://", "https://")):
                    self._cdn_base_url = url.rstrip("/") + "/"
                    return self._cdn_base_url
        return None

    async def fetch_extra(self, song: Song) -> Song:
        if song.audio_url or not song.mid:
            return song

        quality_chain = self._quality_chain()
        requested_quality = quality_chain[0]
        selected_quality: str | None = None
        selected_item: dict[str, Any] | None = None
        last_result_code: Any = None
        for quality in quality_chain:
            file_type = QQ_QUALITY_FILE_TYPES[quality]
            params: dict[str, Any] = {"file_type": file_type}
            if song.song_type is not None:
                params["song_type"] = song.song_type
            if song.media_mid:
                params["media_mid"] = song.media_mid

            result = await self._request(
                f"{self.base_url}/song/{quote(song.mid, safe='')}/url",
                params=params,
                headers=self._headers,
            )
            payload = self._unwrap(result)
            url_items = payload.get("data", []) if payload else []
            item = (
                url_items[0]
                if isinstance(url_items, list)
                and url_items
                and isinstance(url_items[0], dict)
                else {}
            )
            last_result_code = item.get("result")
            logger.info(
                f"QQ 音乐取歌响应: id={song.id} quality={quality} "
                f"file_type={file_type} result={last_result_code} "
                f"url={bool(item.get('purl'))}"
            )
            if item.get("purl"):
                selected_quality = quality
                selected_item = item
                break

        if selected_item is None or selected_quality is None:
            song.note = (
                f"QQ 音乐未返回 {requested_quality} 或兼容音质的播放地址"
                f"（result={last_result_code}），请检查账号音质权限"
            )
            return song

        quality = selected_quality
        item = selected_item
        purl = item["purl"]
        result_code = item.get("result")
        if quality != requested_quality:
            logger.info(
                f"QQ 音质自动降级: id={song.id} "
                f"requested={requested_quality} selected={quality}"
            )

        if str(purl).startswith(("http://", "https://")):
            song.audio_url = str(purl)
        else:
            cdn_base_url = await self._get_cdn_base_url()
            if not cdn_base_url:
                song.note = "QQMusicApi 未返回音频 CDN 地址"
                return song
            song.audio_url = urljoin(cdn_base_url, str(purl))
        song.audio_format = (
            normalize_audio_format(item.get("format"))
            or normalize_audio_format(item.get("filetype"))
            or normalize_audio_format(item.get("file_type"))
            or infer_audio_format_from_url(song.audio_url)
            or QQ_QUALITY_FORMATS[quality]
        )
        song.audio_quality = quality
        logger.info(
            f"QQ 音乐取歌成功: id={song.id} quality={quality} "
            f"result={result_code} format={song.audio_format}"
        )
        return song
