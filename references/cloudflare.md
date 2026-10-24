# 可选：个人域名 + Cloudflare Tunnel / Access

只有用户明确需要域名便捷登录，或要求修复已有域名入口时执行。先按 [workflow.md](workflow.md) 询问是否拥有自有域名、Cloudflare 账号、DNS 管理权限，确认子域名和允许的登录身份；旧实例的域名/邮箱不能默认沿用。没有这些条件时保留 SSH 管理，基础部署不受阻。邮件是独立可选项，不在这里自动创建 Resend 账号或索取其 Key。

## 检测与配置

检测 cloudflared 真实路径、版本、service 是否存在/启用/运行、两个回环 HTTP；未知旧 unit 可能带 Token，不输出全文。检查 DNS 已有记录用途、Access 应用与 IdP；不覆盖其他服务。

1. **[USER ACTION REQUIRED]** 域名接入 Cloudflare；Zero Trust Authentication 启用 One-time PIN 或已有 IdP。两条精确主机名 Self-hosted 应用保护整个站点，Allow 仅用户邮箱，无 Everyone/Bypass。先应用后路由。
2. **[USER ACTION REQUIRED]** Networking → Tunnels 或 Zero Trust Networks → Connectors → Cloudflare Tunnel 创建远程管理 Tunnel。用户复制 connector Token 到受保护输入，先不加路由；不发命令/Token 截图。
3. 安装架构匹配的 cloudflared，检测 `CLOUDFLARED_BIN`；不能假定 apt 包固定安装路径。仓库签名按当前官方来源核对。
4. 用户在私有 SSH 终端非回显录入 Token，安全写入 `TUNNEL_TOKEN_FILE`；目录 root 700、文件 root 600。不要将 `service install TOKEN` 放进历史或参数。
5. 渲染 `assets/cloudflared.service.in`；DynamicUser + LoadCredential + `--token-file %d/tunnel-token`。同步 StateDirectory/HOME，systemd-analyze verify 后启用。宿主机服务才可按该路线回源宿主机回环。
6. **[USER ACTION REQUIRED]** 网关 Published application route → HTTP `127.0.0.1:GATEWAY_WEBUI_PORT`，路径空；NapCat 容器默认 6099，SnowLuma 默认 5099，但回源必须填实际宿主机映射端口。Protect with Access 开启并关联对应应用/AUD。
7. 确认匿名请求到 Access/被拒，才加 AstrBot 路由和它的 AUD；不能用 Bypass 排错。
8. **[USER ACTION REQUIRED]** 桌面无痕、手机移动网络分别进入两个面板；Token 仅存密码管理器。验证面板交互和 WebSocket，首页响应不代表所有功能。

## 排错

出站 7844 UDP QUIC / TCP HTTP2，JWT 验证等需 443，DNS 正常；443 可达不等于 Tunnel 可达。本机 origin 坏先修应用；Tunnel Down 查出站/凭据；Healthy 但 502 查回源端口和地址。匿名直达 WebUI 先撤问题路由或恢复保护，核对完整站点覆盖。合法身份被拒查邮箱、IdP、AUD、时间，不开放 Everyone。保留 SSH 隧道，故障时不临时裸露 WebUI。

历史已验收：一个 Tunnel 两域名、宿主机服务、JWT 校验、匿名 Access 跳转、桌面/iPhone 面板、手机 Token 保存。未从当前部署记录验证：添加 Tunnel 后整机重启、自然掉线的同机扫码、跨 VPS 切流。

## 中文界面指导与核验

按用户实际页面逐步指导，不一口气要求用户提交所有凭据。Access 常见入口为“访问控制 → 应用程序 → 添加应用程序 → 自托管”；Tunnel 常见入口为“网络 → 连接器/隧道”，新版也可在主控制台 Networking → Tunnels。路由可能叫“已发布应用程序路由”“公共主机名”或 Routes → Published application；字段有变化先看不含 Token 的截图并核对官方说明。

先创建两个精确主机名应用，路径留空、Allow 仅指定身份，再创建 Tunnel。页面即使展示 `cloudflared service install TOKEN`，服务器已安装时也不要照抄运行第二套服务；只私密录入 Token，使用准备好的 LoadCredential unit。检测 `command -v` 并解析软链接，不把软链接入口不等于真实二进制当作安装失败。

用户截图中实际主机名可能与约定拼写不同，先对齐 Access 目标和 Tunnel 路由，不能在一个域名上配置 Access、在另一个上发布 WebUI。添加路由通常自动建立 Tunnel CNAME，无需再新建指向 VPS IP 的 A 记录。类型选 HTTP、URL 框只填回环地址加端口；单一完整 URL 框才填 `http://...`。浏览器端仍使用 HTTPS。

展开“其他应用程序设置 → Access”，开启“使用 Access 保护/Protect with Access”。若界面要求 Team name 与 AUD，使用实际 Access 登录团队名和对应应用的 audience tag；两个应用不能混用。服务端只输出 `required`、团队匹配和 AUD 是否匹配的布尔结果，不输出完整配置或 Token。匿名 302 到 Access 证明边缘保护，不能单独证明回源 JWT 校验已启用；两项分别检查，最后由用户认证后验证真实面板交互。

当前模板不需要新增入站 80/443 或管理端口；先保留已有云规则，检查出站 7844。不要把不需要新增入站规则变成擅自删除已有规则。

## Debian 安装例子

历史使用官方签名 apt 仓库。仅目标无已安装版本/仓库冲突且确认安装范围后执行，此处不创建路由或 Token：

```bash
sudo install -d -m 0755 /usr/share/keyrings
sudo curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg -o /usr/share/keyrings/cloudflare-main.gpg
printf '%s\n' 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main' \
  | sudo tee /etc/apt/sources.list.d/cloudflared.list >/dev/null
sudo apt-get update
sudo apt-get install -y cloudflared
command -v cloudflared
cloudflared --version
```

这是当前官方通用 Debian 仓库示例；仍先核对平台与签名方式，不从旧代号猜新仓库。目标源文件已存在先查现状。service 模板替换所有 @变量@、检查 unit，再复制系统 unit 目录，经授权 daemon-reload / enable --now。安装成功不证明 Tunnel 已连接。

官方补充：[控制台创建](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/get-started/create-remote-tunnel/)；[网络要求](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/tunnel-with-firewall/)。
