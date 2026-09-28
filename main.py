import asyncio
import traceback

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.utils.session_waiter import SessionController, session_waiter

from .core.config import PluginConfig
from .core.downloader import Downloader
from .core.platform import BaseMusicPlayer, NetEaseMusicPlayer, QQMusicPlayer
from .core.routing import parse_song_query, resolve_command
from .core.sender import MusicSender


class MusicPlugin(Star):
    """使用私有 QQ 音乐和网易云 API 的精简点歌插件。"""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.cfg = PluginConfig(config, context)
        self.downloader = Downloader(self.cfg)
        self.sender = MusicSender(self.cfg, self.downloader)
        self.players: list[BaseMusicPlayer] = []

    async def initialize(self):
        # 显式注册，防止遗留平台模块被意外加载。
        self.players = [QQMusicPlayer(self.cfg), NetEaseMusicPlayer(self.cfg)]
        logger.info("已启用私有音乐源：QQ音乐、网易云音乐")

    async def terminate(self):
        await self.sender.close()
        await self.downloader.close()
        for player in self.players:
            await player.close()

    def get_player(self, platform_name: str) -> BaseMusicPlayer | None:
        target = platform_name.strip().lower()
        for player in self.players:
            platform = player.platform
            if target == platform.name.lower():
                return player
        return None

    @filter.command(
        "点歌",
        alias={"music", "QQ点歌", "qq点歌", "网易点歌", "网易云点歌"},
    )
    async def search_song(self, event: AstrMessageEvent):
        """点歌/QQ点歌/网易点歌 <歌名> [序号]"""
        # 具体逻辑由全消息监听器处理，以便可靠识别别名。
        pass

    @filter.command(
        "下载音乐",
        alias={
            "下载歌曲",
            "QQ下载",
            "qq下载",
            "QQ音乐下载",
            "网易下载",
            "网易云下载",
        },
    )
    async def download_song(self, event: AstrMessageEvent):
        """下载音乐/QQ下载/网易下载 <歌名> [序号]"""
        # 与点歌共用搜索和选歌流程，只覆盖本次请求的发送方式。
        pass

    @filter.command("音乐状态", alias={"点歌状态"})
    async def music_status(self, event: AstrMessageEvent):
        """检查 QQ 音乐与网易云私有 API 的可用状态。"""
        results = await asyncio.gather(
            *(player.check_status() for player in self.players),
            return_exceptions=True,
        )
        lines = ["音乐服务状态："]
        for player, result in zip(self.players, results, strict=True):
            if isinstance(result, BaseException):
                ok = False
                detail = type(result).__name__
                logger.warning(
                    f"{player.platform.display_name}状态检查失败: {result}"
                )
            else:
                ok, detail = result
            icon = "✅" if ok else "❌"
            lines.append(f"{icon} {player.platform.display_name}：{detail}")
        yield event.plain_result("\n".join(lines))

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_search_song(self, event: AstrMessageEvent):
        if not event.is_at_or_wake_command:
            return

        parts = event.message_str.strip().split(maxsplit=1)
        if len(parts) != 2:
            return
        command, raw_query = parts
        route = resolve_command(command, self.cfg.default_platform)
        if route is None:
            return
        player = self.get_player(route.platform)
        if player is None:
            return

        song_name, index = parse_song_query(raw_query)
        if not song_name:
            yield event.plain_result("未指定歌名")
            return

        try:
            songs = await player.fetch_songs(
                song_name, limit=self.cfg.real_song_limit
            )
        except Exception as exc:
            logger.error(traceback.format_exc())
            yield event.plain_result(f"{player.platform.display_name}搜索失败：{exc}")
            return

        if not songs:
            yield event.plain_result(
                f"{player.platform.display_name}搜索【{song_name}】无结果"
            )
            return

        if self.cfg.selection_mode == "single" or len(songs) == 1:
            index = 1
        if index is not None:
            if not 1 <= index <= len(songs):
                yield event.plain_result(f"序号应在 1-{len(songs)} 之间")
                return
            await self.sender.send_song(
                event,
                player,
                songs[index - 1],
                send_modes=route.send_modes,
            )
            event.stop_event()
            return

        await self.sender.send_song_selection(event, songs, player)

        @session_waiter(timeout=self.cfg.timeout)
        async def selection_waiter(
            controller: SessionController, reply_event: AstrMessageEvent
        ):
            reply = reply_event.message_str.strip()
            if not reply.isdigit():
                return
            selected = int(reply)
            if not 1 <= selected <= len(songs):
                await reply_event.send(
                    reply_event.plain_result(f"序号应在 1-{len(songs)} 之间")
                )
                return
            controller.stop()
            await self.sender.send_song(
                reply_event,
                player,
                songs[selected - 1],
                send_modes=route.send_modes,
            )

        try:
            await selection_waiter(event)
        except TimeoutError:
            yield event.plain_result(f"{route.action_name}超时！")
        except Exception as exc:
            logger.error(traceback.format_exc())
            yield event.plain_result(f"{route.action_name}失败：{exc}")
        finally:
            event.stop_event()
