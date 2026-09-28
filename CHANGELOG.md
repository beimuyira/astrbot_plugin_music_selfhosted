# 更新日志

本项目从公开版本 `1.0.0` 起使用语义化版本。Git 标签在版本号前添加 `v`，例如 `v1.0.0`。

## 1.0.0 - 2026-09-21

- 重构为独立的 `astrbot_plugin_music_selfhosted` 插件身份。
- 只保留 QQ 音乐、网易云音乐点歌、数字选歌和文件下载功能。
- QQ 音乐适配 L-1124/QQMusicApi 私有 Web 服务。
- 网易云适配 NeteaseCloudMusicApi Enhanced 私有服务。
- 移除 TXQQ、Meting 和其他公共音乐聚合 API。
- 增加 QQ 与网易云独立音质配置和自动降级。
- 增加试听链接拒绝、Cookie 备用认证和脱敏诊断日志。
- 增加 OneBot URL 语音直传，降低完整歌曲发送超时概率。
- 增加真实音频格式识别和临时文件清理。
- 增加专辑封面发送和音乐服务状态命令。
- 增加 `下载音乐`、`QQ下载` 和 `网易下载` 文件发送命令。
- 抽离命令路由模块，并增加自动测试、发布校验和 GitHub Actions。

## 上游来源

本项目基于 [Zhalslar/astrbot_plugin_music](https://github.com/Zhalslar/astrbot_plugin_music) 修改。上游历史版本不作为本项目语义化版本的一部分；版权与许可信息见 `LICENSE` 和 `NOTICE.md`。
