# v0.6.1 Alpha 发布说明

bili-agent 是供 Agent 直接使用、阅读和扩展的 B 站基础能力工具箱。当前可作为早期 Alpha 分享源码与安装包；不承诺 B 站全能力或长期稳定。

## 本次交付

- 48 个 CLI 命令和 32 个 Python SDK 方法（18 读、14 写）。
- 纯 HTTP 扫码登录，复用本地会话；不把 Cookie 放在命令行或输出中。
- 业务数据与分页由调用者处理；机器能力发现、JSON 外层、脱敏错误与退出码明确。
- 附接口、认证/签名、代码结构和扩展方法说明。Agent 自行组合业务与二创。

本次补丁统一环境代理配置，给所有命令补 --help 示例，并强调评论 total 不是完整性依据。85 项本地测试通过；代理证书问题在 Muse 环境仍待验证。详情见 README。

## 安装

下载并解压发布源码，进入含 pyproject.toml 的目录：

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install .
bili-agent capabilities
bili-agent login
bili-agent status
```

已有 `bili_agent-0.6.1-py3-none-any.whl` 的用户也可在已激活的环境安装该文件。首次安装依赖通常需要联网；读取实验与扫码登录也需要访问 B 站。无需部署服务器。公开仓库为 https://github.com/MusuOS/bili-agent，新仓库保留版本标签，但暂未发布 GitHub Releases 安装附件；PyPI 尚未发布。

## 已知边界

Python 最低版本为 3.10。本地验证与 CI 配置分别记录在 VALIDATION.md 和 .github/workflows/ci.yml；只有实际执行成功的环境才能标为通过。Windows 尚未验证。

公开接口返回值可能变动，风控和账号权限可能使请求失败。SDK 上游已停止维护。直播认证成功不代表业务事件已验证；评论采集必须检查 complete，不保证能读取被隐藏/删除的评论。没有续采或自动刷新；十四项写入只通过离线测试，默认真实执行，可加 --dry-run 离线预览。

## 发布到 GitHub 时

本节是维护者的手动发布流程，CI 只验证与构建，不自动上传 Release 或 PyPI。

1. 以 bili-agent 目录为独立仓库根目录；不要把其他平台实验、虚拟环境、用户配置或导出数据一起上传。
2. 按 CONTRIBUTING.md 构建源码包与 wheel，验证元数据、归档内容和独立安装。查看待提交文件与 diff，确认只有公开项目内容。
3. 推送到 MusuOS/bili-agent 后，等待全部 CI jobs 通过；若失败，修复或准确缩小支持范围。CI 不使用 B 站 Cookie，也不运行真实账号测试。
4. 记录对应提交，再创建 v0.6.1 标签和 GitHub Release，并勾选 Pre-release。附上该提交验证过的 wheel、源码包和 SHA256 校验信息；发布正文可基于本文件与 CHANGELOG。
5. 填写真实仓库地址、维护者联系渠道与项目元数据。仓库创建、公开、推送、Release 和 PyPI 上传属于实际发布操作，只有明确执行发布时才进行；当前不配置自动上传。

私信四个读取接口已经有限样本实测；文字发送未真实发信。阅读 README 的私信游标与消息隐私说明。发送无送达／已读保证；支持 --dry-run，不重试。
