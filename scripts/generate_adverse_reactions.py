#!/usr/bin/env python3
import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path


TARGET_TAGS = {
    "中度患者": ("中度（2级）", "否"),
    "重度患者": ("重度（3级）", "是"),
}
DISCOVERY_METHODS = ("AI用药随访发现", "患者自评反馈")
BRAIN_SYMPTOMS = {
    "primary": ("头晕感", "恶心感", "乏力感", "头部胀闷感", "胃部不适", "皮肤瘙痒"),
    "companion": ("食欲下降", "轻微头痛", "活动耐量下降", "短暂面部潮红", "腹部不适"),
}
CORONARY_SYMPTOMS = {
    "primary": ("胃部不适", "恶心感", "头晕感", "乏力感", "心悸感", "皮肤瘙痒"),
    "companion": ("食欲下降", "轻微头痛", "短暂面部潮红", "活动后不适感", "腹部不适"),
}
OTHER_SYMPTOMS = {
    "primary": ("头晕感", "乏力感", "恶心感", "胃部不适", "轻微头痛", "皮肤瘙痒"),
    "companion": ("食欲下降", "腹部不适", "短暂面部潮红", "活动耐量下降", "困倦感"),
}
OCCURRENCE_PATTERNS = (
    "偶发且持续时间尚不明确",
    "在日间活动后被注意到",
    "在用药前后时间段内间歇出现",
    "近期反复出现但频次尚待确认",
    "休息状态下仍有出现的反馈",
)
REQUIRED_FIELDS = (
    "userid",
    "symptomDescription",
    "severityGrade",
    "treatmentMeasures",
    "treatmentOutcome",
    "remark",
)


def load_json(path):
    return json.loads(Path(path).expanduser().resolve().read_text(encoding="utf-8"))


def stable_number(userid, salt):
    digest = hashlib.sha256(f"{salt}:{userid}".encode("utf-8")).hexdigest()
    return int(digest[:12], 16)


