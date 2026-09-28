from __future__ import annotations

import sys
import types
import unittest


class _Logger:
    def __getattr__(self, _name):
        return lambda *_args, **_kwargs: None


class _ClientSession:
    def __init__(self, **_kwargs):
        self.closed = False

    async def close(self):
        self.closed = True


class _Component:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _ComponentType:
    Record = "record"


class _Image(_Component):
    @classmethod
    def fromURL(cls, url):
        return cls(url=url, kind="image")


class _Record(_Component):
    @classmethod
    def fromURL(cls, url):
        return cls(url=url, kind="record")

    @classmethod
    def fromFileSystem(cls, path):
        return cls(path=path, kind="record")


class _File(_Component):
    pass


def _install_runtime_stubs() -> None:
    api = types.ModuleType("astrbot.api")
    api.logger = _Logger()
    event = types.ModuleType("astrbot.api.event")
    event.AstrMessageEvent = object
    components = types.ModuleType("astrbot.core.message.components")
    components.BaseMessageComponent = _Component
    components.ComponentType = _ComponentType
    components.File = _File
    components.Image = _Image
    components.Record = _Record

    aiohttp = types.ModuleType("aiohttp")
    aiohttp.ClientTimeout = lambda **_kwargs: object()
    aiohttp.ClientSession = _ClientSession
    aiohttp.ClientError = Exception
    aiohttp.ContentTypeError = ValueError
    aiohttp.ClientResponse = object

    config = types.ModuleType("core.config")
    config.PluginConfig = object
    downloader = types.ModuleType("core.downloader")
    downloader.Downloader = object

    sys.modules.update(
        {
            "astrbot": types.ModuleType("astrbot"),
            "astrbot.api": api,
            "astrbot.api.event": event,
            "astrbot.core": types.ModuleType("astrbot.core"),
            "astrbot.core.message": types.ModuleType("astrbot.core.message"),
            "astrbot.core.message.components": components,
            "aiohttp": aiohttp,
            "core.config": config,
            "core.downloader": downloader,
        }
    )


_install_runtime_stubs()

from core.model import Platform, Song  # noqa: E402
from core.platform.ncm_nodejs import NetEaseMusicPlayer  # noqa: E402
from core.platform.qq import QQMusicPlayer  # noqa: E402
from core.sender import MusicSender  # noqa: E402


class _Config:
    request_timeout = 1
    http_proxy = None
    qq_api_base_url = "http://qqmusic-api:8080"
    qq_cookie = ""
    qq_quality = "flac"
    netease_api_base_url = "http://ncm-api:3000"
    netease_cookie = "MUSIC_U=test-only"
    netease_quality = "lossless"
    quality_fallback = True
    send_cover = False
    onebot_direct_record = False
    real_send_modes = ["record_local", "record_link", "text"]
    record_unsupported = []
    file_unsupported = []


class PlatformFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_qq_quality_fallback_and_cover(self) -> None:
        player = QQMusicPlayer(_Config())
        file_types: list[int] = []

        async def request(url, **kwargs):
            params = kwargs.get("params") or {}
            if url.endswith("/search/search_by_type"):
                return {
                    "code": 0,
                    "data": {
                        "song": [
                            {
                                "id": 1,
                                "mid": "song-mid",
                                "name": "Song",
                                "singer": [{"name": "Singer"}],
                                "album": {"pmid": "album-mid"},
                            }
                        ]
                    },
                }
            file_types.append(params["file_type"])
            purl = (
                "https://cdn.example.test/song.mp3"
                if params["file_type"] == 12
                else ""
            )
            return {"code": 0, "data": {"data": [{"result": 0, "purl": purl}]}}

        player._request = request
        songs = await player.fetch_songs("Song")
        self.assertTrue(songs[0].cover_url.endswith("album-mid.jpg"))
        song = await player.fetch_extra(songs[0])
        self.assertEqual(file_types, [7, 12])
        self.assertEqual(song.audio_quality, "mp3_320")
        self.assertEqual(song.audio_format, "mp3")
        await player.close()

    async def test_netease_prefers_requested_quality_across_auth(self) -> None:
        player = NetEaseMusicPlayer(_Config())
        calls: list[tuple[str | None, bool]] = []

        async def request(_url, **kwargs):
            params = kwargs.get("params") or {}
            headers = kwargs.get("headers") or {}
            level = params.get("level")
            plugin_cookie = "Cookie" in headers
            calls.append((level, plugin_cookie))
            if level == "lossless" and not plugin_cookie:
                info = {
                    "url": "https://cdn.example.test/trial.mp3",
                    "freeTrialInfo": {"start": 0, "end": 30},
                }
            elif level == "exhigh" and not plugin_cookie:
                info = {
                    "url": "https://cdn.example.test/full.mp3",
                    "type": "mp3",
                    "br": 320000,
                    "freeTrialInfo": None,
                }
            else:
                info = {"url": None, "freeTrialInfo": None}
            return {"data": [info]}

        player._request = request
        song = await player.fetch_extra(Song(id=2))
        self.assertEqual(
            calls,
            [("lossless", False), ("lossless", True), ("exhigh", False)],
        )
        self.assertEqual(song.audio_quality, "exhigh")
        self.assertTrue(song.audio_url.endswith("full.mp3"))
        await player.close()


class _Event:
    def get_platform_name(self):
        return "test"

    def plain_result(self, text):
        return text

    async def send(self, _payload):
        return None


class SenderModeTests(unittest.IsolatedAsyncioTestCase):
    async def test_file_mode_overrides_default_voice_for_one_request(self) -> None:
        sender = MusicSender(_Config(), object())
        called: list[str] = []

        async def record(_event, _song):
            called.append("record_local")
            return True

        async def file(_event, _song):
            called.append("file_local")
            return True

        sender._send_record_local = record
        sender._send_file_local = file
        player = types.SimpleNamespace(platform=Platform("test", "Test", []))
        song = Song(id=3, audio_url="https://cdn.example.test/song.mp3")

        self.assertTrue(await sender.send_song(_Event(), player, song))
        self.assertEqual(called, ["record_local"])

        called.clear()
        self.assertTrue(
            await sender.send_song(
                _Event(),
                player,
                song,
                send_modes=("file_local", "file_link", "text"),
            )
        )
        self.assertEqual(called, ["file_local"])


if __name__ == "__main__":
    unittest.main()
