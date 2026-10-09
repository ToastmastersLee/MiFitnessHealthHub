# 用户后续操作

## 现在可用

1. 在 `D:\Github\MiFitnessHealthHub` 运行 `scripts/test.ps1` 和 `.venv/Scripts/python.exe scripts/poc.py`，查看 `data/poc/result.json`。
2. 阅读桥接器评估及隐私约定。当前只使用合成数据，没有真实登录或上传。
3. 自行在 GitHub 创建一个空仓库，推荐 `MiFitnessHealthHub`。为便于后续衔接，可不预置 README、license 或 .gitignore。
4. 将仓库 HTTPS 地址交给 Codex；本轮没有添加远程地址、创建远程仓库或推送。首次推送前再检查跟踪文件。

## 在真实账号验证前确认

- 手环具体型号：9 / 9 Pro / 9 Active；Mi Fitness 版本、手机系统、手环固件。
- Mi Fitness App 中实际账户/服务地区。不要因为居住地、语言或上游默认 cn 就推定地区。
- 是否已有通过理解并信任的途径获得的本人 `user_id` 和 `passToken`。只回答是否具备，不能把值发送到聊天。如果没有，继续用合成流程；本项目没有可靠获取向导。
- 本机 Windows keyring 后端和目录 ACL；数据库、原始 JSON、日志可能包含明文个人信息。
- 需要分析哪些数据集和日期，是否允许 Codex 接触真实指标。默认未授权这一数据分享步骤。

## 可用凭证已就绪时（由用户手动执行）

```powershell
Set-Location -LiteralPath 'D:\Github\MiFitnessHealthHub'
# 交互式输入，仅本机，不把凭证放进命令行
.\.venv\Scripts\mi-fitness-bridge.exe setup
```

`doctor` 在已有凭证时可能连接小米，属于将来的真实验证，不是本轮离线测试。先核对 region、timezone 与来源时间语义，再用短日期范围试同步。

```powershell
# 示例日期，执行前替换为实际需要的范围
.\scripts\sync.ps1 -Mode Cloud -EnableCloud -StartDate 2026-10-01 -EndDate 2026-10-07
```

首次兼容性检查只记录日期、设备型号、地区、包版本、各数据集 works / empty / fails / not tested。
与 App 相同日期的数据自行比对，不上传账号、Token、原始日志、轨迹或数据库。空数据不算证明兼容成功。

## 真实验证之后

- 若真实认证或接口失败，保存脱敏结论并保留离线导入路径；不自动尝试其他地区或第三方登录站点。
- 若成功，确定近 7–14 天重取范围和历史回补策略；跨午夜睡眠可向前后多取一天。
- 再评估 Windows 计划任务：每次计算日期范围、无同库并发、失败反馈、私有日志保留和备份策略。本轮未注册计划任务。
- 再选择 Codex 分析方式：先仅分享数据覆盖摘要；真实指标或本地 MCP 接入需另行确定允许范围。
- 只有需要在公众可访问环境分发或服务化时，再审查上游 AGPL 和隐私设计；当前基础是个人本机使用。

## 当前明确限制

- 手环 9 真实云端兼容性、认证可用性及地区行为未验证。
- 仅 JSON 桥接器导出可导入；CSV、官方账户导出 ZIP、Google Health Connect 等尚未接入。
- 只做结构及数值域校验，不做医学解释或趋势结论。
- 同 ID 最后成功导入覆盖，未保留每次旧指标版本；历史文件需移到 backups/ 避免复扫。
- 固定 UTC 偏移，不自动处理夏令时或旅行期间时区切换。
- 云端脚本尚未经真实账号验证；没有自动刷新凭证、自动账号授权、后台任务或 MCP 注册。
