# 获取多年睡眠与运动记录

更新：2026-10-09。优先通过官方个人数据导出建立历史基线；非官方桥接器保留为未来增量同步候选。当前数据库只有合成记录，尚未导入任何真实睡眠或运动数据。

本流程适用于早期使用 Zepp Life / 小米运动、后来转用 Mi Fitness 的历史。中国大陆是当前规划地区；手机号 +86 不能单独证明 App 服务地区。若后续启用云端桥接，应以 Mi Fitness 实际国家/地区设置为准。

## 不需要把小米登录凭证交给 Codex

用户在小米或 Zepp 官方页面自行登录、验证并下载文件。账号号码、个人资料截图都不能代替数据导出，也不等于 API Token。本项目不保存账户截图、账号 ID、生日或其他个人资料到 Git。

## 第一步：保留 Zepp Life 历史

在 Zepp Life 中使用当年保存记录的登录方式进入，核对睡眠和运动最早可见日期。不能仅因为两个 App 显示同一小米登录方式，就假定数据已经转移。

[Zepp 官方隐私支持页面](https://www.zepp.com/privacy-support) 提供 Export data，选择 **Zepp Life** 而不是 Zepp；官方也列出 App → Profile → Setting → Account and Security 的数据权利入口。具体页面以当前 App 显示为准。先申请并保留原始导出，有日期范围时选择所需全部年份。

原始导出放到本机被 Git 忽略的目录：

```text
D:\Github\MiFitnessHealthHub\private\zepp-life-export
```

本轮已建立空目录。换机可在项目根目录执行 `New-Item -ItemType Directory -Path private/zepp-life-export -Force` 重建。这里暂不推定文件扩展名、CSV 列名或导出覆盖年份；拿到文件后再验证。

## 第二步：可选地将旧记录转入 Mi Fitness

[小米官方转移说明](https://www.mi.com/global/support/faq/details/KA-231328/) 列出：

1. Mi Fitness → Profile（我的）。当前若在 My profile 个人资料页，先返回上一层。
2. Third-party data（第三方数据）→ Zepp Life → Transfer（转移）。
3. 用户自行登录并授权保存历史记录的 Zepp Life 账户，等待完成。
4. 核对睡眠和运动的最早日期、年份以及 App 最后导入时间。

官方说明可转移运动记录和睡眠等数据；它不证明某个具体账号会完整转回所有年份。不要把“转移完成”当作历史完整性验证，也不要用迁移后的导出覆盖保存的 Zepp Life 原始副本。如果已转移，先检查现有覆盖范围，无需反复启动迁移。

## 第三步：小米官方个人数据导出

由用户打开 [小米账号官网](https://account.xiaomi.com/) 并登录当前 Mi Fitness 所用账号。

按照 [小米官方导出说明](https://www.mi.com/global/support/article/KA-11566/)：

**Privacy（隐私）→ Manage Your Data（管理你的数据）→ Mi Fitness → Download（下载）。**

按页面提示绑定或验证邮箱，并申请数据副本。有数据类别和日期范围可选时，选择睡眠、运动及目标全部年份。实际准备时间和下载方式以该账号页面通知为准，本项目不承诺固定等待时长或历史保留年限。

下载后保留原始文件，放到：

```text
D:\Github\MiFitnessHealthHub\private\xiaomi-official-export
```

本轮已建立空目录。换机可执行 `New-Item -ItemType Directory -Path private/xiaomi-official-export -Force` 重建。不要把原始导出、登录验证码、带授权信息的下载链接或截图提交到 GitHub。

## 第四步：实际导出到手之后

用户给出本地文件路径，并明确授权本地解析该份健康导出后，再进行：

1. 核对文件格式、字段、时区、单位与来源；当前导入器只支持桥接器 JSON，不能直接消费未经适配的官方导出。
2. 分别检查 Zepp Life 与 Mi Fitness 的最早/最新日期、逐年记录数量和空缺，明确哪些年份确实可用。
3. 为实际官方格式建立导入适配器，并使用脱敏合成样本验证后写入本地 SQLite。
4. 跨来源保留来源标记、处理重叠日期；运动不按同一时间盲目相加，睡眠不把原版与转移副本重复计数。
5. 生成睡眠年度/月度时长、入睡/醒来时间与有记录天数，以及运动次数、时长、距离、类型趋势。缺失数据不填成零，也不据此作医学判断。

目标是查看实际多年记录；能取得多少历史必须以导出内容和覆盖检查为依据。未取得文件前，不展示合成图表冒充个人趋势。

## GitHub 与数据的关系

项目远程已配置为 `https://github.com/ToastmastersLee/MiFitnessHealthHub.git`，对应用户提供的 SSH 仓库地址；本次尚未推送。
Git 保存代码、说明和测试；真实数据、原始导出及凭证仅留本机或用户自己的安全备份。GitHub 仓库地址不是小米数据授权。
