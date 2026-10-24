# NapCat / SnowLuma + AstrBot VPS Skill

供具备文件读取、终端和 SSH 能力的 Agent 使用的 Linux VPS 部署 Skill，覆盖 **NapCat 或 SnowLuma + AstrBot** 的部署、检查、修复与迁移。

基础目标是 QQ → 协议端 → OneBot v11 → AstrBot → 实际回复。仓库提供 Agent 指令、Compose 模板、只读检查脚本和可选邮件监控，不包含 QQ 账号数据、上游程序或 Docker 镜像。

## 能做什么

- 在已有 VPS 上先检测系统、资源、Docker、端口与现有服务，再选择安装或修复路径。
- NapCat 与 SnowLuma 分支分开处理，避免混用配置目录、扫码方式和专有 API。
- WebUI 与 OneBot HTTP 默认只绑定宿主机回环地址，反向 WebSocket 走容器内部网络。
- **可选域名登录**：Cloudflare Tunnel + Access，包含精确主机名、身份策略和回源 JWT 校验。
- **可选邮件告警**：Resend 发送 QQ 会话掉线/恢复邮件，包含连续采样、冷却、去重和失败队列。
- 区分脚本检查、现场检查和用户真实收到回复/邮件，不以容器运行代替端到端验收。

## 两个独立可选项

Agent 必须先询问是否需要域名便捷登录、是否需要邮件告警；本次会话已明确的回答不重复询问。不能因为已有域名就默认启用，也不能从其他实例复制账号或凭据。

| 选择 | 需要确认的条件 |
|---|---|
| 仅基础部署 | VPS、SSH/运维权限、目标 QQ 与手机授权、可用的 Docker/网络资源 |
| 域名 WebUI | 自有域名、Cloudflare 账号、DNS 管理权限、子域名和 Access 身份 |
| 掉线邮件 | Resend 账号、已验证的发信域名或验证 DNS 的条件、收件邮箱、私密输入发送 Key 的方式 |

两项均可不选。邮件不依赖 WebUI 域名或 Cloudflare；发信域名可独立，DNS 也可由其他服务商管理。条件不足时，基础部署仍可继续。

## 使用方式

### 支持 Agent Skills 的客户端

将本仓库完整内容放入客户端的 Skill 目录，文件夹名称使用 **`astrbot-napcat-vps`**，再按客户端方式加载。保留这个名称是为了兼容原调用名；内容同时支持 SnowLuma。

```bash
git clone https://github.com/XuanbaoSleepy/astrbot-qq-vps-skill.git astrbot-napcat-vps
```

在支持该调用语法的客户端中：

```text
使用 $astrbot-napcat-vps，在新的 Linux VPS 上部署 SnowLuma + AstrBot。
先确认可选域名与邮件需求，再检测环境并完成所选范围的部署和验收。
```

### 其他 Agent

无需特定客户端或插件：提供仓库文件，让 Agent 从 [SKILL.md](SKILL.md) 开始读取，并授予完成任务所需的终端/SSH 权限。`agents/openai.yaml` 是可选的客户端显示元数据，核心流程不依赖它。

例如：

```text
读取本目录 SKILL.md，部署 NapCat + AstrBot。我只使用 SSH 管理，不需要域名和邮件。
```

```text
读取本目录 SKILL.md，检查现有 SnowLuma + AstrBot，只修复 OneBot 通信。
```

```text
读取本目录 SKILL.md，迁移现有 QQBot，保留旧机回滚窗口；域名与邮件分别确认。
```

安装 Skill 不会自动连接服务器或执行部署。目标 VPS 以 Linux、Docker Compose 和 systemd 流程为主；其他发行版、架构及镜像版本仍需现场核对。客户端可以在 Windows、macOS 或 Linux 上运行，实际能力取决于所用 Agent 的工具与权限。

## 文件结构

```text
SKILL.md                  Agent 入口和需求确认规则
agents/openai.yaml        可选客户端元数据
references/workflow.md    共用流程与可选范围
references/deployment-guide.md  NapCat 详细流程
references/snowluma.md    SnowLuma 分支
references/cloudflare.md 可选域名入口
references/monitoring.md  可选邮件与覆盖边界
references/troubleshooting.md   故障排查
assets/                  Compose、环境变量示例与 systemd 模板
scripts/                 预检、验证、监控和离线测试
```

`assets/compose.yaml` 对应 NapCat，`assets/compose-snowluma.yaml` 对应 SnowLuma。示例中的变量必须从目标环境检测或由用户提供，不能直接作为生产配置运行。

## 检查与测试

Python 检查脚本使用标准库。以下测试使用本地 fixture 和 mock，不连接 QQ、Docker、Cloudflare 或 Resend，不发送真实邮件：

```bash
python3 -B -m unittest discover -s scripts -p 'test_*.py'
```

Windows 可使用：

```powershell
python -X utf8 -B -m unittest discover -s scripts -p 'test_*.py'
```

目前包括 NapCat 兼容、SnowLuma 状态探测、告警状态机和独立可选范围测试。只读检查的参数说明：

```bash
bash scripts/preflight.sh --help
python3 scripts/verify.py --help
```

`preflight.sh` 默认不探测可选 Cloudflare/Resend 端点；选择后分别添加 `--with-cloudflare`、`--with-resend`。`verify.py` 保留旧 NapCat 参数别名，新增 `--gateway-type napcat|snowluma`；基础验证不要求邮箱、Key 或 cloudflared。

## 隐私与运行数据

- 仓库只包含通用文本、模板和测试数据；示例邮箱使用保留的无效域名，不包含实际服务器、QQ、邮箱、密钥或私有会话链接。
- 真正的 `.env`、QQ 登录态、API Key、Token、监控状态、日志和备份应保存在仓库外的目标私有目录；不要提交到 GitHub。
- 预检会按所选范围访问软件源或服务端点。启用邮件后，会经 Resend 将状态、时间、服务器主机名及固定原因文本发送到用户配置的收件邮箱；代码没有向仓库维护者回传数据的逻辑。
- 仓库内的 `.gitignore` 用于减少误提交，不能代替发布前逐文件检查。若自行保存本机密码、截图或新配置，仍需独立检查。

## 验证范围

QQ 会话邮件默认每两分钟采样，三次确认离线告警、两次在线恢复。单独 OneBot 断连属于诊断信息；持续 unknown、监控停止、整机断网/宕机没有独立外部告警，外部心跳需另行设计。

公开流程来自匿名化部署经验和官方文档。过去的成功实例、离线测试和模拟邮件都不能保证新服务器免扫码、所有平台一致，或代替自然掉线、重启、媒体消息和真实设备验收。

上游文档：[NapCat](https://github.com/NapNeko/NapCatQQ)、[SnowLuma](https://github.com/SnowLuma/SnowLuma)、[AstrBot](https://github.com/AstrBotDevs/AstrBot)、[Cloudflare Tunnel](https://developers.cloudflare.com/tunnel/)、[Resend](https://resend.com/docs)。
