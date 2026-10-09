# MiFitnessHealthHub 交接与换机恢复手册

已于 2026-10-09 在 Windows 本机完成项目搭建。

```text
D:\Github\MiFitnessHealthHub
```

这是仓库内的正式交接入口，随 Git 一起保存。上面的路径是首次搭建位置；换机后可以使用其他克隆目录，后续命令均在项目根目录执行。

**当前获取个人数据的入口：[官方导出与多年历史处理](docs/PERSONAL_DATA_ONBOARDING.md)。** Zepp Life 官方 CSV 已可离线导入，参见 [导入及报告重建](docs/ZEPP_LIFE_IMPORT.md)；Mi Fitness 官方导出仍待适配。

Python 3.11+ 项目声明；本机实际使用 Miniconda Python 3.13.5 创建的独立 `.venv`。SQLite 核心不需要第三方运行依赖，桥接器独立安装并固定提交。

## 主要文件

| 文件 | 内容 |
| --- | --- |
| [README.md](README.md) | 快速开始、命令、配置、数据链路和限制 |
| [pyproject.toml](pyproject.toml) | Python 版本、打包和 healthhub 命令 |
| [requirements.txt](requirements.txt) | 核心安装入口 |
| [requirements-bridge.txt](requirements-bridge.txt) | 固定桥接器提交 |
| [requirements-dev.txt](requirements-dev.txt) | 测试及代码检查依赖 |
| [requirements-win-py313.lock.txt](requirements-win-py313.lock.txt) | 本轮 Windows/Python 3.13 依赖版本快照 |
| [.gitignore](.gitignore)、[.env.example](.env.example) | 私有目录排除和不含凭证的配置示例 |
| [validation.py](src/healthhub/validation.py) | 信封、时间、指标、凭证字段校验 |
| [store.py](src/healthhub/store.py) | SQLite 事务、去重、更新、账号绑定及导入审计 |
| [cli.py](src/healthhub/cli.py) | validate / import / sync / summary |
| [setup.ps1](scripts/setup.ps1)、[test.ps1](scripts/test.ps1)、[sync.ps1](scripts/sync.ps1) | PowerShell 工作入口；默认离线同步 |
| [poc.py](scripts/poc.py)、[verify_bridge.py](scripts/verify_bridge.py) | 合成端到端 PoC、原始上游演示和选定上游测试 |
| [测试](tests/test_pipeline.py) | 合成数据验证，含全 10 类数据集测试 |
| [桥接器评估](docs/BRIDGE_EVALUATION.md) | 版本、兼容性证据、许可及固定版本来源 |
| [验证记录](docs/VALIDATION.md) | 本轮结果及复现命令 |
| [后续步骤](docs/NEXT_STEPS.md) | GitHub 仓库、设备地区、凭证前提和真实验证待办 |
| [隐私约定](docs/PRIVACY.md) | 凭证、数据分享、明文 SQLite 与本机 ACL 边界 |

## 实测结果

- 本项目测试：64 passed；上游选定离线测试：34 passed。
- 原始上游合成演示：4 条记录，JSON + 10 个 CSV 导出成功。
- 桥接导出 → Hub SQLite：首次新增 4；再次导入新增 0、更新 0、不变 4。
- 全部 10 类数据集的合成导入、更新、坏记录拒绝、账号混入拒绝和 null 保留通过。
- SQLite quick_check = ok；PowerShell 语法与本地同步通过；Ruff 和 pip check 通过。
- Python 3.11 语法兼容检查通过；运行时只测试了 3.13.5。
- 没有执行真实登录、读取真实账号凭证、上传私人数据或注册计划任务。

