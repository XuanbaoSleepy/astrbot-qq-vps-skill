# 可选：模型提供商专用代理

仅用户需要出口或修复已有代理时阅读，核心 QQBot 不依赖它。

历史验证了独立 sing-box Compose 项目加入 Bot 网络、无宿主机端口；内部 HTTP 代理仅配置 Gemini provider，NapCat/全局出口不改。用户本机从 Mihomo YAML 选 hy2 节点转换，私下上传，TLS 保持校验。模型列表和短生成成功；重启 AstrBot 后 OneBot 重连、QQ 在线，其他模型不自动切换。

不将旧地区、节点、端口、版本摘要、模型名当新默认。配置/订阅/Key 在私有文件，目录 700、文件 600；只报告状态。路线：检测 → 最小计划 → 用户安全上传 → schema 转换/check → 单独启动代理 → 从 AstrBot 测网络/API/短生成 → 仅目标 provider 配置 → 必要时经授权重启 AstrBot、验收重连。

历史坑：Mihomo 跳跃端口串转 sing-box 数组；共项目导致 orphan，独立项目避免误删。回滚先清 provider 代理，再停代理项目，不用旧含 Key 配置覆盖用户后续模型设置。转换器/部署脚本未在本次通用 Skill 新目标验证，故不打包为必选自动流程。
