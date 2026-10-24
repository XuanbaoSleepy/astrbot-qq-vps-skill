---
name: astrbot-napcat-vps
description: 在 Linux VPS 部署、迁移或修复 NapCat/SnowLuma + AstrBot，验证 OneBot v11；按用户选择配置 Cloudflare 域名管理入口和 Resend 掉线邮件。
---

# NapCat / SnowLuma + AstrBot VPS

保留调用名 `$astrbot-napcat-vps` 以兼容旧引用。按 Detect → Plan → Deploy → Configure → Verify → Report 工作；不继承旧实例的权限、账号或秘密。

## 必须先确认的可选项

**域名便捷登录和邮件告警是两个独立可选项，不是基础部署前提。Agent 必须主动询问用户：**

1. 是否需要用个人域名便捷登录 WebUI（Cloudflare Tunnel + Access）？
2. 是否需要 QQ 掉线/恢复邮件告警（Resend）？

需要域名入口时，必须询问是否拥有可用域名、Cloudflare 账号及该域名的 DNS 管理权限，再确认子域名、Access 登录邮箱/身份提供商。需要邮件时，必须询问是否拥有 Resend 账号、已验证的发信域名（或可配置验证 DNS 的域名）、收件邮箱，以及私密录入限定发送权限 Key 的条件。发信域名可以独立于 WebUI 域名；邮件仅需相应 DNS 管理能力，不强制使用 Cloudflare。

本次会话已明确的需求和条件直接记为已确认，只追问缺项，不能拿历史实例代答。未回答时不得默认启用；明确不需要则跳过安装、控制台、凭据及验收。条件不足时继续独立的基础部署，把所选可选项列为待用户；没有域名/Cloudflare/Resend 不得阻止 SSH 管理和基础 QQBot 验收。

## 路由

- 首次部署/重装/迁移：先读 [workflow.md](references/workflow.md)。用户已指定网关则沿用，未指定才确认 NapCat 或 SnowLuma；不同时启动两者登录同一 QQ。
- NapCat 分支读 [deployment-guide.md](references/deployment-guide.md)；SnowLuma 分支读 [snowluma.md](references/snowluma.md)，不照搬 MODE=astrbot、NapCat 配置路径或专用 API。
- 修复：先检测，区分容器、QQ、OneBot、本机隧道、Cloudflare、邮件故障；按需读 [troubleshooting.md](references/troubleshooting.md)，不重新部署全部组件。
- 仅选择域名入口时读 [cloudflare.md](references/cloudflare.md)；仅选择邮件时读 [monitoring.md](references/monitoring.md)。二者互不隐含。
- 仅用户需要模型专用出口或已有代理故障时读 [optional-provider-proxy.md](references/optional-provider-proxy.md)，代理不是前提。

## 工作流

1. **Detect**：确认目标/SSH 指纹，运行 `bash scripts/preflight.sh --deploy-dir "$DEPLOY_DIR"`。仅已选择域名/邮件时分别追加 `--with-cloudflare` / `--with-resend`。检测资源、Docker、已有目录/容器/端口/规则；不输出完整配置、秘密日志或二维码。
2. **Plan**：区分基础部署、已选择的域名、已选择的邮件，列数据位置、备份、影响、回滚、用户步骤。健康服务不重建，已有可选设施不擅自关闭。
3. **Deploy**：NapCat 用 `assets/compose.yaml` + `.env.example`；SnowLuma 用 `assets/compose-snowluma.yaml` + `.env.snowluma.example`。按架构核验镜像并固定 RepoDigest；保留共享网络、反向 WS、持久化、回环映射、重启策略和轮转。
4. **Configure**：以所选网关的当前 schema 配置两端 WS/Token。标记 `[USER ACTION REQUIRED]` 的扫码、账号核对、初始密码和私密输入。只对已选择项配置 Tunnel/Access 或 Resend；Cloudflare 不是告警发送器。
5. **Verify**：`verify.py --help` 后使用 `--gateway-type napcat|snowluma --gateway ...`；旧 NapCat 参数仍兼容。基础检查不需要邮箱/Key；`--qq-probe-config` 可只验 QQ/WS。只对已选择项追加 Tunnel/monitor 参数与用户实收。修改脚本后跑 `python3 -B -m unittest discover -s scripts -p 'test_*.py'`；不把脚本退出 0 当作真实 `/help` 实收。
6. **Report**：分别报告基础、域名、邮件的通过/失败/待用户/未实测；未选择项标为不适用，不列为缺失或故障。说明监控盲点，未演练的真实掉线、重启和设备验收如实标记。

## 安全边界与停点

- SSH/防火墙/公网暴露变更、重启主机、删除数据前，说明具体影响并获取动作授权；已有明确授权不重复问。先准备第二条 SSH 和回滚。检测脚本不执行这些操作。
- Secret 在目标私有文件或非回显交互录入，root 600 / 目录 700；不进聊天、Git、命令参数或普通输出。备份也含凭据。
- QQ 登录态失效等用户验证，不自动踢号、扫码或无限重启；账号不符停下，不能自动采纳误登账号。
- WS 仅内网，HTTP/WebUI 仅回环；检查 Docker PortBindings、IPv6 和云规则，UFW 状态不是充分证据。
- 历史监控 QQ 在线/WS 断连仍返回 online，unknown 不触发 QQ loss，整机宕机不能自报。更广覆盖需另行提出扩展，不擅自改状态机。
- 当前 schema/控制台字段不符先查现场与官方说明，不猜着覆盖。失败后先定位；风险登录/凭证失效停在人工操作，不循环重启。

## 可复用资源

- `scripts/preflight.sh`：只读环境/资源/网络采集。
- `scripts/verify.py`：只读容器/端口/HTTP/QQ/WS/监控新鲜度检查，非完整用户验收。
- `scripts/qq_monitor.py`：共用状态机，`gateway_type` 选择 NapCat/SnowLuma 探测；只在选择邮件后安装/启用。通用新版仍须目标验收。
- `scripts/test_monitor.py`、`test_snowluma.py`、`test_optional_scopes.py`：离线状态机、双网关与可选验证范围测试，不发真实邮件。
- `assets/`：Compose、变量示例、监控配置结构、systemd 模板。按 guide 渲染、校验；不运行未替换模板，路径须正确 systemd 引用/转义。