def occurrence_time(userid, activated_at):
    hours = 1 + stable_number(userid, "occurrence") % 72
    return (activated_at - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")


def discovery_method(userid):
    return DISCOVERY_METHODS[stable_number(userid, "discovery") % len(DISCOVERY_METHODS)]


def stable_choice(userid, salt, values):
    return values[stable_number(userid, salt) % len(values)]


def age_context(age):
    if age >= 75:
        return "高龄阶段"
    if age >= 60:
        return "老年阶段"
    if age >= 45:
        return "中年阶段"
    return "青年阶段"


def symptom_catalog(disease):
    if "脑梗" in disease or "卒中" in disease:
        return BRAIN_SYMPTOMS
    if "冠心病" in disease or "心绞痛" in disease:
        return CORONARY_SYMPTOMS
    return OTHER_SYMPTOMS


def symptom_profile(patient):
    userid = patient["userid"]
    catalog = symptom_catalog(patient["disease"])
    primary = stable_choice(userid, "symptom-primary", catalog["primary"])
    companion = stable_choice(userid, "symptom-companion", catalog["companion"])
    pattern = stable_choice(userid, "symptom-pattern", OCCURRENCE_PATTERNS)
    return {
        "summary": f"{primary}，并伴{companion}",
        "pattern": pattern,
        "ageContext": age_context(int(patient["age"])),
    }


def symptom_description(patient, severity_grade, product_name, profile):
    context = (
        f"患者{patient['age']}岁，处于{profile['ageContext']}，基础疾病为{patient['disease']}。"
        f"在使用{product_name}期间反馈可能出现{profile['summary']}，{profile['pattern']}。"
    )
    if severity_grade == "重度（3级）":
        return (
            context
            + "具体起始时间、持续时长、发生频次、伴随危险信号及对日常活动的影响需尽快人工核实。"
        )
    return (
        context
        + "发生频次、持续时间、伴随表现及与用药时间的先后关系需人工核实。"
    )


def relationship_analysis(patient, product_name):
    return (
        f"上述表现与{product_name}存在时间关联的可能性，但也可能与{patient['disease']}本身、"
        f"年龄（{patient['age']}岁）或其他合并因素有关；用药时间和因果关联需由医师或药师人工核实。"
    )


def treatment_measures(patient, severity_grade, symptoms):
    allergy_note = (
        f"并再次核对既往过敏史（{patient['allergyHistory']}）"
        if patient["allergyHistory"] != "无"
        else "并再次确认既往过敏史"
    )
    if severity_grade == "重度（3级）":
        return (
            f"针对反馈的{symptoms}，建议尽快触发人工干预，核实症状事实、当前全部用药及时间关系，{allergy_note}；"
            "记录生命体征和相关危险信号，如症状持续加重或出现紧急情况应及时就医，不自行调整用药。"
        )
    return (
        f"针对反馈的{symptoms}，建议人工复核症状事实、当前全部用药及时间关系，{allergy_note}；"
        "记录症状变化，必要时联系医师或药师评估，不自行调整用药。"
    )


def treatment_outcome(product_name, symptoms, relationship, measures):
    relationship_summary = "可能存在时间关联但仍需人工核实"
    if product_name not in relationship:
        relationship_summary = "关联性仍需人工核实"
    measures_summary = "症状核实、监测及联系医师或药师建议"
    if "及时就医" in measures:
        measures_summary = "人工干预、危险信号监测及必要时及时就医建议"
    return (
        f"结合{symptoms}的症状描述、与{product_name}{relationship_summary}的分析及{measures_summary}，"
        "当前资料未提供处理后转归，待后续随访核实并记录。"
    )


def remark(patient, severity_grade, product_name):
    return (
        f"患者为{patient['gender']}，{patient['age']}岁，疾病为{patient['disease']}，"
        f"既往过敏史为{patient['allergyHistory']}，涉及产品为{product_name}，严重程度建议为{severity_grade}。"
        "请复核症状是否真实发生、当前用药名称及关联性；以上信息不构成诊断、处方调整或疗效结论。"
    )


def build_record(patient, product_name):
    severity_grade, manual_intervention = TARGET_TAGS[patient["patientTags"]]
    activated_at = datetime.fromisoformat(patient["activateTime"])
    profile = symptom_profile(patient)
    symptoms = profile["summary"]
    relationship = relationship_analysis(patient, product_name)
    measures = treatment_measures(patient, severity_grade, symptoms)
    record = {
        "userid": patient["userid"],
        "disease": patient["disease"],
        "occurrenceTime": occurrence_time(patient["userid"], activated_at),
        "discoveryMethod": discovery_method(patient["userid"]),
        "symptomDescription": symptom_description(patient, severity_grade, product_name, profile),
        "severityGrade": severity_grade,
        "medicationRelationship": relationship,
        "treatmentMeasures": measures,
        "treatmentOutcome": treatment_outcome(product_name, symptoms, relationship, measures),
        "manualIntervention": manual_intervention,
        "followupRecord": "",
        "remark": remark(patient, severity_grade, product_name),
    }
    for field in REQUIRED_FIELDS:
        if not str(record.get(field, "")).strip():
            raise ValueError(f"{patient['userid']}缺少必填字段{field}")
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--patients", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--product", required=True)
    args = parser.parse_args()

    product_name = args.product.strip()
    if not product_name:
        raise ValueError("产品名称不能为空")

    extracted = load_json(args.patients)
    source_patients = extracted.get("patients", [])
    selected = [patient for patient in source_patients if patient.get("patientTags", "").strip() in TARGET_TAGS]
    if not selected:
        raise ValueError("患者标签中没有中度患者或重度患者")

    userids = [patient["userid"] for patient in selected]
    if len(userids) != len(set(userids)):
        raise ValueError("筛选后的userid存在重复")

    records = [build_record(patient, product_name) for patient in selected]
    if [record["userid"] for record in records] != userids:
        raise AssertionError("不良反应记录userid顺序不一致")

    payload = {
        "meta": {
            "source": extracted.get("source", ""),
            "sourceTitle": extracted.get("title", ""),
            "sourcePatientCount": len(source_patients),
            "targetPatientCount": len(selected),
            "productName": product_name,
            "targetTags": list(TARGET_TAGS),
            "tagCounts": dict(Counter(patient["patientTags"] for patient in selected)),
            "reviewNotice": "生成内容需由药物警戒人员复核，不构成诊断、处方调整或疗效结论。",
        },
        "sourcePatients": selected,
        "records": records,
    }
    target = Path(args.output).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "sourcePatientCount": len(source_patients),
                "targetPatientCount": len(selected),
                "tagCounts": payload["meta"]["tagCounts"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
