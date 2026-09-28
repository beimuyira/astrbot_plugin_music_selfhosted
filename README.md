# astrbot_plugin_music_selfhosted

面向私有化部署的 AstrBot 点歌插件。插件只连接你自行部署的 QQ 音乐和网易云音乐 API，不依赖公共聚合音乐接口。

本项目基于 [Zhalslar/astrbot_plugin_music](https://github.com/Zhalslar/astrbot_plugin_music) 重构，保留原项目 MIT 许可和作者署名。当前分支专注于自建 API、点歌、文件下载和稳定发送，不追求与上游的全部功能保持一致。

## 功能

- QQ 音乐与网易云音乐可随时切换，也可配置默认平台。
- 使用自建 [L-1124/QQMusicApi](https://github.com/L-1124/QQMusicApi) 和 [NeteaseCloudMusicApiEnhanced/api-enhanced](https://github.com/NeteaseCloudMusicApiEnhanced/api-enhanced)。
- 支持搜索后回复序号，也支持在命令末尾直接指定序号。
- 普通点歌默认发送语音；下载命令临时改为发送音乐文件。
- 支持 MP3、FLAC、OGG、M4A 等真实文件格式。
- 支持 QQ 与网易云音质选择和自动降级。
- 支持在音频前单独发送专辑封面。
- 支持检查两个私有 API、上游和登录来源。
- 拒绝网易云返回的短时长试听链接。

## 后端要求

| 平台 | 私有服务 | 容器网络地址示例 |
| --- | --- | --- |
| QQ 音乐 | L-1124/QQMusicApi Web 服务 | `http://qqmusic-api:8080` |
| 网易云音乐 | NeteaseCloudMusicApi Enhanced | `http://ncm-api:3000` |

建议让 AstrBot、QQMusicApi 和网易云 API 加入同一个 Docker 网络，只在容器网络内暴露音乐 API。私有服务仍会访问音乐平台官方上游；插件不会绕过会员、数字专辑、地区版权或账号自身的播放权限。

QQMusicApi 推荐通过 `accounts.toml` 管理默认账号。网易云 API 推荐由容器持有登录 Cookie；插件配置中的 Cookie 只作为备用认证，并通过 HTTP Cookie 请求头发送。

## 安装

### 从 GitHub 安装

在 AstrBot 插件管理页面使用仓库地址：

```text
https://github.com/beimuyira/astrbot_plugin_music_selfhosted
```

### 上传 ZIP

从 GitHub Releases 下载 `astrbot_plugin_music_selfhosted-<version>.zip`，直接上传至 AstrBot 插件管理页面。不要上传源码仓库外层目录或包含旧版本 ZIP 的工作目录。

安装后在插件配置页面填写两个私有 API 地址并重新加载插件。

## 命令

```text
点歌 <歌名> [序号]          使用默认平台并按默认策略发送
QQ点歌 <歌名> [序号]        强制使用 QQ 音乐
网易点歌 <歌名> [序号]      强制使用网易云音乐

下载音乐 <歌名> [序号]      使用默认平台并以文件发送
QQ下载 <歌名> [序号]        使用 QQ 音乐并以文件发送
网易下载 <歌名> [序号]      使用网易云音乐并以文件发送

音乐状态                    检查两个私有音乐服务
```

`selection_mode=text` 时插件会展示候选歌曲并等待回复序号；设置为 `single` 时直接选择第一首。文件发送意图会保留到本次数字选歌完成，不会修改后台默认配置。

## 发送策略

普通点歌默认顺序：

```text
record_local → record_link → text
```

下载命令固定使用：

```text
file_local → file_link → text
```

本地文件发送完成后会立即清理临时音频。文件扩展名依据 API 格式字段、HTTP `Content-Type` 和音频 URL 判断，不会通过修改后缀伪装格式。

在 aiocqhttp/NapCat 平台开启 `onebot_direct_record` 后，语音模式会把远程音频 URL 直接交给 OneBot，避免完整歌曲被转换成体积很大的 WAV/Base64 数据。

## 主要配置

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `default_platform` | `qq` | 普通点歌和下载命令使用的平台 |
| `qq_api_base_url` | `http://qqmusic-api:8080` | QQMusicApi 地址 |
| `qq_cookie` | 空 | 可选，优先推荐 API 服务端账号 |
| `qq_quality` | `mp3_128` | QQ 请求音质 |
| `netease_api_base_url` | `http://ncm-api:3000` | 网易云 API 地址 |
| `netease_cookie` | 空 | 可选备用 Cookie |
| `netease_quality` | `standard` | 网易云请求音质 |
| `quality_fallback` | `true` | 目标音质不可用时逐级降级 |
| `send_cover` | `true` | 在歌曲前发送专辑封面 |
| `onebot_direct_record` | `true` | NapCat 使用 URL 直传语音 |

QQ 示例降级链为 `flac → mp3_320 → mp3_128`；网易云示例为 `lossless → exhigh → higher → standard`。实际降级会写入脱敏日志。

## 安全说明

- 不要把 Cookie、`accounts.toml`、`.env`、反向代理密钥或运行日志提交到 GitHub。
- 不建议把音乐 API 端口直接暴露到公网；优先使用 Docker 内部网络。
- 公开部署时应自行增加反向代理认证、访问频率限制和 HTTPS。
- 日志仅记录认证来源，不记录 Cookie 内容和账号详情。

发现安全问题时，请按 [SECURITY.md](SECURITY.md) 的方式私下报告，不要在公开 Issue 中粘贴凭证。

## 开发与发布

```bash
python tools/validate_release.py
python -m unittest discover -s tests -v
```

推送 `v*` 标签后，GitHub Actions 会校验标签与 `metadata.yaml` 版本并生成可直接上传 AstrBot 的 ZIP。

## 许可

本项目使用 [MIT License](LICENSE)。上游署名和本项目修改者信息见 [NOTICE.md](NOTICE.md)。