合成产物位于 `D:\Github\MiFitnessHealthHub\data\poc\`，均被 Git 忽略。真实数据收件箱为 `data/inbox/`，与 PoC 分离。

## 桥接器结论

[shkyyy18/mi_fitness_data_bridge](https://github.com/shkyyy18/mi_fitness_data_bridge) 是非官方实验性项目。固定版本 0.3.3，提交 `ae70f5e6e167474e93d4c2beeb8ae3d3297d5ade`；当前 AGPL-3.0-only。本项目消费导出结果，不复制其连接器实现。

上游明确没有已验证设备名单，当前需已有 `user_id` 和 `passToken`，没有一键授权或本项目已验证的凭证获取路径。合成测试只证明本地链路；手环 9 的具体型号、固件、账号地区与真实云端兼容性仍未验证。

## Git 状态

- 本地仓库：`D:\Github\MiFitnessHealthHub\.git`。
- 分支：`main`；初始提交：`e5c3f18`。
- 核心代码、依赖声明、测试及本手册均由 Git 跟踪；当前状态以 `git status` 为准。
- 数据库、JSON 导出、CSV、日志、work 和 venv 不在跟踪列表。
- 用户已创建仓库；origin 为 `https://github.com/ToastmastersLee/MiFitnessHealthHub.git`，本次尚未推送。推送代码后才可在另一台机器从 GitHub 恢复该项目。

## 换机器恢复（仓库已推送之后）

前提：新 Windows 机器安装 Git 和 Python 3.11+，可访问 GitHub 和 Python 包下载源。推荐继续使用 Miniconda Python；无须复制旧机器的虚拟环境。

在你选择的项目父目录打开 PowerShell：

```powershell
git clone https://github.com/ToastmastersLee/MiFitnessHealthHub.git MiFitnessHealthHub
Set-Location -LiteralPath '.\MiFitnessHealthHub'
.\scripts\setup.ps1 -WithBridge
.\scripts\test.ps1
.\.venv\Scripts\python.exe scripts/poc.py
.\.venv\Scripts\python.exe scripts/verify_bridge.py
```

`setup.ps1 -WithBridge` 会重建虚拟环境、安装依赖，并将上游示例检出到固定提交；`poc.py` 会重建合成数据库与导出。首次需要联网下载依赖，测试和 PoC 无需小米账号。

核心离线工具不需要桥接器时，可只运行 `scripts/setup.ps1`。相同 Windows / Python 3.13 环境的精确依赖版本记录在 `requirements-win-py313.lock.txt`；常规安装使用依赖范围，重新跑测试检查实际解析版本。

### Git 能恢复的内容

源码、PowerShell 脚本、测试、依赖声明、配置示例、桥接器评估、验证记录和本手册均可随克隆恢复。文档采用仓库内相对链接，移动项目目录后仍然可用。无需依赖原 Codex 聊天目录或读取聊天历史。

### 需另行恢复的私有内容

`data/`、`backups/`、`.env`、日志与 Windows 凭证存储不随 Git 同步。PoC 合成数据可以重跑重建；实际 Zepp Life 原始导出、数据库及报告必须由用户通过自己的安全备份单独迁移；迁移 SQLite 前停止所有写入程序，使用一致性备份，避免复制正在写入的数据库。

凭证在新机器上由用户重新交互式配置，不能通过 Git 迁移，也不放进本手册。Windows 计划任务和 MCP 连接需要单独建立；本轮没有注册它们。代码和说明可直接恢复，私有数据迁移不能由 Git 替代。

## 现在可执行

```powershell
# 在当前项目根目录执行
.\scripts\test.ps1
.\.venv\Scripts\python.exe scripts/poc.py
```

接下来由用户在官方页面自行申请历史数据副本，保存到被 Git 忽略的 private/ 目录，并授权本地解析具体文件。真实桥接同步前再确认 Mi Fitness 账户地区和可信凭证获取前提；不要把任何凭证发到聊天。当前云端脚本只提供带明确开关和日期范围的待验证雏形。

## Zepp Life 历史的恢复

适配器为 `src/healthhub/zepp.py`；本地页面生成器为 `src/healthhub/zepp_report.py`。
恢复 private 中原始导出后，按 [说明](docs/ZEPP_LIFE_IMPORT.md) 运行 `scripts/import_zepp.ps1`。
数据详情和统计仅保存在 `private/analysis/zepp-life/`；本手册不记录个人数据数量、年份或账号。
