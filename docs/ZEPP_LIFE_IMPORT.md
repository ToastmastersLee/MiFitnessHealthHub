# Zepp Life 官方 CSV：离线导入与历史页面

这是独立于 Mi Fitness 桥接器的官方导出适配器。无需账号登录或第三方运行依赖。
代码、合成测试和本操作说明随 Git 保存；个人数据、报告和导入审计保存在忽略目录。

## 运行

在仓库根目录，先把原始解压目录放到 `private/zepp-life-export/`。
保留官方 `<数字账号>_<数字时间戳>` 目录名；账号数字仅用于数据库内带盐 HMAC 绑定，不放进记录 payload 或报告。
下面 `<官方导出目录名>` 必须替换为实际目录名，不是登录凭证。

```powershell
.\scripts\import_zepp.ps1 -ExportDirectory 'private/zepp-life-export/<官方导出目录名>' -OpenReport
```

也可以分步检查：

```powershell
.\.venv\Scripts\python.exe -m healthhub validate-zepp 'private/zepp-life-export/<官方导出目录名>'
.\.venv\Scripts\python.exe -m healthhub import-zepp 'private/zepp-life-export/<官方导出目录名>' --subject zepp-life
.\.venv\Scripts\python.exe -m healthhub zepp-report --subject zepp-life
```

默认数据库为 `data/healthhub.db`；subject 与 Mi Fitness 的 `band9-local` 分开，不能盲目合并账号或日期。
每次先整份校验再以单个事务导入；重复导入去重，已有身份的数据修正采用最后成功导入版本。
不要用旧快照覆盖已经修正的新数据。输入文件不被修改或删除。

## 私有产物

- `private/analysis/zepp-life/history.html`：可直接双击打开的独立页面，无外部请求、资源或遥测。按年月筛选统计与明细；年度图表和年度表保持全年口径。
- `summary.json`：完整可重算的本地展示数据、年度统计及质量标记。
- `quality.md`：覆盖窗口、有效/异常/缺少行、缺失字段与解释范围。
- `quality_checks.ipynb`：只读 SQL/Python 核验 notebook；执行输出仍应留在 private。
- 首次实际导入时可另存 `import-audit.json`，记录每类文件校验和、首导与重跑结果；CLI 重跑不会自动覆盖这个首次审计。

`zepp-report` 只允许写入数据库所在项目的 `private/` 子树，例如数据库 `data/healthhub.db` 对应项目根目录。
它会重新生成上述四个标准产物，勿在这些生成文件中手工保存唯一副本。
换机需单独迁移原始导出与私有 SQLite；Git 仅恢复代码、文档和合成测试。

## 当前格式与边界

| 来源目录 | 支持与身份粒度 |
| --- | --- |
| ACTIVITY | 每个来源日期一行；展示步数，距离及热量保持原文 |
| SLEEP | 每个来源日期一行；保留零时长占位、阶段空值及午睡原文 |
| SPORT | 类型编码 + 转换后的开始时间；秒、米、千卡按显式列名处理 |
| HEARTRATE | 时间戳一行；原文保存 |
| BODY | 时间戳一行；`null` 保持缺失，单位不擅自推定 |
| ACTIVITY_MINUTE / ACTIVITY_STAGE / HEALTH_DATA / HEARTRATE_AUTO / SLEEP_MINUTE | 支持当前表头且为空；若非空则整份拒绝，需追加适配器 |
| USER | 不读取、不计算校验和、不入库、不复制账号档案 |

拒绝新目录、改变的表头、错误行宽、非有限/负指标、重复身份及无时区时间。
CSV 采用严格解析，并支持来源的反斜杠引号转义；缺失数字支持空字符串与字面量 `null`。
账号 HMAC 不构成匿名化；SQLite、原始导出和报告仍是私人明文数据。

**时间口径：** 默认 UTC+08:00。来源明确带 `+0000` 的时间会转换；运动按本地开始日归属。
睡眠日期保留原始 `date`，不强行改为入睡日；和本地结束日不同时会标记。
桥接 JSON 的睡眠覆盖采用开始日，两者不能未经统一直接合并。

**主睡眠口径：** 时间差减去 `wakeTime`。阶段字段分钟单位以本次格式中阶段和时间差一致性为依据，属于导出内验证。
仅正时长、跨度不超过24小时、必需阶段完整、阶段和时间差误差不超过1分钟的记录进入均值。
这些是格式与统计守卫，不是医疗阈值。零时长与异常保留原文并排除均值；没有记录不能解释为没有睡眠。
REM 为空仍为未知；计算一致性时不加缺失 REM，不把它宣称为真实零时长。
午睡 JSON 单独解析为起止会话；错误形式保留原文和标记。所有午睡均不计入页面的主睡眠均值。

运动类型代码没有官方映射证据，保留代码，不能把全部运动距离说成跑步公里数。
平均配速仅由总秒数/总米数推算；原导出的 max/min/avgPace 保留而不冒充标准单位转换。
这里没有 GPS、睡眠阶段曲线或运动瞬时心率等未返回的明细；无数据类别不代表设备完全不支持该能力。

来源记录使用 `records.dataset=zepp_*` 与 payload `source=zepp_life_official_csv` 标记。
导入审计的 schema 为 `zepp-life-csv-v1`，文件集合指纹按目录类别与原始文件字节计算，排除 USER。
报告只针对 Zepp 来源，不合并 Mi Fitness 迁移副本或咕咚记录。新来源到手后再检查重叠和覆盖。
