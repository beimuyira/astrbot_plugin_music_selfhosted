from __future__ import annotations

import unittest

from core.routing import FILE_SEND_MODES, parse_song_query, resolve_command


class RoutingTests(unittest.TestCase):
    def test_default_platform_routes(self) -> None:
        point = resolve_command("点歌", "netease")
        download = resolve_command("下载音乐", "qq")

        self.assertIsNotNone(point)
        self.assertEqual(point.platform, "netease")
        self.assertIsNone(point.send_modes)
        self.assertIsNotNone(download)
        self.assertEqual(download.platform, "qq")
        self.assertEqual(download.send_modes, FILE_SEND_MODES)

    def test_explicit_platform_routes(self) -> None:
        self.assertEqual(resolve_command("QQ下载", "netease").platform, "qq")
        self.assertEqual(resolve_command("网易云下载", "qq").platform, "netease")
        self.assertEqual(resolve_command("QQ点歌", "netease").platform, "qq")

    def test_unknown_command_or_platform_is_rejected(self) -> None:
        self.assertIsNone(resolve_command("未知命令", "qq"))
        self.assertIsNone(resolve_command("点歌", "invalid"))

    def test_song_query(self) -> None:
        self.assertEqual(parse_song_query("好久不见"), ("好久不见", None))
        self.assertEqual(parse_song_query("好久不见 2"), ("好久不见", 2))
        self.assertEqual(parse_song_query("歌曲 2026 live"), ("歌曲 2026 live", None))
        self.assertEqual(parse_song_query("歌曲 0"), ("歌曲", 0))


if __name__ == "__main__":
    unittest.main()
