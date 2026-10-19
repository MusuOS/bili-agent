# v0.1 本地验证（2026-10-10）

- 独立 Python 3.10.20 临时环境，从项目目录安装成功，不依赖原 bilibili-cli 环境或硬编码解释器路径。
- 已生成 `dist/bili_agent-0.1.0-py3-none-any.whl`。检查 wheel：只包含包代码、许可证和包元数据，没有 Cookie、账号导出 JSON/JSONL、截图或日志。
- 21 项离线测试通过：分页终止、重复页、计数核对、直播规范化与停止、脱敏错误、会话文件保护、输出权限、离线能力发现。
- 安装后的新入口实测成功：status（已有会话有效）、video、live-info、my-dynamics、history、favorites、following、watch-later、feed、related、subtitles（轨道）、comments（单页）。只读取少量样本，业务数据没有纳入包。
- help/version、capabilities、doctor 与非法参数退出码/JSON 已检查。

本轮未重新跑全量评论、字幕正文下载或真实直播业务事件。全量评论与直播的既有实验边界见 README。未执行账号写入、首次登录、Cookie 刷新或 GitHub 发布。尚无多平台安装验证与外部用户验证。

# v0.2 扫码登录验证（2026-10-10）

- 新增 `login`，共 21 个命令。成功后使用自有 `~/.config/bili-agent/credential.json`，读取仍兼容旧实验会话。
- 安装后的 v0.2 wheel：28 项离线测试通过，覆盖等待扫码/确认、成功核验保存、0600 权限、既有会话保留、验证失败、过期、超时、未知状态及敏感字段不出现在事件中。
- 实际纯 HTTP 接口已成功生成二维码并返回等待扫码状态；适配当前 `account.bilibili.com` 二维码域名。
- 手机确认后的真实凭证保存与后续登录读取，需要本人的扫码才能完成端到端验证；不能以离线成功样例代替实测结果。
- 首次手机扫码已确认，但 CLI 因过严的回调链接域名/协议校验失败，未写入会话。已修复：登录回调仅作为 HTTPS 轮询结果中的数据解析，不访问其 URL；真正身份校验仍调用 HTTPS nav 接口。跨域回调回归测试通过，正在重新扫码验证。
- 后续实测发现当前成功轮询通过 HTTP Set-Cookie 返回凭证，回调链接不含完整凭证。已支持响应 Cookie，并保留旧格式回调兼容；新增回归测试，安装后的 29 项测试通过。
- 最终本人扫码确认成功，HTTPS nav 身份验证通过，会话已保存到用户配置目录，登录进程退出码 0。二维码结束后清理；实验旧凭证未被替换。
- 保存后重新启动 CLI：`status` 返回 valid，`history --size 1` 读取成功，均退出 0；凭证权限 0600，临时二维码已删除。纯 HTTP 首次登录到后续读取的端到端验证完成。

# v0.3 基础能力验证（2026-10-10）

- 按基础能力工具箱定位，移除未发布的 material 命令、素材包组合和 research 示例模块。保留上游业务字段，不生成分析或创作结论。
- 25 个 CLI 命令；新增 search、user、user-videos、user-dynamics。9 个 Python Client 读取方法与 CLI 共享实现，输入验证、脱敏错误、超时与取消均有测试。
- 从 wheel 安装到独立 Python 3.10 环境：38 项离线测试通过。已验证 capabilities 返回的文档与源码路径可读；wheel 含实现/Agent 指南，不含 research/models 模块、Cookie、账号 JSON、日志或二维码。
- 安装后的 CLI 实测：视频详情用于选择公开作者样本；status、search（2 条）、user、user-videos（2 条）、user-dynamics、comments（单页）、subtitles（轨道）全部退出 0、输出可解析 JSON，stderr 为空。
- Python SDK 四个新基础方法也已独立实测通过。该结果是有限账号与样本验证，不代表任意账号、地区和长期接口可用性。
- 本轮未执行账号内容写入或 GitHub 发布。全量评论、实时直播业务事件与新版全部分页末尾未重新采集验证。


# Alpha 发布准备（2026-10-10）

- 新增 GitHub CI：Linux Python 3.10/3.11/3.12，macOS Python 3.12；只读 GitHub token，不提供 B 站凭证，不执行账号联网测试。YAML 已本地解析，远端矩阵尚未运行。
- 新增 CONTRIBUTING、CHANGELOG、Release 说明、Issue/PR 模板；依赖显式声明二维码生成，包元数据标记 Alpha。
- 使用标准 python -m build 生成 sdist，再从 sdist 构建 wheel；twine --strict 元数据检查通过。archive audit 检查源码/安装包必要文件与导出类型，负例确认拒绝账号导出和路径穿越；不能代替人工审查源码是否手工包含秘密。
- macOS Python 3.10 与 3.11：安装候选 wheel 后，独立空目录检查入口、能力发现、安装文档、SDK 和凭证缺失错误；38 项离线测试通过。没有把配置的 Python 3.12/Linux CI 当作已通过。
- 候选包保存在 dist/alpha-0.3.0，附 SHA256SUMS；当前没有创建远端仓库、推送、GitHub Release 或 PyPI 上传。

