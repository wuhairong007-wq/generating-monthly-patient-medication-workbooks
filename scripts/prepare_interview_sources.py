#!/usr/bin/env python3
"""Prepare source-backed interview eligibility and evidence; never invent dialogue."""
import argparse
import calendar
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path

from extract_insight_sources import clean, filter_period, normalize_patient_id, read_source

REQUIRED_ROLES = {"patients", "healthPlans", "tracking", "followups", "symptomAssessments"}
MONTHLY_REQUIRED_ROLES = {"patients", "medicationReminders", "followups", "symptomAssessments"}
SEVERITIES = {"轻度": 1, "中度": 2, "高度": 3, "重度": 3}


def parse_research_period(value):
    text = clean(value)
    month = re.fullmatch(r"(\d{4})(?:年|-)(\d{1,2})月?", text)
    if month:
        year, number = map(int, month.groups())
        return date(year, number, 1), date(year, number, calendar.monthrange(year, number)[1])
    parts = [part.strip() for part in text.split("至")]
    if len(parts) not in (1, 2):
        raise ValueError("调研时间须为 YYYY年M月、YYYY-MM、YYYY-MM-DD 或日期范围")
    try:
        start, end = date.fromisoformat(parts[0]), date.fromisoformat(parts[-1])
    except ValueError as error:
        raise ValueError("调研时间须为有效月份、日期或 YYYY-MM-DD 至 YYYY-MM-DD") from error
    if start > end:
        raise ValueError("调研时间开始日期不能晚于结束日期")
    return start, end


def prepare_interview(request):
    dialogue_mode = request.get("dialogueMode", "simulated")
    if dialogue_mode not in {"simulated", "actual", "outline"}:
        raise ValueError("dialogueMode只能为simulated、actual或outline")
    count = request.get("count")
    if type(count) is not int or count < 1:
        raise ValueError("调研数量必须为正整数")
    method = request.get("researchMethod", "深度访谈")
    if method not in {"电话随访", "深度访谈"}:
        raise ValueError("调研方式只能为电话随访或深度访谈")
    include_mild = request.get("includeMild", False)
    if type(include_mild) is not bool:
        raise ValueError("includeMild必须为布尔值")
    start, end = parse_research_period(request.get("researchTime"))
    paths = [Path(path).expanduser().resolve() for path in request.get("sourcePaths", [])]
    if len(paths) not in (5, 6):
        raise ValueError("患者调研访谈须提供5或6份Excel资料")
    if len(set(paths)) != len(paths):
        raise ValueError("依据文件路径存在重复")
    data, diagnostics = {}, {}
    for path in paths:
        if not path.is_file():
            raise ValueError(f"文件不存在：{path}")
        role, records, header_row = read_source(path)
        if role not in REQUIRED_ROLES | MONTHLY_REQUIRED_ROLES | {"adverseEvents"}:
            raise ValueError(f"访谈不接受工作簿角色：{role}")
        if role in data:
            raise ValueError(f"工作簿角色重复：{role}")
        data[role] = filter_period(role, records, start, end)
        diagnostics[role] = {"path": str(path), "headerRow": header_row,
                             "sourceRows": len(records), "includedRows": len(data[role])}
    monthly = "medicationReminders" in data
    required = MONTHLY_REQUIRED_ROLES if monthly else REQUIRED_ROLES
    unexpected = data.keys() - required - {"adverseEvents"}
    if unexpected:
        raise ValueError("不能混合月度与旧版访谈资料角色：" + ", ".join(sorted(unexpected)))
    missing = required - data.keys()
    if missing:
        raise ValueError(f"缺少工作簿角色：{', '.join(sorted(missing))}")
    ids = [normalize_patient_id(row) for row in data["patients"]]
    if not ids or any(not value for value in ids):
        raise ValueError("患者主表为空或存在空userid")
    duplicates = [value for value, total in Counter(ids).items() if total > 1]
    if duplicates:
        raise ValueError(f"患者主表userid存在重复：{duplicates[0]}")
    if "adverseEvents" not in data:
        raise ValueError("缺少不良反应清单，无法建立受访资格；患者标签或风险评分不能替代事件严重度")
    known_ids = set(ids)
    for role, rows in data.items():
        if role != "patients":
            data[role] = [row for row in rows if normalize_patient_id(row) in known_ids]
            diagnostics[role]["unmatchedRows"] = len(rows) - len(data[role])
            diagnostics[role]["matchedRows"] = len(data[role])
    severity_by_id = {}
    for event in data["adverseEvents"]:
        userid = normalize_patient_id(event)
        if userid not in known_ids:
            continue
        raw_severity = clean(event.get("不良反应严重程度分级"))
        normalized = re.fullmatch(r"(轻度|中度|高度|重度)(?:患者|[（(][123]级[）)])?", raw_severity)
        severity = normalized[1] if normalized else raw_severity
        if severity not in SEVERITIES:
            raise ValueError(f"{userid}不良反应严重程度无效：{severity}")
        severity_by_id[userid] = max(severity_by_id.get(userid, 0), SEVERITIES[severity])
    eligible = [userid for userid in ids if severity_by_id.get(userid, 0) >= (1 if include_mild else 2)]
    eligible.sort(key=lambda userid: -severity_by_id[userid])  # Equal severity retains source order.
    if len(eligible) < count:
        raise ValueError(f"符合不良反应严重度条件的患者可选{len(eligible)}人，需要{count}人，停止生成")
    selected = []
    for userid in eligible[:count]:
        selected.append({
            "userid": userid,
            "severity": {1: "轻度", 2: "中度", 3: "高度"}[severity_by_id[userid]],
            "evidence": {role: [row for row in rows if normalize_patient_id(row) == userid]
                         for role, rows in data.items()},
        })
    return {
        "researchTime": request["researchTime"], "researchMethod": method,
        "inputMode": "monthly" if monthly else "legacy",
        "dialogueMode": dialogue_mode, "simulationAuthorized": dialogue_mode == "simulated",
        "outputKinds": ["records"] if method == "电话随访" else ["analysis", "records"],
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "includeMild": include_mild, "requestedCount": count,
        "eligiblePatientCount": len(eligible), "selectedPatients": selected,
        "sourceDiagnostics": diagnostics,
        "dialogueProvenance": "本文件仅为源数据和受访资格，不证明访谈已发生；默认模拟模式已获技能配置授权，无需再次确认，后续问答须作为模拟情景交付。" if dialogue_mode == "simulated" else "本文件仅为源数据和受访资格；真实原话须来自实际访谈，提纲模式不生成患者回答。",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    request = json.loads(Path(args.request).read_text(encoding="utf-8"))
    result = prepare_interview(request)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    print(json.dumps({"output": str(output), "selectedCount": len(result["selectedPatients"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
