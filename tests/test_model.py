from __future__ import annotations

import unittest

from core.model import (
    infer_audio_format_from_content_type,
    infer_audio_format_from_url,
    normalize_audio_format,
)


class AudioFormatTests(unittest.TestCase):
    def test_normalize_audio_format(self) -> None:
        self.assertEqual(normalize_audio_format("audio/mpeg"), "mp3")
        self.assertEqual(normalize_audio_format(".FLAC"), "flac")
        self.assertIsNone(normalize_audio_format("exe"))

    def test_infer_from_url(self) -> None:
        self.assertEqual(
            infer_audio_format_from_url("https://example.test/song.ogg?token=1"),
            "ogg",
        )

    def test_infer_from_content_type(self) -> None:
        self.assertEqual(infer_audio_format_from_content_type("audio/mp4"), "m4a")
        self.assertEqual(
            infer_audio_format_from_content_type("audio/flac; charset=binary"),
            "flac",
        )


if __name__ == "__main__":
    unittest.main()
