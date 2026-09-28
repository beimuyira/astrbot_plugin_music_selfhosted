from abc import ABC, abstractmethod
from typing import ClassVar

import aiohttp

from astrbot.api import logger

from ..config import PluginConfig
from ..model import Platform, Song


class BaseMusicPlayer(ABC):
    """
    全功能音乐平台基类 + HTTP 支持
    子类必须实现：
    - platform: 平台信息（包含名称和显示名称)
    - fetch_songs: 获取歌曲列表
    """

    _registry: ClassVar[list[type["BaseMusicPlayer"]]] = []
    """ 存储所有已注册的 MusicPlatform 类 """

    platform: ClassVar[Platform]
    """ 平台信息（包含名称和显示名称） """

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; WOW64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/55.0.2883.87 Safari/537.36"
        )
    }

    def __init__(self, config: PluginConfig):
        self.cfg = config
        timeout = aiohttp.ClientTimeout(total=self.cfg.request_timeout)
        self.session = aiohttp.ClientSession(timeout=timeout)

    def __init_subclass__(cls, **kwargs):
        """自动注册子类到 _registry"""
        super().__init_subclass__(**kwargs)
        if ABC not in cls.__bases__:  # 跳过抽象类
            BaseMusicPlayer._registry.append(cls)

    @classmethod
    def get_all_subclass(cls) -> list[type["BaseMusicPlayer"]]:
        """获取所有已注册的 Parser 类"""
        return cls._registry

    # ---------- 子类必须实现 ----------

    @abstractmethod
    async def fetch_songs(
        self, keyword: str, limit: int, extra: str | None = None
    ) -> list[Song]:
        """
        搜索歌曲
        :param keyword: 搜索关键字
        :param limit: 搜索数量
        :param extra: 额外参数
        """
        raise NotImplementedError

    # ---------- 可复用方法 ----------
    async def fetch_extra(self, song: Song) -> Song:
        """由具体平台补充播放地址。"""
        return song

    async def check_status(self) -> tuple[bool, str]:
        """检查私有服务及其音乐上游状态。"""
        return False, "未实现状态检查"

    async def close(self):
        """释放 session"""
        if not self.session.closed:
            await self.session.close()

    # ---------- 内部 HTTP 方法 ----------

    async def _request(
        self,
        url: str,
        *,
        method: str = "GET",
        params: dict | None = None,
        data: dict | None = None,
        json_data: dict | None = None,
        headers: dict | None = None,
        cookies: dict | None = None,
        ssl: bool = True,
    ):
        headers = headers or self.HEADERS
        try:
            async with self.session.request(
                method.upper(),
                url,
                params=params,
                data=data,
                json=json_data,
                headers=headers,
                cookies=cookies,
                proxy=self.cfg.http_proxy,
                ssl=ssl,
            ) as resp:
                return await self._parse_response(resp)
        except (aiohttp.ClientError, TimeoutError) as exc:
            logger.warning(f"请求音乐 API 失败: {url}: {exc}")
            return None

    async def _parse_response(self, resp: aiohttp.ClientResponse):
        try:
            resp_text = await resp.text()

            if resp.status != 200:
                logger.warning(f"HTTP 请求返回 {resp.status}: {resp_text[:200]}")
                return None

            if not resp_text.strip():
                logger.warning("HTTP 响应为空")
                return None

            try:
                return await resp.json(content_type=None)
            except (ValueError, aiohttp.ContentTypeError):
                return resp_text

        except Exception as e:
            logger.warning(f"解析响应失败: {e}")
            return None
