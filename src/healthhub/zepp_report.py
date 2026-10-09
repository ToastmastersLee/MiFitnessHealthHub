"""Private, standalone Zepp history view, backed exclusively by imported rows."""

from __future__ import annotations

import json
import sqlite3
import statistics
from collections import Counter
from contextlib import closing
from datetime import UTC, date, datetime
from pathlib import Path

from .validation import ValidationError


def analyze(db_path: Path, subject: str = "zepp-life") -> dict:
    if not db_path.is_file():
        raise ValidationError("Database does not exist")
    with closing(sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        if conn.execute("PRAGMA user_version").fetchone()[0] != 1:
            raise ValidationError("Unsupported local database schema version")
        integrity = conn.execute("PRAGMA quick_check").fetchone()[0]
        if integrity != "ok":
            raise ValidationError("Database integrity check failed")
        offset = conn.execute("SELECT value FROM metadata WHERE key='utc_offset'").fetchone()[0]
        raw_rows = conn.execute(
            "SELECT dataset,local_date,payload_json FROM records "
            "WHERE subject=? AND dataset LIKE 'zepp_%' ORDER BY local_date,record_key",
            (subject,),
        ).fetchall()
        imports = conn.execute(
            "SELECT source_sha256,imported_at,dataset_counts_json FROM import_runs "
            "WHERE subject=? AND source_schema='zepp-life-csv-v1' ORDER BY id DESC LIMIT 1",
            (subject,),
        ).fetchone()
    if not raw_rows or not imports:
        raise ValidationError("No official Zepp records for this subject")
    coverage, flags = {}, Counter()
    sleeps, workouts, activity = [], [], []
    for dataset, day, text in raw_rows:
        payload = json.loads(text)
        if payload.get("source") != "zepp_life_official_csv":
            raise ValidationError("Unexpected source in Zepp records")
        entry = coverage.setdefault(dataset, {"rows": 0, "first_date": day, "last_date": day})
        entry["rows"] += 1
        entry["last_date"] = day
        flags.update(payload["quality_flags"])
        normalized = payload["normalized"]
        if dataset == "zepp_sleep":
            sleeps.append({"date": day, **normalized, "flags": payload["quality_flags"]})
        elif dataset == "zepp_sport":
            workouts.append({"date": day, **normalized})
        elif dataset == "zepp_activity":
            activity.append({"date": day, **normalized})
    all_days = sorted({item["date"] for item in sleeps + activity + workouts})
    first, last = date.fromisoformat(all_days[0]), date.fromisoformat(all_days[-1])
    annual = []
    for year in range(first.year, last.year + 1):
        prefix = str(year)
        sr = [r for r in sleeps if r["date"].startswith(prefix)]
        valid = [r for r in sr if r["valid_main_sleep"]]
        wr = [r for r in workouts if r["date"].startswith(prefix)]
        ar = [r for r in activity if r["date"].startswith(prefix)]
        start = max(first, date(year, 1, 1))
        end = min(last, date(year, 12, 31))
        values = [r["time_asleep_minutes"] for r in valid]
        steps = [r["steps"] for r in ar if r["steps"] is not None]
        annual.append({
            "year": year, "window_days": (end - start).days + 1,
            "sleep_rows": len(sr), "valid_sleep_days": len(valid),
            "invalid_sleep_days": len(sr) - len(valid),
            "missing_sleep_days": (end - start).days + 1 - len(sr),
            "mean_sleep_hours": round(statistics.mean(values) / 60, 3) if values else None,
            "median_sleep_hours": round(statistics.median(values) / 60, 3) if values else None,
            "activity_days": len(ar), "steps_observed_days": len(steps),
            "mean_steps": round(statistics.mean(steps), 1) if steps else None,
            "workouts": len(wr),
            "workout_distance_km": round(sum(r["distance_m"] for r in wr) / 1000, 3),
            "workout_hours": round(sum(r["duration_seconds"] for r in wr) / 3600, 3),
            "sport_type_counts": dict(Counter(r["type_code"] for r in wr)),
        })
    return {
        "report_version": 1, "generated_at": datetime.now(UTC).isoformat(),
        "utc_offset": offset, "integrity": integrity, "coverage": coverage,
        "latest_import": {"source_sha256": imports[0], "imported_at": imports[1],
                          "datasets": json.loads(imports[2])},
        "quality_flags": dict(flags), "annual": annual,
        "sleep": sleeps, "workouts": workouts, "activity": activity,
        "notes": [
            "仅包含本次 Zepp Life 官方导出；Mi Fitness 和咕咚数据尚未合并。",
            "睡眠日期沿用来源 date；运动按开始时间转换到数据库固定 UTC 偏移。",
            "主睡眠时长=(stop-start)-wakeTime；阶段分钟单位由导出内时间差一致性支持。",
            "平均值仅含正时长、必需阶段完整、阶段与时间差相符且跨度不超过24小时的主睡眠。",
            "空 REM 保持未知；naps 原文及可解析的午睡会话另存数据库，不计入主睡眠时长。",
            "缺失或占位记录不等于没有睡眠；年度均值只描述有有效记录的夜晚。",
            "运动类型编码尚未核实，运动总距离不能直接称为跑步总距离。",
            "活动 distance/runDistance/calories 单位或含义未核实；页面仅展示该表的步数。",
            "原始 CSV 未改动；USER 账号档案未读取；未进行账号登录或联网同步。",
        ],
    }


def markdown_report(report: dict) -> str:
    lines = ["# Zepp Life 本地历史与质量报告", "", f"固定时区：UTC{report['utc_offset']}", "",
             "| 年 | 时间窗天数 | 有效主睡眠 | 占位/异常 | 缺少睡眠行 | 平均小时 | 中位小时 | 运动条数 | 运动公里 |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for row in report["annual"]:
        values = [row[key] for key in (
            "year", "window_days", "valid_sleep_days", "invalid_sleep_days", "missing_sleep_days",
            "mean_sleep_hours", "median_sleep_hours", "workouts", "workout_distance_km"
        )]
        lines.append("| " + " | ".join("未知" if v is None else str(v) for v in values) + " |")
    lines += ["", "## 解释范围", ""] + ["- " + note for note in report["notes"]]
    total = len(report["sleep"])
    invalid = sum(not row["valid_main_sleep"] for row in report["sleep"])
    rem_unknown = report["quality_flags"].get("rem_unknown", 0)
    lines += ["", "## 质量发现", "",
              f"- 高影响、高置信度：{invalid}/{total} 行主睡眠无效或为占位；已排除年度时长统计。",
              f"- 高影响、高置信度：{rem_unknown}/{total} 行 REM 未知；不能直接比较全时期 REM 趋势。",
              "- 年度样本覆盖不同，均值变化可能受到缺失夜晚影响；缺失原因尚未确定。",
              "- 中等影响、高置信度：运动类型编码未核实，按全部运动汇总并保留编码。",
              "- 中等影响、高置信度：分钟级睡眠等明细类别以导出审计为准；空文件不能支持阶段曲线分析。",
              "- 低影响：部分午睡无法解析，原文保留且排除主睡眠统计；质量标记列明数量。"]
    lines += ["", "## 导出覆盖", "", "```json", json.dumps(report["coverage"], indent=2), "```",
              "", "## 质量标记（同一行可能有多个）", "", "```json",
              json.dumps(report["quality_flags"], indent=2), "```", "",
              "来源：SQLite records 中 source=zepp_life_official_csv 的记录。",
              "导入指纹：`" + report["latest_import"]["source_sha256"] + "`", ""]
    return "\n".join(lines)


HTML = r'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'">
<title>Zepp Life · 我的历史记录</title><style>
:root{color-scheme:light;font-family:system-ui,"Microsoft YaHei",sans-serif;color:#1e3335;background:#eef3ef}
body{max-width:1200px;margin:auto;padding:32px}h1{font-size:32px;margin-bottom:8px}h2{font-size:20px}
.muted{color:#586d69;font-size:14px}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin:24px 0}
.card,section{background:white;border:1px solid #dce5df;border-radius:16px;padding:22px;margin-bottom:20px}
.cards .card{margin:0}.number{font-size:30px;font-weight:700;margin-top:8px}.controls{display:flex;gap:16px;align-items:center;flex-wrap:wrap;margin:20px 0}
select{padding:9px;border-radius:8px;border:1px solid #b3c8ba;background:white}table{width:100%;border-collapse:collapse;font-size:14px}
th,td{text-align:right;padding:11px;border-bottom:1px solid #e4ece6;white-space:nowrap}th:first-child,td:first-child{text-align:left}
.scroll{overflow:auto}.chart{width:100%;height:auto;max-height:340px}.notice{border-left:4px solid #e7a64f;background:#fff7e8;padding:14px;line-height:1.8}
li{margin:8px 0;line-height:1.6}.twocol{display:grid;grid-template-columns:1fr 1fr;gap:20px}.twocol section{min-width:0}
button{border:1px solid #b3c8ba;border-radius:8px;background:#fff;padding:9px;cursor:pointer}
@media(max-width:850px){body{padding:16px}.cards{grid-template-columns:1fr 1fr}.twocol{grid-template-columns:1fr}}
</style><body><p class="muted">个人健康档案 / Zepp Life 官方导出 / 全部在本地</p>
<h1>我的睡眠与运动历史</h1><p class="muted" id="range"></p>
<div class="controls"><label>年份 <select id="year"><option value="all">全部年份</option></select></label>
<label>月份 <select id="month"><option value="all">全年</option></select></label>
<button id="download">下载年度摘要 CSV</button></div>
<div class="cards"><div class="card">有效主睡眠<div id="sleepCount" class="number"></div><span class="muted">夜 · 排除占位和异常</span></div>
<div class="card">平均主睡眠<div id="sleepMean" class="number"></div><span class="muted">小时 · 排除午睡</span></div>
<div class="card">运动记录<div id="sportCount" class="number"></div><span class="muted">条 · 类型编码未核实</span></div>
<div class="card">运动距离<div id="distance" class="number"></div><span class="muted">公里 · 仅本来源记录</span></div></div>
<p id="selectionNote" class="notice"></p>
<section><h2 id="chartTitle">年度主睡眠平均时长</h2><svg id="chart" class="chart" viewBox="0 0 1000 310" role="img" aria-label="主睡眠平均小时柱形图"></svg><p class="muted">每根柱仅统计有有效记录的夜晚；空缺年份或月份显示“无记录”。图表与年度表按完整年份汇总，月份筛选仅影响上方统计和下方明细。</p></section>
<section><h2>年度覆盖与汇总</h2><div class="scroll"><table><thead><tr><th>年份</th><th>有效睡眠/时间窗天数</th><th>占位或异常</th><th>缺少睡眠行</th><th>均值/小时</th><th>中位/小时</th><th>平均步数</th><th>运动条数</th><th>运动公里</th></tr></thead><tbody id="annual"></tbody></table></div></section>
<div class="twocol"><section><h2>主睡眠明细</h2><p class="muted">显示筛选范围中最近 100 条；日期沿用来源 date，起止时间已换算为本地时间。</p><div class="scroll"><table><thead><tr><th>日期</th><th>开始</th><th>结束</th><th>主睡眠/小时</th><th>深睡/分钟</th><th>REM/分钟</th></tr></thead><tbody id="sleepRows"></tbody></table></div></section>
<section><h2>运动明细</h2><p class="muted">显示筛选范围中最近 100 条；编码保留原值，配速由总时长/距离推算。</p><div class="scroll"><table><thead><tr><th>开始时间</th><th>类型</th><th>公里</th><th>分钟</th><th>推算配速</th></tr></thead><tbody id="sportRows"></tbody></table></div></section></div>
<section><h2>数据边界与来源</h2><ul id="notes"></ul><p class="muted">来源文件类别：SLEEP、SPORT、ACTIVITY、HEARTRATE、BODY；其他类别为空。生成时间 <span id="generated"></span></p></section>
<script>const data=__DATA__;
const el=id=>document.getElementById(id), fmt=(n,d=1)=>n===null||n===undefined?'未知':Number(n).toFixed(d);
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
data.annual.forEach(r=>{let o=document.createElement('option');o.value=r.year;o.textContent=r.year;el('year').append(o)});
for(let m=1;m<=12;m++){let o=document.createElement('option');o.value=String(m).padStart(2,'0');o.textContent=m+'月';el('month').append(o)}
const cov=data.coverage.zepp_sleep;el('range').textContent=(cov?cov.first_date+' 至 '+cov.last_date:'')+' · UTC'+data.utc_offset+' · 只包含 Zepp Life';
el('notes').innerHTML=data.notes.map(n=>'<li>'+esc(n)+'</li>').join('');el('generated').textContent=data.generated_at;
function draw(groups){const max=Math.max(10,...groups.map(g=>g.mean||0)),w=880/groups.length;let svg='';
for(let t=0;t<=max;t+=2){let y=260-t/max*220;svg+=`<line x1="55" y1="${y}" x2="975" y2="${y}" stroke="#e3ece5"/><text x="10" y="${y+4}" font-size="13" fill="#576b62">${t}h</text>`}
groups.forEach((g,i)=>{let x=70+i*w,h=(g.mean||0)/max*220;svg+=`<rect x="${x}" y="${260-h}" width="${w*.65}" height="${h}" rx="5" fill="#367d63"/><text x="${x+w*.325}" y="${g.mean===null?245:252-h}" text-anchor="middle" font-size="12">${g.mean===null?'无记录':fmt(g.mean)}</text><text x="${x+w*.325}" y="284" text-anchor="middle" font-size="12">${g.label}</text>`});el('chart').innerHTML=svg}
function update(){let y=el('year').value,m=el('month').value;const selected=r=>(y==='all'||r.date.startsWith(y))&&(m==='all'||r.date.slice(5,7)===m);
const all=data.sleep.filter(selected),s=all.filter(r=>r.valid_main_sleep),w=data.workouts.filter(selected);
let mean=s.length?s.reduce((a,r)=>a+r.time_asleep_minutes,0)/s.length/60:null;
el('sleepCount').textContent=s.length;el('sleepMean').textContent=fmt(mean,2);el('sportCount').textContent=w.length;el('distance').textContent=fmt(w.reduce((a,r)=>a+r.distance_m,0)/1000,2);
el('selectionNote').textContent='当前筛选：'+(y==='all'?'全部年份':y+'年')+' / '+(m==='all'?'全年':Number(m)+'月')+'。睡眠汇总 '+all.length+' 行，其中 '+(all.length-s.length)+' 行占位或异常。缺少记录不能解释为没有睡眠。';
el('annual').innerHTML=data.annual.filter(r=>y==='all'||String(r.year)===y).map(r=>'<tr>'+[r.year,r.valid_sleep_days+'/'+r.window_days,r.invalid_sleep_days,r.missing_sleep_days,fmt(r.mean_sleep_hours,2),fmt(r.median_sleep_hours,2),fmt(r.mean_steps,0),r.workouts,fmt(r.workout_distance_km,2)].map(v=>'<td>'+esc(v)+'</td>').join('')+'</tr>').join('');
el('sleepRows').innerHTML=all.slice().reverse().slice(0,100).map(r=>'<tr>'+[r.date,r.valid_main_sleep?r.start_at.slice(5,16).replace('T',' '):'未知',r.valid_main_sleep?r.end_at.slice(5,16).replace('T',' '):'未知',r.valid_main_sleep?fmt(r.time_asleep_minutes/60,2):'占位/异常',fmt(r.deep_minutes,0),fmt(r.rem_minutes,0)].map(v=>'<td>'+esc(v)+'</td>').join('')+'</tr>').join('');
el('sportRows').innerHTML=w.slice().reverse().slice(0,100).map(r=>{let pace=r.derived_pace_sec_per_km,p=pace===null?'未知':Math.floor(Math.round(pace)/60)+':'+String(Math.round(pace)%60).padStart(2,'0');return '<tr>'+[r.start_at.slice(0,16).replace('T',' '),r.type_code,fmt(r.distance_m/1000,2),fmt(r.duration_seconds/60,1),p].map(v=>'<td>'+esc(v)+'</td>').join('')+'</tr>'}).join('');
let yearly=data.sleep.filter(r=>r.valid_main_sleep&&(y==='all'||r.date.startsWith(y)));
let groups=(y==='all'?data.annual.map(r=>String(r.year)):Array.from({length:12},(_,i)=>String(i+1).padStart(2,'0'))).map(label=>{let rows=yearly.filter(r=>y==='all'?r.date.startsWith(label):r.date.slice(5,7)===label);return {label:label+(y==='all'?'':'月'),mean:rows.length?rows.reduce((a,r)=>a+r.time_asleep_minutes,0)/rows.length/60:null}});
el('chartTitle').textContent=y==='all'?'年度主睡眠平均时长':y+'年每月主睡眠平均时长';draw(groups)}
el('year').onchange=update;el('month').onchange=update;
el('download').onclick=()=>{let keys=Object.keys(data.annual[0]).filter(k=>k!=='sport_type_counts'),csv='\ufeff'+keys.join(',')+'\n'+data.annual.map(r=>keys.map(k=>r[k]??'').join(',')).join('\n');let a=document.createElement('a');a.href=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));a.download='zepp-annual-summary.csv';a.click();URL.revokeObjectURL(a.href)};update();
</script></body></html>'''


def quality_notebook() -> dict:
    codes = [
        '''from pathlib import Path
import sys, json, sqlite3
root = next(p for p in [Path.cwd(), *Path.cwd().parents]
            if (p / "src/healthhub/zepp.py").is_file())
sys.path.insert(0, str(root / "src"))
from healthhub.zepp_report import analyze
db = root / "data/healthhub.db"
report = analyze(db, subject="zepp-life")
report["coverage"]''',
        '''with sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True) as conn:
    duplicates = conn.execute("SELECT dataset,record_key,COUNT(*) FROM records "
        "WHERE subject='zepp-life' AND dataset LIKE 'zepp_%' "
        "GROUP BY dataset,record_key HAVING COUNT(*)>1").fetchall()
    integrity = conn.execute("PRAGMA quick_check").fetchone()[0]
assert not duplicates and integrity == "ok"
print({"duplicate_keys": len(duplicates), "integrity": integrity})''',
        '''valid = [r for r in report["sleep"] if r["valid_main_sleep"]]
assert all(r["time_asleep_minutes"] > 0 for r in valid)
assert all(abs((__import__("datetime").datetime.fromisoformat(r["end_at"])
    - __import__("datetime").datetime.fromisoformat(r["start_at"])).total_seconds()/60
    - sum(r[k] or 0 for k in ("deep_minutes","light_minutes","rem_minutes","awake_minutes")))
    <= 1 for r in valid)
print({"sleep_rows":len(report["sleep"]),"valid_main_sleep":len(valid),
       "quality_flags":report["quality_flags"]})''',
        '''for year in report["annual"]:
    assert year["valid_sleep_days"] + year["invalid_sleep_days"] == year["sleep_rows"]
    assert year["sleep_rows"] + year["missing_sleep_days"] == year["window_days"]
print(json.dumps(report["annual"], ensure_ascii=False, indent=2))''',
    ]
    return {"nbformat": 4, "nbformat_minor": 5,
            "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python",
                                        "name": "python3"}},
            "cells": [{"id": "intro", "cell_type": "markdown", "metadata": {}, "source": [
                "# 本地主睡眠质量核验\n",
                "只读 SQLite；输出包含个人数据，请将本 notebook 保留在 private/。\n",
                "可从仓库或本文件目录运行；需要本项目 Python 环境。\n",
                "USER 档案不参与导入；分钟单位为导出内一致性推断，不是设备准确性认证。\n",
            ]}] + [{"id": f"check-{i}", "cell_type": "code", "metadata": {},
                     "execution_count": None, "outputs": [], "source": code.splitlines(True)}
                    for i, code in enumerate(codes)]}


def write_report(db_path: Path, output: Path, subject: str = "zepp-life") -> dict:
    report = analyze(db_path, subject)
    root = db_path.resolve().parent.parent
    destination = output.resolve()
    # Personal deliverables must stay in this project's ignored private tree.
    if not destination.is_relative_to(root / "private"):
        raise ValidationError("Report destination must be inside the database project's private directory")
    if any(parent.is_symlink() for parent in [output, *output.parents]):
        raise ValidationError("Report destination cannot traverse a symlink")
    for name in ("history.html", "summary.json", "quality.md", "quality_checks.ipynb"):
        if (output / name).is_symlink():
            raise ValidationError("Report file cannot be a symlink")
    output.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2)
    # Prevent inline-script termination even if future source strings gain markup.
    embedded = text.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    (output / "summary.json").write_text(text + "\n", encoding="utf-8")
    (output / "quality.md").write_text(markdown_report(report), encoding="utf-8")
    (output / "history.html").write_text(HTML.replace("__DATA__", embedded), encoding="utf-8")
    notebook = quality_notebook()
    # A nondefault subject is still a local alias; substitute it in the checks.
    for cell in notebook["cells"]:
        cell["source"] = [line.replace("zepp-life", subject) for line in cell["source"]]
    (output / "quality_checks.ipynb").write_text(json.dumps(notebook, ensure_ascii=False, indent=2),
                                              encoding="utf-8")
    return {"written": ["history.html", "summary.json", "quality.md", "quality_checks.ipynb"],
            "integrity": report["integrity"], "coverage": report["coverage"]}
