#!/usr/bin/env python3
import argparse
import hashlib
import json
import re
from datetime import datetime, time, timedelta
from pathlib import Path


REQUIRED_MEDICATION_FIELDS = [
    "drugName", "specification", "singleDose", "route", "frequency",
    "medicationTime", "treatmentDays", "precautions",
]
ROUTE_WORDS = re.compile(r"口服|肌肉注射|肌内注射|静脉滴注|静脉注射|皮下注射")


def load_json(path):
    return json.loads(Path(path).expanduser().resolve().read_text(encoding="utf-8"))


def confirmation_time(userid, activated_at):
    latest = datetime.combine(activated_at.date(), time(21, 59, 59))
    candidate = activated_at + timedelta(minutes=30)
    if candidate <= latest:
        return candidate.replace(microsecond=0)
    if activated_at < latest:
        available = max(int((latest - activated_at).total_seconds()), 1)
        digest = int(hashlib.sha256(userid.encode()).hexdigest()[:8], 16)
        return (activated_at + timedelta(seconds=1 + digest % available)).replace(microsecond=0)
    next_day = activated_at.date() + timedelta(days=1)
    if next_day.month == activated_at.month:
        digest = int(hashlib.sha256(userid.encode()).hexdigest()[:8], 16)
        return datetime.combine(next_day, time(6 + digest % 4, digest % 60, digest // 60 % 60))
    raise ValueError(f"{userid}在激活当月不存在合法确认时间")


def text_contains_any(text, values):
    return any(str(value) in text for value in values)


def matches(patient, conditions):
    checks = []
    if "diseaseEqualsAny" in conditions:
        checks.append(patient["disease"] in conditions["diseaseEqualsAny"])
    if "diseaseContainsAny" in conditions:
        checks.append(text_contains_any(patient["disease"], conditions["diseaseContainsAny"]))
    if "genderAny" in conditions:
        checks.append(patient["gender"] in conditions["genderAny"])
    if "ageMin" in conditions:
        checks.append(patient["age"] >= int(conditions["ageMin"]))
    if "ageMax" in conditions:
        checks.append(patient["age"] <= int(conditions["ageMax"]))
    if "allergyContainsAny" in conditions:
        checks.append(text_contains_any(patient["allergyHistory"], conditions["allergyContainsAny"]))
    if "allergyNotContainsAny" in conditions:
        checks.append(not text_contains_any(patient["allergyHistory"], conditions["allergyNotContainsAny"]))
    if "aeEqualsAny" in conditions:
        checks.append(patient["adverseEvent"] in conditions["aeEqualsAny"])
    return all(checks) if checks else True


def validated_medication(raw, patient):
    medication = dict(raw)
    for rule in medication.pop("ageDoseRules", []):
        if matches(patient, {key: rule[key] for key in ("ageMin", "ageMax") if key in rule}):
            if "singleDose" in rule:
                medication["singleDose"] = rule["singleDose"]
            if "precautions" in rule:
                medication["precautions"] = f'{medication.get("precautions", "")}；{rule["precautions"]}'.strip("；")
            break
    sex_note = medication.pop("femalePrecautions", "") if patient["gender"] == "女" else medication.pop("malePrecautions", "")
    medication.pop("femalePrecautions", None)
    medication.pop("malePrecautions", None)
    medication.pop("avoidIfAllergyContains", None)
    medication.pop("role", None)
    medication.pop("rationale", None)
    for field in REQUIRED_MEDICATION_FIELDS:
        if field not in medication or medication[field] in (None, ""):
            raise ValueError(f'{patient["userid"]}药品{medication.get("drugName", "")}缺少{field}')
    if not re.fullmatch(r"每日\d+次", str(medication["frequency"])):
        raise ValueError(f'{medication["drugName"]}频次必须为每日N次')
    if ROUTE_WORDS.search(str(medication["medicationTime"])):
        raise ValueError(f'{medication["drugName"]}用药时间混入给药途径')
    if not isinstance(medication["treatmentDays"], int) or medication["treatmentDays"] <= 0:
        raise ValueError(f'{medication["drugName"]}疗程天数必须为正整数')
    notes = [str(medication["precautions"]).strip("；")]
    if sex_note:
        notes.append(str(sex_note).strip("；"))
    if patient["allergyHistory"] != "无":
        notes.append(f'既往过敏史：{patient["allergyHistory"]}，用药前再次核对')
    if patient["adverseEvent"] not in {"否", "无", "未发生"}:
        notes.append(f'本月AE记录为{patient["adverseEvent"]}，继续用药前先评估')
    medication["precautions"] = "；".join(filter(None, notes))
    return medication


def safe_for_allergy(medication, allergy):
    if allergy == "无":
        return True
    return not text_contains_any(allergy, medication.get("avoidIfAllergyContains", []))


def prescription_entry(medication):
    return (
        f'{medication["drugName"]} 规格{medication["specification"]}，每次{medication["singleDose"]}，'
        f'{medication["route"]}，{medication["frequency"]}，{medication["medicationTime"]}，'
        f'疗程{medication["treatmentDays"]}天；{medication["precautions"]}；须经医师或药师审核'
    )


def choose_surgery(profile, patient):
    if profile["productType"] == "用药":
        return ""
    for rule in profile.get("surgeryRules", []):
        if matches(patient, rule.get("when", {})):
            return str(rule.get("surgeryName", "")).strip()
    raise ValueError(f'{patient["userid"]}没有匹配到规范手术方案')


def validate_profile(profile):
    if profile.get("schemaVersion") != 2:
        raise ValueError("product profile schemaVersion必须为2")
    if "baseCompanions" in profile or "conditionalGroups" in profile:
        raise ValueError("schema v2不得使用baseCompanions或顶层conditionalGroups")

    for adjunct in profile.get("directProductAdjuncts", []):
        if adjunct.get("role") != "directProductAdjunct" or not str(adjunct.get("rationale", "")).strip():
            raise ValueError("直接产品辅助品必须声明role和rationale")

    plans = profile.get("diseasePlans")
    if not isinstance(plans, list) or not plans:
        raise ValueError("product profile必须包含非空diseasePlans")

    plan_ids = []
    for plan in plans:
        plan_id = str(plan.get("id", "")).strip()
        if not plan_id:
            raise ValueError("疾病方案id不能为空")
        plan_ids.append(plan_id)
        when = plan.get("when", {})
        if not (when.get("diseaseEqualsAny") or when.get("diseaseContainsAny")):
            raise ValueError(f"{plan_id}的diseasePlan.when必须包含疾病条件")
        if not plan.get("evidence"):
            raise ValueError(f"{plan_id}疾病方案缺少权威依据")
        if not isinstance(plan.get("allowProductOnly"), bool):
            raise ValueError(f"{plan_id}必须显式设置allowProductOnly")
        if not isinstance(plan.get("medicationGroups", []), list):
            raise ValueError(f"{plan_id}的medicationGroups必须为数组")
    if len(plan_ids) != len(set(plan_ids)):
        raise ValueError("疾病方案id不得重复")


def choose_disease_plan(profile, patient):
    matched = [plan for plan in profile["diseasePlans"] if matches(patient, plan["when"])]
    if not matched:
        raise ValueError(f'{patient["userid"]}的疾病{patient["disease"]}没有匹配的diseasePlan')
    if len(matched) > 1:
        plan_ids = "、".join(str(plan["id"]) for plan in matched)
        raise ValueError(f'{patient["userid"]}的疾病{patient["disease"]}同时匹配多个diseasePlan：{plan_ids}')
    return matched[0]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--patients", required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    extracted = load_json(args.patients)
    profile = load_json(args.profile)
    patients = extracted["patients"]

    validate_profile(profile)
    if profile.get("productType") not in {"用药", "器械"}:
        raise ValueError("产品类型仅支持用药或器械")
    product_name = str(profile.get("productName", "")).strip()
    if not product_name:
        raise ValueError("产品名称为空")
    if not profile.get("evidence"):
        raise ValueError("product profile必须记录至少一条权威依据")
    if profile["productType"] == "用药" and profile.get("baseMedication", {}).get("drugName") != product_name:
        raise ValueError("用药产品必须作为baseMedication且名称完全一致")

    records, medication_items, reviewed_patients = [], [], []
    for patient in patients:
        raw_medications = []
        if profile.get("baseMedication"):
            raw_medications.append(profile["baseMedication"])
        raw_medications.extend(profile.get("directProductAdjuncts", []))

        disease_plan = choose_disease_plan(profile, patient)
        disease_medications = []
        for group in disease_plan.get("medicationGroups", []):
            if not matches(patient, group.get("when", {})):
                continue
            choice = next((item for item in group.get("alternatives", []) if safe_for_allergy(item, patient["allergyHistory"])), None)
            if choice:
                disease_medications.append(choice)
            elif group.get("required", False):
                raise ValueError(f'{patient["userid"]}条件组{group.get("id", "")}无安全替代药')
        if not disease_medications and not disease_plan["allowProductOnly"]:
            raise ValueError(f'{patient["userid"]}的疾病方案{disease_plan["id"]}未生成联合药且未允许产品单药')
        raw_medications.extend(disease_medications)

        if not raw_medications:
            raise ValueError(f'{patient["userid"]}没有生成任何用药')
        medications = [validated_medication(raw, patient) for raw in raw_medications]
        names = [item["drugName"] for item in medications]
        if len(names) != len(set(names)):
            raise ValueError(f'{patient["userid"]}联合用药出现重复药品')
        if len(names) > 5:
            raise ValueError(f'{patient["userid"]}联合用药超过5项，需人工复核')

        surgery_name = choose_surgery(profile, patient)
        records.append({
            "userid": patient["userid"],
            "combinedMedication": names,
            "prescriptionList": " + ".join(prescription_entry(item) for item in medications),
            "surgeryName": surgery_name,
        })
        for medication in medications:
            medication_items.append({
                "userid": patient["userid"],
                **{field: medication[field] for field in [
                    "drugName", "specification", "singleDose", "frequency",
                    "medicationTime", "treatmentDays", "precautions",
                ]},
            })
        activated_at = datetime.fromisoformat(patient["activateTime"])
        confirmed_at = confirmation_time(patient["userid"], activated_at)
        days = sorted(set(item["treatmentDays"] for item in medications))
        cycle = "、".join(f"{value}天" for value in days)
        global_notes = "；".join(profile.get("globalNotes", []))
        reviewed_patients.append({
            **patient,
            "confirmationTime": confirmed_at.strftime("%Y-%m-%d %H:%M:%S"),
            "medicationPlan": (
                f'{patient["gender"]}，{patient["age"]}岁，疾病为{patient["disease"]}，'
                f'既往过敏史：{patient["allergyHistory"]}。用药草案：{"、".join(names)}；'
                f'{global_notes}。实际适应证、剂量、疗程及相互作用须由医师或药师复核，不作疗效承诺。'
            ),
            "medicationCycle": cycle,
        })

    userids = [patient["userid"] for patient in patients]
    if [record["userid"] for record in records] != userids:
        raise AssertionError("records userid顺序不一致")
    output = {
        "meta": {
            "source": extracted["source"],
            "sourceTitle": extracted.get("title", ""),
            "productType": profile["productType"],
            "productName": product_name,
            "patientCount": len(patients),
            "monthLabel": max(extracted["summary"].get("activationMonths", {"": 0}), key=extracted["summary"].get("activationMonths", {"": 0}).get),
            "evidence": profile["evidence"],
        },
        "patients": reviewed_patients,
        "records": records,
        "medicationItems": medication_items,
    }
    target = Path(args.output).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    distribution = {str(count): sum(len(record["combinedMedication"]) == count for record in records) for count in sorted(set(map(lambda r: len(r["combinedMedication"]), records)))}
    print(json.dumps({"patientCount": len(patients), "medicationRows": len(medication_items), "medicationCountDistribution": distribution}, ensure_ascii=False))


if __name__ == "__main__":
    main()
