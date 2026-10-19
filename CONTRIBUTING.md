# 贡献指南

本项目为 Agent 提供可调用、可理解、可扩展的 B 站基础能力。优先贡献独立基础操作、兼容性修复、实现说明与关键边界测试。分析、选题、报告、素材组合等应用可以在本项目之上另行开发。

## 开发环境

在仓库根目录，使用 Python 3.10+：

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m unittest discover -s tests -v
```

测试不访问账号或网络，不需要 Cookie。当前 CI 配置 Linux Python 3.10/3.11/3.12 与 macOS Python 3.12；配置本身不代表这些环境已验证通过，结果以 Actions 实际运行为准。Windows 尚未验证。

## 扩展操作

先阅读 [实现指南](docs/IMPLEMENTATION.md)。在 sdk.py 的 Transport 添加接口调用，在 Client 添加输入检查与限时分派，然后添加 CLI 参数、capabilities 和文档。尽量保留上游业务字段，明确 ID、分页、认证需求与副作用，不提供任意 HTTP 写请求入口。

提交说明应包含：具体问题或新增操作、接口/SDK 路线、返回数据与分页方式、如何验证、尚未实测的范围。新的 SDK 定义不能直接标记为已支持；公开说明只有离线测试还是已进行有限真实操作。

离线测试应覆盖有意义的边界，例如参数转发、游标、重复页、错误脱敏、超时取消、凭证保护。不要为文案或简单配置增加只复述实现的测试。

## 凭证与账号

不要提交 Cookie、二维码、账号导出、日志、缓存或虚拟环境；不要要求别人在 Issue 中粘贴 Cookie。真实读取实验使用本人授权的账号，只输出脱敏状态与计数。写入测试默认使用 mock 或 --dry-run；真实评论、点赞、收藏或转发必须由账号所有者授权具体目标与内容，不能混入读取测试。投币会消耗账号硬币，必须单独得到具体目标与数量的授权；直播弹幕与纯文字动态同样不混入读取测试。文字私信已经实现，但真实发信仍需明确收件人 UID 与内容授权，不能在读取测试中顺带发信；不要公开消息正文。内容删除尚未实现。

Git 忽略规则不是安全检查的替代；提交前查看实际 diff 和待提交文件。遇到凭证泄露时先在本机停止使用并撤销相应会话，别把泄露值放到公开 Issue。可使用 GitHub 仓库启用的私密漏洞报告功能；如果该功能尚未启用，不要假定存在私密接收渠道。

## 构建与发布验证

```sh
python -m build
python -m twine check --strict dist/*
python scripts/audit_release.py dist
python -m pip install --force-reinstall --no-deps dist/*.whl
python scripts/smoke_install.py
python -m unittest discover -s tests -v
```

建议从干净工作副本构建，dist 中只保留待发布版本，以免验证旧包。archive audit 检查文件路径、导出类型与必要内容，不能保证发现源码里手工粘贴的所有敏感信息。正式发布前仍应查看代码与打包内容。

遵循 GPL-3.0-or-later，保留 LICENSE/NOTICE 与依赖来源；不要复制不明来源的实现。源码与安装包发布步骤见 [Alpha 发布说明](docs/RELEASE.md)。
