# MiFitnessHealthHub

**交接与换机恢复入口：[HANDOVER.md](HANDOVER.md)。** 手册、代码与复现步骤都在本仓库内，随 Git 保存。

**查看多年个人数据：[官方导出与 Zepp Life 历史处理](docs/PERSONAL_DATA_ONBOARDING.md)。** 已支持 Zepp Life 官方 CSV 的本地导入与历史页面；Mi Fitness 官方导出仍待适配。

面向 **小米手环 9 系列 + 小米运动健康 Mi Fitness** 的本地数据项目。
Python 3.11+ / SQLite / Windows PowerShell。当前完成离线数据链路 PoC；真实设备、账号地区、固件与云端认证的组合尚未验证。

项目位置：`D:\Github\MiFitnessHealthHub`。核心导入工具只有 Python 标准库依赖。
桥接器作为可选第三方依赖单独安装，固定到经过评估的提交，不复制连接器源码。

```text
Mi Fitness 云端
  → 可选 mi_fitness_data_bridge（非官方；真实连接尚待验证）
  → data/bridge.db → data/inbox/bridge.json
  → 整批验证 → data/healthhub.db
  → 本地 SQL / 数量及覆盖范围摘要 → 用户选择是否交给 Codex
```

官方 Zepp Life 导出可直接使用 [离线导入与历史页面](docs/ZEPP_LIFE_IMPORT.md)。私人 SQLite 与报告留在 `data/` / `private/`，均不随 Git 上传。

## 已具备的功能

- 消费桥接器 JSON 信封 `schema_version=1.0`；识别 10 种数据集。
- 校验日期、时间顺序、数值类型、非有限值、非负指标、百分比及 GPS 范围。
- 递归拒绝常见凭证字段，包括 JSON 字符串形式的嵌套内容；错误不回显个人输入。
- 导入前验证整份文件；单文件事务写入，坏记录不会留下部分更新。
- 按本地 subject、数据集、桥接器记录 ID 去重；同 ID 的健康字段变化会更新。
- 保留附加字段和 `null`；不把未知数值补成 0，不估算睡眠分。
- 导入审计包含文件 SHA-256、时间和条数；默认摘要不显示个人测量值或账号。
- 同一 subject 绑定一个账号；专门的 `user_id` 字段从 hub 记录移除，账号绑定使用带随机盐的 HMAC。
- PowerShell 安装、测试及同步入口；默认同步仅扫描本地 JSON。

这些工程测试不证明手环 9 的真实接口可用。桥接器是非官方、实验性工具，依赖非公开接口；当前需要已有 `user_id` / `passToken`，没有一键授权或经本项目验证的凭证获取流程。参见 [评估记录](docs/BRIDGE_EVALUATION.md)。

## 快速开始（无需账号）

已在本机建立 `.venv` 并完成安装；它使用 Miniconda Python 3.13.5。以下操作均在项目根目录运行，不需激活虚拟环境：

```powershell
Set-Location -LiteralPath 'D:\Github\MiFitnessHealthHub'
.\scripts\test.ps1
.\.venv\Scripts\python.exe scripts/poc.py
```

PoC 调用固定版本的上游 `examples/synthetic_demo.py` 中的 seed 和真实导出器，导入 hub 后再导入一次以确认去重。输出落在 **`data/poc/`**，与将来的真实收件箱分离。

初次在另一台机器安装：

```powershell
.\scripts\setup.ps1 -WithBridge
# 只需要离线导入器时使用 .\scripts\setup.ps1
```

安装需要联网下载软件；测试和 PoC 不需账号。PoC 禁止 Python socket 连接；上游测试守卫只允许 Windows asyncio 需要的数字回环地址。

上游原始演示和针对导出、凭证 CLI、数据库路径的测试：

```powershell
.\.venv\Scripts\python.exe scripts/verify_bridge.py --demo
.\.venv\Scripts\python.exe scripts/verify_bridge.py
```

## 本地导入与检查

输入必须是桥接器真实导出结构；每行需要 `id`、`user_id` 和相应日期/时间列。本节只导入桥接 JSON；Zepp Life 官方 CSV 使用独立的 `import-zepp` 命令。

```powershell
# 使用合成文件验证
.\.venv\Scripts\python.exe -m healthhub validate data/poc/inbox/synthetic_bridge.json
.\.venv\Scripts\python.exe -m healthhub summary --db data/poc/synthetic_hub.db --subject synthetic-demo

# 后续由你放入本人已授权导出；这些命令仍然不会登录或联网
.\.venv\Scripts\python.exe -m healthhub import data/inbox/bridge.json --db data/healthhub.db --subject band9-local
.\scripts\sync.ps1
```

