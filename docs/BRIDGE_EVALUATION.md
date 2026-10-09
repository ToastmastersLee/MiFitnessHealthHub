# Mi Fitness Data Bridge 评估

评估日期：2026-10-09（Asia/Shanghai）。目标：小米手环 9 系列 + Mi Fitness，Windows 本地个人数据管线。

## 结论

采用 **固定版本第三方桥接器 + 本地 JSON 消费者** 作为 PoC 架构。离线导出及下游导入已实测；真实登录、小米云端服务、手环 9 / 9 Pro / 9 Active 的具体兼容性和账户地区组合仍待验证。

| 项目 | 本轮证据 |
| --- | --- |
| 上游 | https://github.com/shkyyy18/mi_fitness_data_bridge |
| 固定提交 | `ae70f5e6e167474e93d4c2beeb8ae3d3297d5ade` |
| 包 / 版本 | `mi-fitness-data-bridge` / `0.3.3` |
| Python | 上游要求 >=3.11；本机隔离环境实测 3.13.5 |
| CLI | `mi-fitness-bridge`；兼容别名 `mi-fitness-mcp` |
| 导出 | SQLite 缓存 → JSON 信封 1.0 或各数据集 CSV |
| 安装隔离 | `D:\Github\MiFitnessHealthHub\.venv`；不改 conda base 依赖 |
| 上游源码位置 | 被忽略的 `work/upstream/`，仅用于检查和例程；不是本项目供应的代码 |
| 许可 | 当前 AGPL-3.0-only；本项目不复制连接器源码，无远程发布 |

上游无官方 Xiaomi 背书。没有已验证设备名单；Mi Fitness 和 Zepp Life 不能互换。默认 `cn` 是路由默认值，不代表任何账号或设备的兼容认证。

## 登录和安全前提

CLI 需要已有本人 `user_id` 和 `passToken`，不提供一键账号授权或经过本项目验证的 Token 获取向导。手环型号和 App 名称本身不足以推导凭证获取方法。

交互式 `setup` 隐藏 Token 输入，凭证通过上游 keyring 模块保存。本轮只阅读公开代码并用合成测试评估，不运行本机真实凭证读取、系统 keyring 访问或 doctor。真实启用前必须由用户确认凭证来源以及实际 Windows keyring 后端；源码存在不能证明本机已经配置好。

桥接器导出可带明文 `user_id`、设备标识和轨迹。Hub 移除独立 `user_id` 字段，但原始导出、其他标识、GPS 和指标仍敏感，不能宣称匿名化。局部凭证字段检查无法识别被任意字符串隐藏的秘密，因此只能导入可信来源的导出。

## 数据兼容层

| 数据集 | 导出日期列 | Hub 处理 |
| --- | --- | --- |
| daily_activity | date | 来源日期、整数步数及非负指标 |
| sleep | start_at | 会话顺序、评分 0–100 / null、阶段原文与评分来源 |
| workouts | start_at | 会话顺序、运动汇总字段 |
| workout_detail | timestamp | 秒级曲线字段和非负偏移 |
| workout_gps | timestamp | 经纬度范围和时间 |
| body_measurements | timestamp | 体重等身体测量字段 |
| heart_rate | timestamp | bpm 数值 |
| spo2 | timestamp | spo2_pct 0–100 |
| stress | timestamp | stress_score 0–100 |
| abnormal_heart_beat | start_at | 会话顺序及持续时间 |

这是导出格式兼容范围，不是手环 9 数据能力清单。合成身体测量也不证明手环会测量体重；字段是否存在取决于账户或其他数据来源。未知列保留，未知数据集或主 schema 变化拒绝导入。

上游同步是非公开协议的最佳兼容处理，某些汇总可能与 App 服务端修正结果不同。Hub 不自行重复计算或调整步数、睡眠分和其他指标；只验证工程结构与数值域。睡眠评分缺失仍为 null，不能把它视为零分。

## 可复现评估

1. HTTPS 下载上游公开仓库，记录并固定提交。
2. 在专用 venv 安装该提交对应的本地包，解析依赖。
3. 外部 socket 被拒绝的测试守卫下运行上游原始合成例程，SQLite → JSON + 10 个 CSV。
4. 将同一 seed / 导出器的 JSON 导入独立 hub SQLite，再重跑确认幂等。
5. 本项目全部数据集的合成测试，以及上游导出、CLI 安全和数据库路径的选定测试；数量见 VALIDATION.md。

上游完整测试套件未全量运行；未对真实小米端点发起探测。未来更新上游版本应重新核对 schema、命令、凭证路径及合成验证，不直接跟随 main。

## 固定版本来源

- [README](https://github.com/shkyyy18/mi_fitness_data_bridge/blob/ae70f5e6e167474e93d4c2beeb8ae3d3297d5ade/README.md)
- [兼容性与凭证前提](https://github.com/shkyyy18/mi_fitness_data_bridge/blob/ae70f5e6e167474e93d4c2beeb8ae3d3297d5ade/docs/compatibility.md)
- [导出格式](https://github.com/shkyyy18/mi_fitness_data_bridge/blob/ae70f5e6e167474e93d4c2beeb8ae3d3297d5ade/docs/export-format.md)
- [包、Python 和依赖](https://github.com/shkyyy18/mi_fitness_data_bridge/blob/ae70f5e6e167474e93d4c2beeb8ae3d3297d5ade/pyproject.toml)
- [安全约定](https://github.com/shkyyy18/mi_fitness_data_bridge/blob/ae70f5e6e167474e93d4c2beeb8ae3d3297d5ade/SECURITY.md)
- [许可证](https://github.com/shkyyy18/mi_fitness_data_bridge/blob/ae70f5e6e167474e93d4c2beeb8ae3d3297d5ade/LICENSE)

后续公开分发或深度集成时，应按实际使用方式审查上游 AGPL 义务，不能把当前上游说成 MIT。当前仅本机个人 PoC，不创建远程、不推送。
