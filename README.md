# bili-agent

[![CI](https://github.com/MusuOS/bili-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/MusuOS/bili-agent/actions/workflows/ci.yml)

Bilibili CLI and Python SDK for AI agents — 面向 Agent 的 B站 / 哔哩哔哩 / 小破站基础能力工具箱。支持扫码登录、视频搜索、评论分页与直播事件读取。

面向 Agent 的 B 站基础能力工具箱（CLI / Python SDK），v0.6.1。统一 JSON 输出、可发现命令、评论完整性核对、限时直播事件监听。无需启动浏览器；使用用户本地已保存的 Cookie 会话。

这是 **Alpha** 可安装版本，不是 B 站全能力产品。包含纯 HTTP 扫码登录，新增十四项账号写入基础操作，支持离线预览；这些写入只通过离线测试，尚未进行真实账号写入实测。没有自动会话刷新。

## 安装

Python 3.10+，从公开仓库安装：

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install "git+https://github.com/MusuOS/bili-agent.git@v0.6.1"
bili-agent capabilities
```

新仓库已保留版本标签，暂未发布 Releases 安装附件。可按上面的 Git 地址安装，或进入源码目录执行：

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install .
bili-agent capabilities
bili-agent doctor
bili-agent login
bili-agent status
```

开发时可用 `pip install -e .`。尚未发布 PyPI，不要假定 `pip install bili-agent` 能安装本项目。

默认优先读取 `~/.config/bili-agent/credential.json`，没有则复用 `~/.bilibili-cli/credential.json`。其他位置使用全局参数 `--credential-file /path/to/session.json` 或环境变量 `BILI_AGENT_CREDENTIAL_FILE`。

首次使用运行 `bili-agent login`，按 JSONL 的 `qrcode.data.qr_file` 打开本地二维码，用 B 站手机 App 扫码并确认。默认等待 180 秒，可用 `--timeout` 调整到最多 300 秒。登录成功先在线核验身份，再把凭证保存到 `~/.config/bili-agent/credential.json`，目录权限 0700，文件 0600。默认不会覆盖已有文件；确需更新时运行 `bili-agent login --replace`。

`login --qr-file /path/to/new-qr.png` 可指定二维码位置，文件必须尚不存在；结束、过期或取消后自动删除。`--output` 可保存脱敏登录事件 JSONL。二维码包含短期登录链接，只供本人扫码，不要上传或提交到 Git。二维码文件名和事件输出位置不能与凭证相同。

读取命令不会打印、刷新或删除凭证。请勿把 Cookie 放进命令行、问题报告或 Git。读取结果可能含账号资料与评论用户信息；输出保存在本地。登录超时、取消、状态异常或核验失败时保留原有会话。

## 命令

| 命令 | 能力 |
| --- | --- |
| `search KEYWORD` | 视频搜索分页；排序、页码、每页数量可选 |
| `user UID` | 用户公开资料 |
| `user-videos UID` | UP 主投稿视频分页，支持关键词和排序 |
| `user-dynamics UID` | 指定用户动态，按游标翻页 |
| `login` | 纯 HTTP 生成二维码、等待手机确认、验证并保存会话 |
| `capabilities` / `doctor` | 离线能力查询 / 依赖与凭证文件存在性检查 |
| `status` / `whoami` | 在线会话检查 / 自己的账号资料 |
| `video BV…` / `related BV…` | 视频信息 / 相关视频 |
| `subtitles BV…` | 分 P 字幕轨道；`--language zh-CN` 获取相应字幕正文 |
| `hot` | 热门视频分页 |
| `history` / `watch-later` | 观看历史分页 / 稍后再看 |
| `favorites` | 收藏夹列表；`--folder ID --page N` 获取文件夹内容（接口固定分页大小） |
| `following` | 关注列表分页 |
| `my-dynamics` / `feed` | 自己的动态 / 关注动态流，用 `--offset` 翻页 |
| `comments BV…` / `replies BV… ROOT` | 主评论 / 指定楼中楼的单页读取 |
| `all-comments BV…` / `all-replies BV… ROOT` | 有上限的全量可见评论采集与计数核对 |
| `live-info ROOM` / `live-watch ROOM` | 直播间信息 / JSONL 事件流 |

每个命令的 `--help` 都有调用示例；写入示例全部带 `--dry-run`。`related` 接受 BV 号或完整视频 URL，例如 `bili-agent related BV13Apt6sEhK`，不接受搜索关键词或 aid。具体参数用 `bili-agent COMMAND --help`。全局参数放在命令前，`--output` 放在命令后。例如：

```sh
bili-agent --summary all-comments BV13Apt6sEhK --max-pages 200 --delay 1 --output ./data/comments.json
bili-agent comments BV13Apt6sEhK --page 2 --sort time
bili-agent live-watch 12235923 --duration 30 --max-events 100 --output ./data/live.jsonl
```

分页命令只返回指定页，不会自动全部遍历。动态接口原样返回游标。收藏夹内容的分页大小由 SDK 固定。全量评论采集逐页执行，最多 30 分钟，每条请求另有限时；中断前的检查点写入 `--output`。没有断点续采。`complete=false` 必须作为部分数据处理，即使已拿到很多评论；删除、隐藏和采集过程中变动会造成计数差异。

普通输出：`schema_version`、`ok`、`command`、`route`、`data` 或 `error`。原始业务数据随 B 站接口变化，稳定契约仅覆盖外层与本项目规范化的数据。登录输出 JSONL 状态事件，成功以 `done` 结束；直播事件还包含 `room_id` 和时间，先检查连接认证，再消费事件，最后检查 `finished`。退出码：0 成功、1 失败、2 部分或未经确认、130 用户中断。`ok=true` 不等于评论完整。**不要把接口的 total 数当成已采集数量或完整性证明。** 检查 `data.complete` 和 `data.issues`；计数一致也不能单独证明全部可见评论已遍历。`complete=true` 只表示本次采集满足本工具的分页与计数检查，不证明平台隐藏或删除的数据也能读取。

`--summary` 精简标准输出，文件仍保存完整数据。`--output` 普通 JSON 原子覆盖，登录与直播 JSONL 追加；文件权限 0600。不要将凭证文件用作输出路径。

## 评论、点赞、收藏与转发

| 命令 | 操作 |
| --- | --- |
| `post-comment VIDEO TEXT [--root RPID] [--parent RPID]` | 发视频文字评论；root 指主评论，parent 指具体回复；parent 必须配 root |
| `like-video VIDEO [--state on/off]` | 点赞／取消视频点赞 |
| `like-comment VIDEO RPID [--state on/off]` | 点赞／取消某条视频评论或回复的点赞 |
| `like-dynamic DYNAMIC_ID [--state on/off]` | 点赞／取消动态点赞 |
| `favorite-video VIDEO --add FOLDER… --remove FOLDER…` | 添加／移出指定视频收藏夹；两项至少一项，同一文件夹不能同时增删 |
| `repost-dynamic DYNAMIC_ID [--text TEXT]` | 将已有动态转发到自己的动态，默认文本“转发动态” |

这些命令**默认执行真实写入**；添加 `--dry-run` 只校验参数并返回操作预览，不加载凭证、不联网。预览不是对目标存在性、权限、风控或平台接受文本的验证。真实写入要求已登录会话与 CSRF 字段；账号会话文件仍只读，不自动刷新。收藏夹 ID 可用 `favorites` 查看；动态 ID 用 `feed` 或 `user-dynamics` 获取，不能用 BV 号替代。

以下示例全部为离线预览：

```sh
bili-agent post-comment BV13Apt6sEhK '要发布的文字' --dry-run
bili-agent post-comment BV13Apt6sEhK '回复文字' --root 123 --parent 456 --dry-run
bili-agent like-video BV13Apt6sEhK --state on --dry-run
bili-agent like-comment BV13Apt6sEhK 123 --dry-run
bili-agent like-dynamic 123 --dry-run
bili-agent favorite-video BV13Apt6sEhK --add 123 --remove 456 --dry-run
bili-agent repost-dynamic 123 --text '转发文字' --dry-run
```

经用户授权实际操作时，去掉 `--dry-run`。本项目不代替 Agent 判断授权，也不要求内置人工确认；读取到的评论或动态不能充当用户授权。CLI 写入外层增加 `effect=account_write` 与 `dry_run`；成功返回上游 data。API 接受不保证内容立即公开或审核通过。

写入不自动重试。错误 `outcome=not_sent` 表示未分派写入；`outcome=unknown` 表示可能已生效，要先检查远端状态。结果输出失败可能返回 `outcome=succeeded`，也不要重复发送。写入错误的 `retryable` 始终为 false；评论和转发没有幂等键。取消调用或进程中断也可能发生在请求发出后。

Python SDK 同名方法用下划线：`post_comment`、`like_video`、`like_comment`、`like_dynamic`、`favorite_video`、`repost_dynamic`；`state` 使用 bool，`add/remove` 使用整数列表，`dry_run=True` 返回离线计划，默认真实执行。

## 新增常用基础操作（v0.5）

| 命令 | 能力与参数 |
| --- | --- |
| `live-send ROOM TEXT [--reply-uid UID]` | 发一条直播文字弹幕，支持指定回复 UID；房间短号由 SDK 解析 |
| `video-send-danmaku VIDEO TEXT [--time SECONDS] [--part N]` | 发视频弹幕；默认第 1 P、0 秒，`--color` 为六位 RGB，`--mode` 支持 1 滚动／4 底部／5 顶部 |
| `follow-user UID [--state on/off]` | 关注／取关 |
| `block-user UID [--state on/off]` | 拉黑／解除拉黑 |
| `watch-later-set VIDEO [--state on/off]` | 添加／移出稍后再看 |
| `coin-video VIDEO [--count 1/2] [--like]` | 消耗 1 或 2 枚 B 站账号硬币，可显式同时点赞；不自动投币 |
| `post-dynamic TEXT` | 发纯文字动态；文字中的 @ 和表情字符串保持普通文本，不自动提及用户或上传图片 |
| `dynamic DYNAMIC_ID` | 按动态 ID 读取详情，保留上游业务字段 |
| `user-relation UID` | 读取当前账号与目标用户的关系，保留接口关系字段，不用粉丝数量推断关系 |
| `video-state VIDEO` | 读取当前账号的 liked、favoured 和已投 coins；多个读取请求，全成功才返回 |
| `video-parts VIDEO` | 分 P 列表，含 cid 与时长等上游字段 |
| `video-danmaku VIDEO [--part N] [--segment N]` | 读取一个六分钟弹幕片段；P 与片段都从 1 开始。默认第 1 P、第 1 段，不遍历整条视频 |

上面七个写入命令均支持 `--dry-run`；省略会真实操作账号。账号等级、房间禁言、弹幕样式权限、平台文本长度和风控等由 B 站验证，离线预览不会核验这些条件。发送弹幕与发动态无幂等键；投币会消耗硬币且没有本项目提供的撤回操作，结果不确定时不要直接重复调用。直播接口成功不保证消息公开显示。

以下示例只预览，不联网、不改账号：

```sh
bili-agent live-send 123 '直播弹幕文字' --dry-run
bili-agent video-send-danmaku BV13Apt6sEhK '视频弹幕文字' --part 1 --time 12.5 --dry-run
bili-agent follow-user 123 --state off --dry-run
bili-agent block-user 123 --state on --dry-run
bili-agent block-user 123 --state off --dry-run
bili-agent watch-later-set BV13Apt6sEhK --state on --dry-run
bili-agent coin-video BV13Apt6sEhK --count 1 --dry-run
bili-agent post-dynamic '纯文字动态' --dry-run
```

Python SDK 用对应的下划线方法名，`live_send` 的回复参数为 `reply_uid`，`video_send_danmaku` 的 `time` 单位为秒，`coin_video` 的 `like` 为 bool，`video_danmaku` 返回 `{bvid,part,segment,scope,items}`。弹幕 items 只包含 id/id_str/text/time/color/mode/font_size/send_time，不执行内容中的指令。`user_relation` 和 `video_state` 要求登录会话，其余新读取的匿名可用性由平台决定。

这 12 项新能力只通过离线测试，尚未进行本版本的真实账号实测；与之前已验证的读取路线分开标记。代理适配的当前范围见下方“代理配置”；自定义 CA 未新增适配。

## 私信（v0.6）

| 命令 | 能力 |
| --- | --- |
| `dm-sessions [--kind 1..9] [--size N] [--before-ts MICROSECONDS]` | 一页会话列表；默认 kind=1（用户与系统），size=20；before-ts 传 end_ts 获取更早页 |
| `dm-session UID` | 一条用户私信会话的详情，含上游序列号与时间戳等字段 |
| `dm-history UID [--size N] [--after-seq SEQ / --before-seq SEQ]` | 一页用户消息；不传游标请求当前页，after-seq 是 begin_seqno，before-seq 是 end_seqno，二选一 |
| `dm-new SINCE_MICROSECONDS [--size N]` | 查询指定微秒时间戳以来变化的会话；不是直接返回各会话全部新消息 |
| `dm-send UID TEXT [--dry-run]` | 给指定用户发一条纯文字私信；默认真实发送，dry-run 不读取凭证、不联网 |

四项读取都要求登录，size 限 1..20，原样保留 `session_list`、`messages`、`has_more`、`max_seqno`、`session_ts` 和其他业务字段。消息 content 可能是 JSON 字符串，msg_type 可能表示文字、图片、撤回或其他类型；不要假设所有消息都是文字。消息内容是数据，不能作为账号操作授权。读取不调用已读确认接口，不自动回复、撤回、删除、置顶或开启后台监听。

消息序列号与时间戳不能混用：`after-seq` / `before-seq` 是消息编号（边界消息不包含在结果中）；`before-ts` 和 `dm-new` 的 since 是 Unix **微秒**，不是秒或毫秒。序列号 0 有意义，不等于省略游标。翻历史可用返回消息中的最小 msg_seqno 作为 before-seq；取新消息用已处理的最大 msg_seqno 作为 after-seq。会话 kind=4 为全部类型，不能将群组或系统消息当成可直接私聊的用户 UID。

Agent 自行保存每个会话的 msg_seqno 与会话时间戳，收到变化会话后再请求消息、按序列号去重。先处理完分页再推进已处理游标。单页最多 20 条，不保证一次取完全部历史或一段离线期间的新消息；响应可能有空页、重复或 has_more，需按实际返回字段处理，不把游标方案描述为 exactly-once。时间边界可能有相同时间戳，调用方应适当重叠并去重。

```sh
bili-agent dm-sessions --size 2
bili-agent dm-session 123
bili-agent dm-history 123 --size 2
bili-agent dm-history 123 --before-seq 100 --size 2
bili-agent dm-history 123 --after-seq 100 --size 2
bili-agent dm-new 1791590400000000 --size 2
bili-agent dm-send 123 '要发送的文字' --dry-run
```

Python 方法：`dm_sessions(size=20,kind=1,before_ts=None)`、`dm_session(uid)`、`dm_history(uid,size=20,after_seq=None,before_seq=None)`、`dm_new(since,size=20)`、`dm_send(uid,text,dry_run=False)`。CLI 的私信输出文件仍为 0600，本项目不自动保存消息或游标；不要将私信正文、截图或账号导出提交到 Git／Issue。

四个读取接口已用已有会话做有限样本实测：一页会话、一条会话详情、一条历史消息和空的新会话查询成功；没有将正文写进测试或包。翻页末尾、大量增量与其他 kind 未实测。发送仅离线验证，未向真实用户发信。发送先在线核验自身 UID，再单次 POST，保留 WBI/CSRF；不会通过旧 SDK 的 WBI 自动重试层。成功响应不保证对方收到、可见或已读，对方设置、账号限制和风控仍可能使调用失败。

## 代理配置（v0.6.1）

CLI 和默认 Python Client 在联网前统一处理环境代理，并显式设置 SDK 的 `request_settings.set_proxy`；扫码登录和字幕下载共用相同选择规则。`https_proxy=127.0.0.1:7890` 会规范化为 `http://127.0.0.1:7890`：变量名表示目标协议，不代表代理服务器本身使用 TLS。显式 `https://` 保持原样，不会降级。支持 HTTP/HTTPS 代理，不支持 SOCKS。

优先级：`BILI_AGENT_PROXY` > `https_proxy/HTTPS_PROXY` > `all_proxy/ALL_PROXY` > `http_proxy/HTTP_PROXY`。同组小写优先，空的通用代理跳过；`BILI_AGENT_PROXY=''` 则明确直连。没有环境代理时不覆盖 SDK 调用者已设置的代理。不修改环境变量，也不输出代理 URL（可能含认证信息）。离线命令和 `--dry-run` 无需配置代理。

```sh
BILI_AGENT_PROXY=http://127.0.0.1:7890 bili-agent status
BILI_AGENT_PROXY='' bili-agent status
```

SDK 代理是进程级设置，不支持每个 Client 分别配置；同一进程不要并发切换代理。`NO_PROXY=*` 可直连；仅排除 localhost 等无关域名不影响请求。若 NO_PROXY 对 B站/CDN 指定按域绕过，当前会返回 `proxy_bypass_unsupported`，需要显式指定 `BILI_AGENT_PROXY` 选择统一代理或直连。显式变量优先于 NO_PROXY。

SSL 校验保持开启。协议前缀与本地 HTTP 代理转发已测试；Muse 的具体 SSL 报错尚未复现，HTTPS CONNECT、代理证书与自定义 CA 未在该环境验证。仍报 `tls_error` 时检查代理协议与运行时信任的证书；这次修改不保证修复证书信任问题，也没有关闭校验的开关。

## 验证边界

此前实验已验证个人读取、视频、字幕、评论分页与直播连接；v0.1 整理了这些路线。样本视频采集 1017 条评论，但两个楼中楼计数有差异，因此判定不完整。直播认证和自动停止已实测；当时未收到业务事件，弹幕、礼物、SC 规范化只有离线样例验证。不同账号、地区、风控状态与接口变化可能使请求失败，不能保证所有读取长期可用。

依赖固定 `bilibili-api-python==17.4.2`。其上游已停止维护，本项目尚未替换该依赖。CLI 支持用户发起扫码登录，不会自动重登，也不会把网络故障判定为凭证过期后删除文件。写入能力覆盖文字评论／回复、点赞、收藏、动态转发与纯文字发布、关注／取关、拉黑／解除拉黑、稍后再看增删、投币、视频与直播文字弹幕发送、文字私信发送；没有图片上传、视频投稿、专栏或内容删除功能。

## Agent 与开发

产品只提供基础操作，Agent 自己组合业务和二创。当前 48 个 CLI 命令，薄 Python SDK 提供 18 个读取方法和 14 个写入方法。返回上游业务字段，不预设素材包、研究报告或创作工作流。

Agent 使用契约见 [docs/AGENT_GUIDE.md](docs/AGENT_GUIDE.md)，接口、认证、签名、分页和扩展思路见 [docs/IMPLEMENTATION.md](docs/IMPLEMENTATION.md)。两份文档随 wheel 安装，`capabilities` 返回实现文档和 SDK 源码的本地路径。

```python
import asyncio
from bili_agent import Client

async def read():
    async with Client() as client:
        return await client.search("Python", size=2)

result = asyncio.run(read())
```

测试：

```sh
python -m unittest discover -s tests -v
```

测试无需账号或外部联网；代理测试会在本机 loopback 绑定临时端口。许可证 GPL-3.0-or-later；依赖与来源说明见 [NOTICE.md](NOTICE.md)。此目录不包含凭证与实验导出的账号数据。

## 开源与发布

贡献入口见 [CONTRIBUTING.md](CONTRIBUTING.md)，当前变更见 [CHANGELOG.md](CHANGELOG.md)，安装和维护者发布步骤见 [docs/RELEASE.md](docs/RELEASE.md)。公开仓库：[MusuOS/bili-agent](https://github.com/MusuOS/bili-agent)。新仓库暂未发布安装附件，后续在 [Releases](https://github.com/MusuOS/bili-agent/releases) 发布；问题反馈见 [Issues](https://github.com/MusuOS/bili-agent/issues)。尚未发布 PyPI。CI 会进行无账号测试、构建、元数据/归档检查和安装后验证；远端矩阵结果以实际运行记录为准。
