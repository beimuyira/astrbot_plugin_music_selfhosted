# 贡献指南

感谢参与维护私有音乐点歌插件。

## 提交前检查

1. 不要提交 Cookie、账号文件、真实服务器地址或运行日志。
2. 保持两个音乐平台适配器互相独立。
3. 网络请求必须使用异步客户端，不要在事件循环中执行阻塞下载。
4. 新命令优先在 `core/routing.py` 中声明路由，避免继续扩张 `main.py` 条件分支。
5. 新增行为应补充测试和 README。

运行：

```bash
python tools/validate_release.py
python -m unittest discover -s tests -v
ruff check .
```

提交信息建议使用 `feat:`、`fix:`、`docs:`、`refactor:` 或 `test:` 前缀。
