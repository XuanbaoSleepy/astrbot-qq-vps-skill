# 共用工作流与可选项分流

## 开始时先询问

基础目标是 NapCat **或** SnowLuma 与 AstrBot 的 QQ → 网关 → OneBot → AstrBot → 回复闭环。SSH 转发足够完成基础管理；个人域名、Cloudflare、Resend 都不是基础必需条件。

Agent 必须主动询问“是否需要个人域名便捷登录”和“是否需要掉线邮件告警”，分别记录是/否/未决定。当前会话明确给出的答案沿用，历史实例不作答案。可先做不依赖答案的只读检查；未决定前不安装或索取可选服务的凭据。

| 选择 | 必须询问的条件 | 未具备时 |
|---|---|---|
| 域名 WebUI | 是否有自有域名、Cloudflare 账号和该域 DNS 管理权限；期望子域、旧记录是否仍使用；Access 允许邮箱/IdP | 基础部署继续，提供 SSH 管理；域名项待用户，不自行注册/购买/接管 DNS |
| 邮件告警 | 是否有 Resend 账号、已验证发信域名或可配置验证 DNS 的域名；发件地址、收件邮箱、私密录入发送 Key 的条件；希望覆盖 QQ 会话还是更广故障 | 基础部署继续；缺少自有发信条件时不能承诺用测试域给任意收件人正式发信 |
| 二者都否 | SSH 认证、目标 QQ、现场资源即可 | 不安装 cloudflared/邮件 timer，不要求域名、邮箱或 Resend Key |

邮件可用独立发信域名，DNS 可由其他服务商托管；选择邮件不等于同意给 WebUI 配域名。已有域名也不等于有 Cloudflare 权限或同意启用任一可选项。用户已选择且明确提供了条件时不要再问一轮授权。

## 检测与实施

1. 确认目标、SSH 认证和主机指纹；首次 TOFU 记录与独立核对要区分。检查 OS/架构/CPU/RAM/Swap/磁盘、端口、现有部署、Docker、软件包锁和网络。
2. `preflight.sh` 默认只探测基础软件来源。域名选择是才加 `--with-cloudflare`，邮件选择是才加 `--with-resend`。检测输出的未知项不是通过结论。
3. 空机先保存软件源、包清单、规则及服务基线。安装 Docker 会创建桥接/NAT；有明确部署授权后执行必要安装，保护 SSH 和已有服务。已安装可用环境不重装。
4. 镜像仓库、软件源、QQ、Tunnel、Resend 分开检测。直连超时不代表镜像不存在；使用可信镜像转发或官方发布源，保留上游仓库、版本、架构及固定摘要，不关闭 TLS。apt 镜像也须校验官方签名。
5. NapCat 进入 [deployment-guide.md](deployment-guide.md)；SnowLuma 进入 [snowluma.md](snowluma.md)。不对同一账号同时运行两套协议端，不自动替换用户指定的产品。
6. 目标配置以实际生成的文件、版本源码和 live API 为准。UTF-8 BOM 用 `utf-8-sig` 读取；不要输出原值来诊断字段。Windows 文本管道可能追加 CRLF，脚本按 LF 传输，先排查行尾再判定远端错误；不把它当 shell 版本兼容问题。
7. 先验证目标 QQ 身份、在线状态、当前 WS socket 和另一 QQ 的 `/help` 回复，再完成所选可选项。用户已登录后不为演练主动踢号或重建健康会话。

## 三种验证范围

先看 `python3 scripts/verify.py --help`，再用现场值：

```bash
python3 "$SKILL_DIR/scripts/verify.py" \
  --gateway-type "$GATEWAY_TYPE" --gateway "$GATEWAY_CONTAINER" \
  --astrbot "$ASTRBOT_CONTAINER" --gateway-webui-port "$GATEWAY_WEBUI_PORT" \
  --astrbot-webui-port "$ASTRBOT_WEBUI_PORT" \
  --onebot-http-port "$ONEBOT_HTTP_PORT" --onebot-ws-port "$ONEBOT_WS_PORT"
```

- 基础：上面参数验证容器、持久化、回环端口、HTTP 和 Docker，自身不需要域名/邮件；它没有证明 QQ 消息回复。
- QQ/WS：追加 `--qq-probe-config "$QQ_PROBE_CONFIG"`；使用 `assets/qq-probe-config.example.json`，选择 `gateway_type`，只填探测所需字段。SnowLuma 可追加 `--novnc-port "$NOVNC_PORT"` 检查扫码入口映射。
- 域名已选择：追加 `--cloudflared-unit "$CLOUDFLARED_UNIT"`，另验精确主机名匿名 Access、回源 JWT/AUD 和用户登录后交互。
- 邮件已选择：追加全部 `--monitor-config "$MONITOR_CONFIG" --monitor-state "$MONITOR_STATE" --monitor-unit "$MONITOR_UNIT"`，另验真实邮件实收、隔离模拟及自然 timer 触发。它不要求同时传入 cloudflared unit。

旧 `--napcat` / `--napcat-webui-port` 是兼容别名，省略 gateway type 时沿用 NapCat。退出 0 仅代表覆盖范围通过，1=失败，2=证据不足；缺少所选 QQ/邮件验收不能报全部通过。未选择域名/邮件不是证据不足。

## 收尾与恢复

分别列出基础、域名、邮件的状态；未选项写“不适用”，条件欠缺的所选项写“待用户”。保留 root 私有配置、数据、版本摘要、回滚方式和告警覆盖边界；可恢复的部署记录不含实际秘密。临时 SSH 扫码隧道可结束，并提供重开命令。

恢复/迁移只转移用户选择且现有的可选服务；不能因为新机没有 Cloudflare/Resend 就阻断基础恢复。域名切流、旧 Tunnel connector、旧监控队列另行检查；不覆盖健康旧入口，不把跨机器 QQ 登录态可用当保证。