# GitHub Alpha 发布验证（2026-10-10）

- 独立公开仓库：https://github.com/MusuOS/bili-agent。仅提交源码、文档、离线测试与 CI；没有账号凭证或实验导出。中文简介包含 B站、哔哩哔哩、小破站，Topics 使用平台支持的英文/拼音关键词。
- 首次远端工作流发现 job env 不支持 runner.temp 上下文；已修复。四个环境全部通过。
- Linux Python 3.10/3.11/3.12、macOS Python 3.12：38 项离线测试、sdist 到 wheel 构建、严格元数据检查、归档审计、安装入口/文档/SDK 检查与安装后重测均通过。CI 没有 B 站凭证，不把离线测试等同于新增账号功能实测。
- v0.3.0 以 GitHub Alpha Pre-release 提供 wheel、sdist 和 SHA256SUMS；PyPI 未发布。前文“尚未发布”等内容记录对应阶段的历史状态。

# v0.4 写入基础能力（2026-10-10）

- 增加六项 CLI / SDK 写入，共 31 个命令和 15 个 SDK 方法。
- 本地 51 项离线测试通过；新增写入参数映射、无凭证/网络预览、无会话/CSRF、aid 前置失败、超时不重试和脱敏结果。
- 没有使用真实凭证执行发评论、点赞、收藏或转发。新能力的验证状态为 offline_only_not_live_verified。
- 前述 GitHub CI 与登录读取结果对应此前提交；本版本远端结果应以对应 Actions run 为准。

# v0.5 常用基础操作（2026-10-10）

- 新增 12 项操作：7 写、5 读；总计 43 命令、27 个业务 SDK 方法。
- 本地 64 项离线测试通过：新增关系正反枚举、直播短号解析委托、视频 P/六分钟片段映射、视频弹幕参数、纯文本动态、投币与稍后再看映射，以及 CLI 分派与缺会话边界。
- 所有新增写入均未执行真实账号互动，也没有消耗账号硬币。五项新读取也只离线测试，能力发现已标明。
- 原登录、评论读取与直播监听实验仍保留原样本边界；代理/CA 适配未修复。远端构建和安装结果以对应 v0.5 Actions run 为准。

# v0.6 私信（2026-10-10）

- 新增五项私信基础操作，共 48 个命令、32 个业务 SDK 方法。76 项离线测试通过：游标省略与零值、时间戳与序列号映射、请求参数、文字 JSON 编码、真实 sender 身份查询、WBI -403 单次发送与错误脱敏。
- 使用已保存的本人会话做少量纯 HTTP 读取：dm-sessions(size=1) 返回一项，dm-new(当前微秒时间戳,size=1) 返回空列表，选择既有用户会话后的 dm-session 与 dm-history(size=1) 均成功。只输出状态和数量，不显示消息正文／UID，也未保存消息到文件。
- 没有执行真实发信、已读确认、撤回、删除或自动回复；发送仍为 offline_only_not_live_verified。游标分页末尾、多 kind、积压消息完整恢复未实测。
- 新包审计要求 messaging.py 和离线测试出现在对应归档；真实消息与凭证不会被纳入包。远端 CI/安装结果以本提交 Actions 为准。

## v0.6.1 代理与 Agent 易用性

- 85 项测试通过，包含新增 9 项代理测试；不访问外部网络或账号。本机临时 HTTP 代理实际转发 SDK 和登录 HTTP 请求，验证无 scheme 的 https_proxy 与统一选择规则。环境优先级、NO_PROXY 限制、错误脱敏、配置幂等与离线 dry-run 也覆盖。
- 全部命令增加 --help 示例，写入示例使用 --dry-run；related 展示 BV 与完整 URL。文档强调 total 不能证明评论完整，需要检查 complete 与 issues。
- SSL 校验没有关闭；Muse 原始 SSL 问题、HTTPS CONNECT、代理 TLS 与自定义 CA 未验证。不是对其运行时故障已解决的声明。没有新增真实账号写入实测。
- wheel/sdist 审计要求包含 network.py，sdist 包含 test_network.py；远端四环境构建、安装与测试结果以本提交 Actions 为准。
