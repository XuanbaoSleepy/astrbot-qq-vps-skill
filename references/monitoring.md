# 可选：QQ 状态监控与 Resend

用户明确选择邮件告警，或要求修复已有告警后才执行；先按 [workflow.md](workflow.md) 询问是否有 Resend 账号、已验证发信域名或验证 DNS 的条件、发件地址、收件邮箱及私密录入 Key 的条件。邮件不依赖 WebUI 域名或 cloudflared；DNS 可以由 Cloudflare 或其他服务商托管。没有 Resend/域名不阻止基础部署；未选邮件不安装/启用 timer、不要求邮件实收。

## 配置合同

`assets/monitor-config.example.json` 复制到目标私有文件，替换所有 REPLACE 值：`http_url` 只允许回环 HTTP；`token_file` 是独立 HTTP Token；`qq_user_id` 是用户确认的目标；`gateway_type` 明确选 `napcat` / `snowluma`，`gateway_container`、AstrBot 名称和 WS 端口从现场检测。旧 `napcat_container` 字段与省略类型的旧 NapCat 配置仍兼容；新旧字段冲突或未知类型拒绝执行。不要跨产品复制监控 state 的日志锁存。

- NapCat：保留踢号/登录日志锁存、HTTP online/good、账号匹配，`active_user_probe` 历史为 true，调用 `nc_get_user_status`。能力缺失不能静默关掉并宣称等价；该调用成功也不能单独证明 QQ 在线。
- SnowLuma：不调用 `nc_get_user_status`。按固定版本确认的 `session closed: UIN=...` 锁存目标账号关闭事件；HTTP 适配器消失且已有关闭证据则 offline，无证据的 HTTP 故障则 unknown。健康且身份匹配的 live API 清除旧关闭锁存，日志读取失败不掩盖有效在线 API。账号配置文件的部分覆盖不能代替实际接口测试。

若用户只要 QQ/WS 检查，不要索取邮箱或 Key；改用 `assets/qq-probe-config.example.json` 与验证器的 `--qq-probe-config`。

service 设置 QQBOT_MONITOR_CONFIG / QQBOT_MONITOR_STATE。无实例目录、账号或邮箱默认。root 600、目录 700；monitor 需 Docker/nsenter 权限，flock 防并发。cloudflared 动态用户不能照搬给 monitor。

## 发送和验收

Resend HTTPS POST UTF-8 JSON、纯文本；Key 在 Python 内从文件读取，保留历史可工作的 NapCatMonitor/1.0 UA（名称不决定网关类型）。主题自动区分 NapCat/SnowLuma，可用非秘密 `gateway_label` 明确标记 SIMULATION。发信域名由 Resend 验证，Cloudflare 若被选作 DNS 管理方则按面板值配置验证记录。

指导用户在 Resend 确认域名 Verified，创建本实例独立的 Sending access Key，限定发信域名；在其私有 SSH 终端隐藏输入，不把 Key 或完整安装命令贴聊天。已具备账号及验证域名则复用，不重复创建/改动旧实例 Key。API 仅发送权限不能读取域名列表时，不扩大 Key 权限，只结合用户面板确认及实际测试发信。

`--test-resend` 发一封标记测试邮件，不改状态；mail ID + 用户实收才通过。切换前保留旧渠道，实收/隔离去重通过并确认后再清活动项，保留私有回滚备份。旧 ntfy 源码不能作为最终版本。

三组 `test_*.py` 均无真实网络/邮件/生产状态操作。端到端模拟另用独立状态、明确 SIMULATION 主题/原因、限制发送数量，不踢 QQ；可比较生产 state 哈希证明确实隔离。测试及模拟邮件分别确认实收，不用 API accepted 冒充到达。

## 状态与盲点

共享状态机保持 3 offline 一次 loss、2 online 恢复；初次 unknown→online 不发恢复。恢复后 30 分钟内再离线冷却，提前恢复可撤未发 loss。unknown 重置连续计数不改变 phase。NapCat 与 SnowLuma 各自使用匹配的日志 cursor/锁存，不能把一种网关的正则应用到另一种。

失败 pending 顺序重试，最高约 30 分钟间隔；不能保证网络恰好一次送达。phase online 的旧文件不证明当前在线，查 last_probe_at。timer 仅 OnBootSec + OnUnitActiveSec，不叠加日历。

单独 WS 断连仍是 QQ online；持续 unknown、主机/timer 停止无独立邮件。更广覆盖另行规划 OneBot/probe stale/外部 heartbeat，不自动重写可靠逻辑。异常输出仅类型，避免 URL/Key 泄露。

## 部署

只在用户选择邮件后，将监控脚本复制到 DEPLOY_DIR/bin；替换 monitor.service.in / timer.in 中目录、配置/state、unit、lock。路径有空格须按 systemd 引用转义，不盲目 sed。systemd-analyze verify 后先离线测试、配置、邮件实收，再启用 timer。观察一次自然定时采样推进、service 成功、状态新鲜和空 pending，不能只跑手动命令就声称 timer 已验收。目标 QQ 不自动采用当前 HTTP 返回账号。

## 验证层级

原实现统一收集 Docker stdout/stderr 并按时间排序，每轮最多处理一个队列事件，service 超时 180 秒。2026-10-24 的独立 SnowLuma 部署已确认真实在线与文本回复、测试邮件、七次模拟离线只发一次及恢复实收、自然 timer；未制造真实 QQ 掉线或主机重启。此处双网关通用脚本是随后抽象的新版本，仅其本地测试通过，不代表已更新任何生产主机。
