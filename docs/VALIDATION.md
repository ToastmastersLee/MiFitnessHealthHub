# 本轮验证结果

日期：2026-10-09（Asia/Shanghai）。工程测试与 PoC 全部使用合成数据。另在用户授权的本机私有导出上检查了 Zepp Life 导入幂等性、原文件指纹及 SQLite 完整性，具体个人结果只保存在 private。

| 检查 | 结果 |
| --- | --- |
| 核心单元与 CLI 测试 | 64 passed |
| 上游选定离线测试 | 34 passed（export、CLI security、DB path override） |
| 上游原始 synthetic_demo.py | 成功：4 条合成记录，JSON + 10 个 CSV |
| 桥接器 → Hub PoC | 成功：首次新增 4，重跑新增 0、更新 0、不变 4 |
| 全部 10 数据集入库 | 合成测试通过：每组 1 行，重复导入不增加 |
| 更新与校验 | 同 ID 修正更新、坏行整批拒绝、账号混入拒绝、null 保留等测试通过 |
| SQLite | quick_check = ok；PoC 累计 4 行 |
| PowerShell | 全部脚本语法解析通过；test.ps1 和本地 sync.ps1 实测通过 |
| 云端保护 | 缺少 -EnableCloud 时拒绝；没有执行真实登录或云端同步 |
| Ruff | All checks passed |
| pip check | No broken requirements found |
| Python >=3.11 语法 | ast.parse feature_version=(3,11) 检查通过 |
| 实际运行环境 | Windows、Miniconda 衍生 venv、CPython 3.13.5 |

Python 3.11 / 3.12 未执行运行时测试；语法检查不能代替跨版本运行验证。上游完整套件未全量运行。真实手环 9 云端兼容性仍为 not_verified。

## 已执行命令

在 `D:\Github\MiFitnessHealthHub`：

```powershell
.\scripts\test.ps1
.\.venv\Scripts\python.exe scripts/verify_bridge.py
.\.venv\Scripts\python.exe scripts/verify_bridge.py --demo
.\.venv\Scripts\python.exe scripts/poc.py

# 本轮仅给本地同步脚本配置合成数据路径
$env:HEALTHHUB_DB = 'data/poc/synthetic_hub.db'
$env:HEALTHHUB_INBOX = 'data/poc/inbox'
.\scripts\sync.ps1 -Subject synthetic-demo
```

环境值在临时命令会话中使用，没有写入 Windows 全局环境或用户 Profile。PoC 可重复运行，已有库时首次导入也会显示 unchanged=4，这是预期幂等行为。

PoC 禁止 Python socket 网络连接；上游测试为兼容 Windows asyncio，仅允许数字回环地址，拒绝外部连接。守卫是本轮测试机制，不是对第三方任意代码的操作系统沙箱。

## 可检查的本地合成产物（均被 Git 忽略）

```text
D:\Github\MiFitnessHealthHub\data\poc\synthetic_bridge.db
D:\Github\MiFitnessHealthHub\data\poc\inbox\synthetic_bridge.json
D:\Github\MiFitnessHealthHub\data\poc\csv\
D:\Github\MiFitnessHealthHub\data\poc\synthetic_hub.db
D:\Github\MiFitnessHealthHub\data\poc\result.json
D:\Github\MiFitnessHealthHub\work\bridge-verification\
```

依赖版本快照：`requirements-win-py313.lock.txt`。它记录本轮 Windows CPython 3.13.5 安装的第三方版本和固定桥接器提交，可在相同平台环境复现。其他平台或 Python 次版本优先使用 requirements-dev.txt / requirements-bridge.txt 后重新验证，不把该快照当作跨平台锁文件。

Git 主分支为 main；代码、配置示例、说明、测试、依赖声明可跟踪。私有目录、数据库和导出不进入初始提交。已配置用户提供的远程仓库；无推送、无计划任务注册。

## Zepp Life 新增验证

- 合成 CSV 转义引号、午睡 JSON、null、UTC 跨日和未知类型代码。
- 占位/异常睡眠保留原文、排除均值；缺少日期与异常行分别计数。
- 重跑不新增，修正更新；账号混入、重复主键、坏数值和未知非空明细整份拒绝。
- 报告只能写入 private，SQLite 完整性检查通过；页面年月筛选已验证。
- 本轮实际运行仍为 Python 3.13.5；未登录或执行云端同步。
