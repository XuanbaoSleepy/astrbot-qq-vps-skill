# 历史故障排查

先确认网关类型及用户是否选择域名/邮件。未选择的 Cloudflare/Resend 不存在不是故障；基础 QQBot 无需为此重新部署或索取凭据。以下历史原因不能直接当作当前根因。

关键词：SWAS/ECS、SSH -N、登录态、online=true、OneBot11、误登、ntfy、1010、Mihomo、orphan、Access。

| 症状 | 历史原因 | 排查 | 实际解决 | 避免复发 |
|---|---|---|---|---|
| 找不到 ECS 角色绑定 | 实际为 SWAS，ECS/IMDS 假设不适用 | 查云产品、uploader 是否启用 | 放弃该路线；FC 仅草案，先 ntfy 后 Resend | 先识别产品，不让通用 VPS 依赖 ECS |
| SSH 命令窗口空白 | -N 正常维持转发 | 本地端口探测，另开 SSH echo | 保持窗口、另开终端操作 | 解释 -N、ExitOnForwardFailure |
| 电脑 WebUI 打不开 | 本机隧道断开 | VPS curl 正常，本机端口失败 | 重建隧道，本机恢复 200 | ServerAliveInterval、Tunnel 入口、SSH 备用 |
| 重启后容器恢复 QQ 离线 | QQ 拒绝快速登录态 | 失效日志、Mounts 与目录存在 | 用户手机授权，真实 loss/restored 实收 | 不承诺免扫码、不无限重启 |
| online=true 但 Bot 离线 | HTTP 单信号不足 | 踢号日志、账号、主动 API、WS | 日志锁存和多信号判断 | 容器 healthy 不当 QQ 验收 |
| 登录后状态仍离线 | 正则未覆盖实际恢复日志 | 新日志、cursor、锁存 | 加 OneBot11 适配器初始化完成并测试 | 升级时核对日志 schema |
| 登录错误 QQ | 手机扫码未切 Bot 小号 | 预期账号匹配布尔值 | 重置运行会话，重登目标，不删除全部数据 | 扫码前核对手机和授权页 |
| ntfy Topic 泄露 | 截图带 secret-like Topic | 识别泄露不复述 | 轮换作废旧 Topic、重新订阅实收 | 不截图秘密；最终迁 Resend 清活动项 |
| Python 发信 403/1010，curl 可达 | 请求特征被访问层阻断 | 比较客户端、状态码，不打印认证 | 加 NapCatMonitor/1.0 UA，mail ID + 实收 | 先定位，别直接换 Key/服务 |
| 定时触发方式复杂 | 日历和开机触发叠加 | 查 timer 字段/执行时间 | 改 OnBootSec + OnUnitActiveSec | 单一组合、现场复核 |
| hy2 配置 check 失败 | Mihomo 逗号端口串需拆数组 | 正式 sing-box check，不打印节点 | 仅转换端口字段 | 不照搬跨产品 schema、保持 TLS |
| 镜像拉取受阻 | registry 网络不可达，统一根因未确认 | DNS/TLS/registry 独立检测 | 选可达可信来源固定摘要 | 特定代理源不固化为唯一来源 |
| proxy 变 orphan | 多 Compose 文件共项目名 | 看项目标签/network | 代理独立项目接 Bot 网络 | 不 remove-orphans 盲清 |
| Cloudflare 菜单找不到 | 控制台入口变化 | 找 Tunnels/Connectors 实体 | 用新版入口 | 实施时查官方说明 |
| iPhone Token 图不显示/转移不便 | 临时媒体显示和跨设备步骤问题 | 用户观察，不上传 Token 图 | 安全转移、密码管理器保存、删除临时图 | 秘密媒体不打包进 Skill |
| SnowLuma 账号文件没有启用数组但接口正常 | 账号文件只保存部分覆盖，全局配置仍生效 | 查有效全局配置、live API 与当前 WS，不输出 Token | 本次无需覆盖健康账号文件 | 不把文件局部值当实际在线状态 |
| SnowLuma 掉线后 HTTP 无响应 | 会话结束会销毁账号适配器 | 对应 UIN 的 session closed 日志、当前 API | 专用探测锁存关闭；健康身份匹配 API 清除旧锁存 | 不调用 NapCat 专用 API 或仅把连接失败归为已证实掉线 |
| Access 已建但新域名没被保护 | 应用主机名和 Tunnel 路由拼写不一致 | 比较精确主机名和匿名重定向 | 对齐主机名，分别关联各自 AUD | 不默认截图中名称和约定值相同 |
| 302 到 Access，但隧道未校验 JWT | 边缘 Access 与 originRequest.access 是两项设置 | 检查 required、teamName、audTag 的匹配布尔值 | 开启 Protect with Access 并匹配各应用 | 不用单一 302 代替全部验收 |
| cloudflared 路径检查失败但服务可运行 | command -v 返回软链接入口 | readlink -f、可执行性和实际版本 | unit 使用已核验路径 | 不凭默认 /usr/bin 或 /usr/local/bin 重装 |
| SSH 预检末尾报 `$'\\r'` | Windows 文本管道附加 CRLF | 检查脚本行尾与传输方式 | LF 文件传输，脚本末尾明确 exit | 不把退出 127 误报为远端部署失败 |
| Windows 离线测试替换临时 state 报权限错误 | 沙箱默认临时目录的替换权限 | 检查失败路径及 workspace temp 权限 | 仅测试进程改用工作区临时目录重跑 | 不因此修改 Linux 生产状态保存逻辑 |

历史处理不能证明新故障同因；先只读定位。手机同机扫码未完整验收，失败时用第二屏幕刷新二维码，不主动踢号。
