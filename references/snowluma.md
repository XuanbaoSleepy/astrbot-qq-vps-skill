# SnowLuma + AstrBot 分支

依据 2026-10-24 的 Debian 12 / amd64 实际部署：SnowLuma 2.1.1、AstrBot 4.29.1。该版本快照不是固定版本要求；后续部署重新核对官方稳定版、Docker 镜像发布版本和摘要。该实例的域名、账号、邮箱和凭据不属于通用模板。

## 前提与 Compose

先完成 [workflow.md](workflow.md) 的两项可选需求询问；没有域名或邮件也可用 SSH 完成部署。

使用 `assets/compose-snowluma.yaml` 与 `.env.snowluma.example`，填用户选择的空目录、唯一容器名和检测出的空闲端口。官方镜像源候选 `motricseven7/snowluma`，AstrBot 候选 `soulter/astrbot`；若通过镜像服务获取，确认仍是上游项目产物并固定正确架构的 registry digest，不把本机 image ID 当 RepoDigest。

当前 Docker 框架需要 `SYS_PTRACE`、`seccomp=unconfined` 和 1 GiB shm；新版镜像为 Node 设置 file capability，不因此降低宿主机 `kernel.yama.ptrace_scope`。先按当前镜像核对需求，不能把这些容器设置扩大成 privileged、host PID 或无关宿主机修改。

| 容器端口 | 用途 | 模板发布 |
|---|---|---|
| 5099 | SnowLuma WebUI | 仅宿主机回环 |
| 6081 | noVNC / QQ 扫码 | 仅宿主机回环，临时 SSH 转发 |
| 3000 | OneBot HTTP 探测 | 仅宿主机回环 |
| 3001 / 5900 | 正向 WS / 原生 VNC | 不发布；需要的反向 WS 走内部网络 |
| 6185 / 6199 | AstrBot WebUI / 反向 WS | 6185 仅回环，6199 不发布 |

持久化 `snowluma/data → /app/data`、`snowluma/qq-config → /app/.config`、`snowluma/qq-share → /app/.local/share`、`astrbot/data → /AstrBot/data`。按实际 UID/GID 建目录；SnowLuma 常用 1000，但以镜像配置为准，不用 chmod 777。模板将 AstrBot temp 只读映射到 SnowLuma 的相同绝对路径，用实际 QQ 运行用户测试可读性；这不等于已验收图片/文件往返。

```bash
docker compose --env-file .env -f compose.yaml config --quiet
docker compose --env-file .env -f compose.yaml pull
docker compose --env-file .env -f compose.yaml up -d
```

上面假定已将所选模板复制为目标的 compose.yaml；不直接运行未填写的资产模板，不覆盖已有 Compose 或数据。

## 初始密码与扫码

先用本机回环 HTTP 验证首页及静态资源；读取配置/日志时只报告状态与布尔值，原始初始密码在用户自己的私有终端查看：

```bash
docker logs "$GATEWAY_CONTAINER" 2>&1 | grep -F 'initial credentials' | tail -n 1
docker logs "$GATEWAY_CONTAINER" 2>&1 | grep -Fi 'remote desktop password:' | tail -n 1
docker logs "$ASTRBOT_CONTAINER" 2>&1 | grep -i 'initial password' | tail -n 1
```

这些日志标记来自已验证版本，升级后可能改变；不要把找不到标记当成可重置登录态的理由。SnowLuma 未完成首次改密时，重启可能重新生成 bootstrap password，使用当前有效值；noVNC 密码通常随持久化数据保留，以用户已修改值为准。

**[USER ACTION REQUIRED]** 先确认目标 QQ，再用 SSH 转发本机地址到服务器回环 noVNC。用户连接桌面、核对手机当前 QQ 并扫码，登录 WebUI 后完成其引导及密码修改。SSH `-N` 空白正常，窗口需要保持；不要把 noVNC 直接开放公网。若另选 noVNC 域名，也属于明确选择的额外 Access/路由，不能沿用未经保护的通配主机名。

## OneBot 配置与实际状态

不要设置 NapCat 的 `MODE=astrbot` 或挂载 NapCat 目录。当前 SnowLuma 网络配置使用 `config/onebot.json` 的全局 defaults 与 `onebot_<uin>.json` 的账号覆盖，适配器在 `networks` 下。账号文件可能只存部分覆盖，数组空/缺字段不能证明当前适配器没启动；核对有效全局配置和 live API，避免为此覆盖健康账号配置。

反向连接目标为 `ws://astrbot:6199/ws`，以实际 AstrBot service 名、端口和路径为准；在容器里不能用 127.0.0.1 指代另一容器。`wsClients` 的关键字段是 `name`、`enabled`、`url`、`accessToken`、`role: Universal`、`messageFormat: array`、`reconnectIntervalMs`。AstrBot 平台类型为 `aiocqhttp`，匹配 `ws_reverse_host`、`ws_reverse_port` 和 `ws_reverse_token`。当前配置 JSON 可能带 UTF-8 BOM。

HTTP 与反向 WS 使用各自私有 Token；两端 WS Token 必须匹配。修改前备份，已有正常平台不清空。只给新建且尚未登录的服务安排必要重启；用户已登录后优先按当前版本支持的热重载操作，不为验证反复重启 QQ。

验收：HTTP `get_login_info` 匹配用户确认的账号、`get_status` 返回 online/good、当前 AstrBot 6199 established socket 和用户真实 `/help` 回复。日志历史“已连接”不能代替当前 socket；不要自动将 API 返回的账号当用户指定账号。

## 可选项与已知边界

选择域名后按 [cloudflare.md](cloudflare.md) 将网关回源指向宿主机回环 5099 的实际映射端口；选择邮件后按 [monitoring.md](monitoring.md)，配置 `gateway_type: snowluma`。SnowLuma 不调用 NapCat 专用的 `nc_get_user_status`。

SnowLuma 2.1.1 会在会话关闭后销毁账号网络适配器，日志为 `session closed: UIN=...`。因此单纯 HTTP 失败是 unknown；目标账号的确认关闭日志可锁存 offline，正确账号的有效 online/good API 可清除旧锁存。不能用 NapCat 的踢号正则假装完成 SnowLuma 探测。

本次现场已验收两个面板、准确账号与 OneBot、文本回复、Resend 测试及隔离掉线/恢复实收、自然定时采样；没有制造真实 QQ 掉线、没有整机重启、手机或真实媒体收发演练。Skill 通用脚本是后续抽象版，仅其离线测试通过不能宣称已替换到生产。

官方：[Docker 框架](https://github.com/SnowLuma/SnowLuma.Docker.Framework)、[Docker 部署](https://snowluma.github.io/zh/docs/guide/deploy/docker)、[配置与继承](https://snowluma.github.io/zh/docs/guide/configuration)、[对接 AstrBot](https://snowluma.github.io/zh/docs/guide/connect-bot)。
