from __future__ import annotations

import asyncio
from collections.abc import Sequence

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.core.message.components import (
    BaseMessageComponent,
    ComponentType,
    File,
    Image,
    Record,
)

from .config import PluginConfig
from .downloader import Downloader
from .model import Song, infer_audio_format_from_url, normalize_audio_format
from .platform import BaseMusicPlayer


class OneBotURLRecord(BaseMessageComponent):
    """绕过 aiocqhttp 的 WAV/Base64 转换，直接把 URL 交给 OneBot。"""

    type: ComponentType = ComponentType.Record
    file: str
    cache: int = 0
    proxy: int = 1
    timeout: int = 120

    def __init__(self, url: str):
        super().__init__(file=url, cache=0, proxy=1, timeout=120)

    def toDict(self) -> dict:
        return {
            "type": "record",
            "data": {
                "file": self.file,
                "cache": self.cache,
                "proxy": self.proxy,
                "timeout": self.timeout,
            },
        }


class MusicSender:
    """只负责文本选歌和歌曲发送，不调用任何额外音乐 API。"""

    def __init__(self, config: PluginConfig, downloader: Downloader):
        self.cfg = config
        self.downloader = downloader

    async def close(self) -> None:
        return None

    async def send_song_selection(
        self,
        event: AstrMessageEvent,
        songs: list[Song],
        player: BaseMusicPlayer,
    ) -> str:
        lines = [f"【{player.platform.display_name}】请回复序号选择歌曲："]
        for index, song in enumerate(songs, 1):
            duration = self._format_time(song.duration)
            suffix = f" ({duration})" if duration else ""
            lines.append(f"{index}. {song.name} - {song.artists}{suffix}")
        await event.send(event.plain_result("\n".join(lines)))
        return "text"

    @staticmethod
    def _format_time(duration_ms: int | None) -> str:
        if not duration_ms:
            return ""
        minutes, seconds = divmod(duration_ms // 1000, 60)
        return f"{minutes}:{seconds:02d}"

    @staticmethod
    def _is_aiocqhttp(event: AstrMessageEvent) -> bool:
        platform = str(event.get_platform_name() or "").lower()
        event_type = f"{type(event).__module__}.{type(event).__name__}".lower()
        return "aiocqhttp" in platform or "aiocqhttp" in event_type

    @staticmethod
    def _error_message(exc: Exception) -> str:
        message = str(exc).strip()
        return f"{type(exc).__name__}: {message}" if message else type(exc).__name__

    @staticmethod
    def _audio_suffix(song: Song) -> str:
        audio_format = (
            normalize_audio_format(song.audio_format)
            or infer_audio_format_from_url(song.audio_url)
            or "mp3"
        )
        return f".{audio_format}"

    async def _send_onebot_record_url(
        self, event: AstrMessageEvent, song: Song
    ) -> bool:
        if not song.audio_url:
            return False
        try:
            logger.info(
                f"OneBot 原生语音发送: id={song.id} "
                f"duration={song.duration} transport=direct-url"
            )
            await event.send(
                event.chain_result([OneBotURLRecord(song.audio_url)])
            )
            return True
        except Exception as exc:
            logger.warning(f"OneBot 原生语音发送失败: {self._error_message(exc)}")
            return False

    async def _send_cover(self, event: AstrMessageEvent, song: Song) -> bool:
        if not self.cfg.send_cover or not song.cover_url:
            return False
        try:
            await event.send(
                event.chain_result([Image.fromURL(song.cover_url)])
            )
            return True
        except Exception as exc:
            logger.warning(f"专辑封面发送失败: {self._error_message(exc)}")
            return False

    async def _send_record_link(self, event: AstrMessageEvent, song: Song) -> bool:
        if not song.audio_url:
            return False
        if self.cfg.onebot_direct_record and self._is_aiocqhttp(event):
            return await self._send_onebot_record_url(event, song)
        try:
            await event.send(event.chain_result([Record.fromURL(song.audio_url)]))
            return True
        except Exception as exc:
            logger.warning(f"语音链接发送失败: {self._error_message(exc)}")
            return False

    async def _send_record_local(self, event: AstrMessageEvent, song: Song) -> bool:
        if not song.audio_url:
            return False
        if self.cfg.onebot_direct_record and self._is_aiocqhttp(event):
            # aiocqhttp 会把 Record 统一转换为 WAV/Base64。完整歌曲会显著
            # 膨胀并容易触发 WebSocket 超时，因此不再先下载本地 MP3。
            return await self._send_onebot_record_url(event, song)
        file_path = await self.downloader.download_song(
            song.audio_url, song.audio_format
        )
        if not file_path:
            return False
        try:
            await event.send(
                event.chain_result([Record.fromFileSystem(str(file_path.resolve()))])
            )
            return True
        except Exception as exc:
            logger.warning(f"本地语音发送失败: {self._error_message(exc)}")
            return False
        finally:
            file_path.unlink(missing_ok=True)

    async def _send_file_link(self, event: AstrMessageEvent, song: Song) -> bool:
        if not song.audio_url:
            return False
        try:
            file_name = f"{song.name}_{song.artists}{self._audio_suffix(song)}"
            await event.send(
                event.chain_result([File(name=file_name, url=song.audio_url)])
            )
            return True
        except Exception as exc:
            logger.warning(f"文件链接发送失败: {self._error_message(exc)}")
            return False

    async def _send_file_local(self, event: AstrMessageEvent, song: Song) -> bool:
        if not song.audio_url:
            return False
        file_path = await self.downloader.download_song(
            song.audio_url, song.audio_format
        )
        if not file_path:
            return False
        try:
            file_name = f"{song.name}_{song.artists}{file_path.suffix}"
            await event.send(
                event.chain_result(
                    [File(name=file_name, file=str(file_path.resolve()))]
                )
            )
            return True
        except Exception as exc:
            logger.warning(f"本地文件发送失败: {self._error_message(exc)}")
            return False
        finally:
            file_path.unlink(missing_ok=True)

    @staticmethod
    async def _send_text(event: AstrMessageEvent, song: Song) -> bool:
        if not song.audio_url:
            return False
        try:
            text = f"{song.name} - {song.artists}\n{song.audio_url}"
            await event.send(event.plain_result(text))
            return True
        except Exception as exc:
            logger.warning(f"文本链接发送失败: {MusicSender._error_message(exc)}")
            return False

    def _is_mode_supported(self, mode: str, event: AstrMessageEvent) -> bool:
        platform = event.get_platform_name()
        if mode == "text":
            return True
        if mode in {"record_link", "record_local"}:
            return platform not in self.cfg.record_unsupported
        if mode in {"file_link", "file_local"}:
            return platform not in self.cfg.file_unsupported
        return False

    async def send_song(
        self,
        event: AstrMessageEvent,
        player: BaseMusicPlayer,
        song: Song,
        *,
        send_modes: Sequence[str] | None = None,
    ) -> bool:
        logger.info(
            f"点歌: {player.platform.display_name} / {song.name} / {song.artists}"
        )
        if not song.audio_url:
            song = await player.fetch_extra(song)
        if not song.audio_url:
            reason = f"：{song.note}" if song.note else ""
            await event.send(event.plain_result(f"【{song.name}】音频获取失败{reason}"))
            return False

        active_modes = (
            send_modes if send_modes is not None else self.cfg.real_send_modes
        )
        await self._send_cover(event, song)
        logger.info(
            f"歌曲发送参数: id={song.id} quality={song.audio_quality} "
            f"format={song.audio_format} cover={bool(song.cover_url)} "
            f"modes={active_modes}"
        )

        senders = {
            "record_link": self._send_record_link,
            "record_local": self._send_record_local,
            "file_link": self._send_file_link,
            "file_local": self._send_file_local,
            "text": self._send_text,
        }
        is_onebot_direct = (
            self.cfg.onebot_direct_record and self._is_aiocqhttp(event)
        )
        onebot_record_attempted = False
        onebot_record_failed = False
        for mode in active_modes:
            if not self._is_mode_supported(mode, event):
                continue
            if is_onebot_direct and mode in {"record_link", "record_local"}:
                if onebot_record_attempted:
                    continue
                onebot_record_attempted = True
            sender = senders.get(mode)
            if sender:
                if onebot_record_failed and mode not in {
                    "record_link",
                    "record_local",
                }:
                    # OneBot 调用超时后给 WebSocket 一个短暂恢复窗口，且不再
                    # 提交第二条语音任务。
                    await asyncio.sleep(1)
                    onebot_record_failed = False
                if await sender(event, song):
                    return True
                if is_onebot_direct and mode in {"record_link", "record_local"}:
                    onebot_record_failed = True

        await event.send(event.plain_result("歌曲发送失败"))
        return False
