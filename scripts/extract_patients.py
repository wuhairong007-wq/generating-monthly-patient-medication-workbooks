#!/usr/bin/env python3
import argparse
import json
from collections import Counter
from datetime import date, datetime
from pathlib import Path

import openpyxl


EXPECTED_HEADERS = [
    "序号", "患者唯一标识", "姓名", "激活日期", "性别", "年龄", "联系电话", "所属地区",
    "疾病", "既往过敏史", "AI用药提醒次数", "AI随访次数", "症状自评完成次数",
    "患教内容阅读次数", "AI服务使用概况", "本月是否发生不良反应（AE）", "AE严重程度分级", "患者标签",
]


def as_text(value):
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def as_datetime(value, userid):
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    try:
        return datetime.fromisoformat(as_text(value))
    except ValueError as exc:
        raise ValueError(f"{userid}激活日期无效：{value}") from exc


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    source = Path(args.source).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)

    workbook = openpyxl.load_workbook(source, read_only=True, data_only=True)
    sheet = workbook.worksheets[0]
    rows = sheet.iter_rows(values_only=True)
    try:
        title_row = next(rows)
        header_row = next(rows)
    except StopIteration as exc:
        raise ValueError("患者文件至少需要标题行、表头行和数据行") from exc
    headers = [as_text(value) for value in header_row]
    if headers != EXPECTED_HEADERS:
        raise ValueError(f"第二行表头不符合18列契约：{headers}")

    patients = []
    seen = set()
    for values in rows:
        if not any(value is not None for value in values):
            continue
        row = dict(zip(headers, values))
        userid = as_text(row["患者唯一标识"])
        if not userid:
            raise ValueError("发现空userid")
        if userid in seen:
            raise ValueError(f"发现重复userid：{userid}")
        seen.add(userid)

        age_raw = row["年龄"]
        try:
            age = int(age_raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{userid}年龄无效：{age_raw}") from exc
        if age < 0 or age > 120 or float(age_raw) != age:
            raise ValueError(f"{userid}年龄无效：{age_raw}")
        activated_at = as_datetime(row["激活日期"], userid)
        gender = as_text(row["性别"])
        if gender not in {"男", "女"}:
            raise ValueError(f"{userid}性别无效：{gender}")
        disease = as_text(row["疾病"])
        if not disease:
            raise ValueError(f"{userid}疾病为空")

        patients.append({
            "sequence": int(row["序号"]),
            "userid": userid,
            "patientName": as_text(row["姓名"]),
            "activateTime": activated_at.strftime("%Y-%m-%d %H:%M:%S"),
            "gender": gender,
            "age": age,
            "disease": disease,
            "allergyHistory": as_text(row["既往过敏史"]) or "无",
            "adverseEvent": as_text(row["本月是否发生不良反应（AE）"]) or "否",
            "adverseEventGrade": as_text(row["AE严重程度分级"]),
            "patientTags": as_text(row["患者标签"]),
        })

    if not patients:
        raise ValueError("患者文件没有数据行")
    activation_months = Counter(p["activateTime"][:7] for p in patients)
    payload = {
        "source": str(source),
        "title": as_text(title_row[0] if title_row else ""),
        "headers": headers,
        "patients": patients,
        "summary": {
            "patientCount": len(patients),
            "distinctUseridCount": len(seen),
            "diseaseCounts": dict(Counter(p["disease"] for p in patients)),
            "genderCounts": dict(Counter(p["gender"] for p in patients)),
            "allergyCounts": dict(Counter(p["allergyHistory"] for p in patients)),
            "adverseEventCounts": dict(Counter(p["adverseEvent"] for p in patients)),
            "ageMin": min(p["age"] for p in patients),
            "ageMax": max(p["age"] for p in patients),
            "activationMonths": dict(activation_months),
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()