`sync` 扫描收件箱顶层的 `*.json`，按文件名排序；每个文件独立事务，后续文件失败时已经成功的文件保留。重跑会去重。
**当前同 ID 采用最后成功导入的健康字段；不按上游修订时间自动判断新旧。** 因此真实收件箱建议只保留每次覆盖更新的 `bridge.json`，历史快照放到被忽略的 `backups/`，避免旧导出覆盖新修正。

SQLite 中的 `records.payload_json` 保存健康字段；`import_runs` 保存导入审计；`subjects` 保存账号绑定；`metadata` 保存版本所需参数。版本由 `PRAGMA user_version` 标识。导入器拒绝写入桥接器数据库或其他未识别数据库。

同一数据库首次确定 UTC 偏移后拒绝混用其他偏移。默认 `+08:00`：有偏移时间转换到该偏移，无偏移时间按此本地时间解释，原始时间字符串留在 payload 中。每日活动沿用来源日期；睡眠覆盖日期采用**开始日**，不是醒来日。固定偏移不处理夏令时；若账号在有夏令时地区，需在真实导入前扩展时区处理。

摘要中 `coverage` 是本地累计记录覆盖范围，`latest_import_datasets` 区分最新导出中返回空数组的数据集和未包含的数据集。空数组不意味着真实兼容性成功；未返回的数据不会删除库中已有记录。

## 配置和隐私

[.env.example](.env.example) 只列非敏感配置；工具读取进程环境，**不会自动加载 `.env`**。CLI 参数优先于环境值。

```powershell
$env:HEALTHHUB_DB = 'data/healthhub.db'
$env:HEALTHHUB_INBOX = 'data/inbox'
$env:HEALTHHUB_SUBJECT = 'band9-local'
$env:HEALTHHUB_UTC_OFFSET = '+08:00'
```

subject 是自选本地别名，使用字母、数字、`_`、`-`；不要填真实账号。更多边界见 [隐私约定](docs/PRIVACY.md)。账号凭证只交给桥接器的交互式配置和系统凭证存储，不能放进本项目 `.env`、命令行或聊天。

## 将来的云端同步

当前没有执行 `setup` / `doctor` / 云端 `sync`，也没有注册 Windows 计划任务。
如果后续你已通过可信方式自行取得本人凭证、确认 App 账户地区并完成安全检查，可以在本地手动运行桥接器交互式 `setup`。不应把凭证发给 Codex。

云端脚本为待真实验证的雏形，需明确开关和日期：

```powershell
# 将来的操作示例；现在不需要执行
.\scripts\sync.ps1 -Mode Cloud -EnableCloud -StartDate 2026-10-01 -EndDate 2026-10-07
```

云端步骤是桥接器同步 → 本地 JSON 导出 → hub 导入。上游输出只存到 `work/logs/`，不回显账号信息；失败会中止后续步骤。目前导出整个桥接缓存，以便纳入已缓存的历史修正。真实首次验证通过后，再考虑每天重取近期 7–14 天并定期回补更早范围；小米之后修正早期数据时需重取对应范围。

后续计划任务应调用脚本并检查退出状态，同时保证没有同库并行同步。任务注册、数据展示给 AI 和 MCP 接入都留待你确认具体范围后进行。完整操作清单见 [后续步骤](docs/NEXT_STEPS.md)。

## 文件导航

| 文件 | 用途 |
| --- | --- |
| `src/healthhub/validation.py` | 导出信封、指标和凭证检查 |
| `src/healthhub/store.py` | SQLite、事务、去重、更新、审计和摘要 |
| `src/healthhub/cli.py` | validate / import / sync / summary 命令 |
| `scripts/setup.ps1`、`test.ps1`、`sync.ps1` | Windows 工作入口 |
| `scripts/poc.py`、`verify_bridge.py` | 无账号合成链路和上游验证 |
| `tests/` | 合成测试，含全部 10 类数据集 |
| `docs/BRIDGE_EVALUATION.md` | 候选桥接器版本、兼容性、许可和来源 |
| `docs/VALIDATION.md` | 本次实测结果与复现方式 |
| `docs/NEXT_STEPS.md` | 地区、凭证、真实兼容性和远程仓库待办 |

`data/`、`work/`、`private/`、`.venv/`、数据库、导出和日志全部被 Git 忽略。Git 仅跟踪代码、说明和合成测试；已配置 `origin` 为 `https://github.com/ToastmastersLee/MiFitnessHealthHub.git`，尚未推送。

`requirements-win-py313.lock.txt` 保存本轮 Windows Python 3.13.5 依赖版本；同平台复现可用 `python -m pip install -r requirements-win-py313.lock.txt`，其他平台/次版本需重新验证依赖。
