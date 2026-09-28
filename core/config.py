from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from pathlib import Path
from types import MappingProxyType, UnionType
from typing import Any, Union, get_args, get_origin, get_type_hints

from astrbot.api import logger
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.star.context import Context
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path

from .routing import VOICE_SEND_MODES


class ConfigNode:
    _SCHEMA_CACHE: dict[type, dict[str, type]] = {}
    _FIELDS_CACHE: dict[type, set[str]] = {}

    @classmethod
    def _schema(cls) -> dict[str, type]:
        return cls._SCHEMA_CACHE.setdefault(cls, get_type_hints(cls))

    @classmethod
    def _fields(cls) -> set[str]:
        return cls._FIELDS_CACHE.setdefault(
            cls, {key for key in cls._schema() if not key.startswith("_")}
        )

    @staticmethod
    def _is_optional(tp: type) -> bool:
        return get_origin(tp) in (Union, UnionType) and type(None) in get_args(tp)

    def __init__(self, data: MutableMapping[str, Any]):
        object.__setattr__(self, "_data", data)
        object.__setattr__(self, "_children", {})
        for key, tp in self._schema().items():
            if key.startswith("_") or key in data or hasattr(self.__class__, key):
                continue
            if not self._is_optional(tp):
                logger.warning(f"[config:{self.__class__.__name__}] miss key: {key}")

    def __getattr__(self, key: str) -> Any:
        if key in self._fields():
            return self._data.get(key)
        raise AttributeError(key)

    def __setattr__(self, key: str, value: Any) -> None:
        if key in self._fields():
            self._data[key] = value
            return
        object.__setattr__(self, key, value)

    def raw_data(self) -> Mapping[str, Any]:
        return MappingProxyType(self._data)

    def save_config(self) -> None:
        if not isinstance(self._data, AstrBotConfig):
            raise RuntimeError("save_config() only supports AstrBotConfig")
        self._data.save_config()


class PluginConfig(ConfigNode):
    default_platform: str
    qq_api_base_url: str
    qq_cookie: str
    qq_quality: str
    netease_api_base_url: str
    netease_cookie: str
    netease_quality: str
    quality_fallback: bool
    send_cover: bool
    onebot_direct_record: bool
    song_limit: int
    selection_mode: str
    send_modes: list[str]
    record_unsupported: list[str]
    file_unsupported: list[str]
    proxy: str
    request_timeout: int
    download_timeout: int
    timeout: int

    _plugin_name: str = "astrbot_plugin_music_selfhosted"

    _DEFAULTS: dict[str, Any] = {
        "default_platform": "qq",
        "qq_api_base_url": "http://qqmusic-api:8080",
        "qq_cookie": "",
        "qq_quality": "mp3_128",
        "netease_api_base_url": "http://ncm-api:3000",
        "netease_cookie": "",
        "netease_quality": "standard",
        "quality_fallback": True,
        "send_cover": True,
        "onebot_direct_record": True,
        "song_limit": 5,
        "selection_mode": "text",
        "send_modes": list(VOICE_SEND_MODES),
        "record_unsupported": [],
        "file_unsupported": [],
        "proxy": "",
        "request_timeout": 15,
        "download_timeout": 120,
        "timeout": 30,
    }

    def __init__(self, config: AstrBotConfig, context: Context):
        if "default_platform" not in config:
            legacy = str(config.get("default_player_name") or "").lower()
            config["default_platform"] = "qq" if "qq" in legacy else "netease"
        for key, value in self._DEFAULTS.items():
            if key not in config or config[key] is None:
                config[key] = list(value) if isinstance(value, list) else value

        super().__init__(config)
        self.context = context
        self.temp_dir = Path(get_astrbot_temp_path()) / self._plugin_name
        self.songs_dir = self.temp_dir / "songs"
        self.songs_dir.mkdir(parents=True, exist_ok=True)
        self._send_modes = [
            mode.split("(", 1)[0].strip() for mode in self.send_modes if mode
        ]

    @property
    def http_proxy(self) -> str | None:
        return self.proxy.strip() or None

    @property
    def real_send_modes(self) -> list[str]:
        return self._send_modes

    @property
    def real_song_limit(self) -> int:
        return 1 if self.selection_mode == "single" else max(1, self.song_limit)
