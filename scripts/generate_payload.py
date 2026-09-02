#!/usr/bin/env python3
import argparse
import copy
import hashlib
import json
import math
import os
import re
from collections import defaultdict
from datetime import datetime, time, timedelta
from pathlib import Path

from search_disease_medications import is_allowed_url, search_candidates


REQUIRED_MEDICATION_FIELDS = [
    "drugName", "specification", "singleDose", "route", "frequency",
    "medicationTime", "treatmentDays", "precautions",
]
ROUTE_WORDS = re.compile(r"口服|肌肉注射|肌内注射|静脉滴注|静脉注射|皮下注射")
MIN_COMBINED_MEDICATION_COUNT = 3
MIN_DISEASE_MEDICATION_COUNT = 2


def minimum_unique_medication_plan_count(patient_count):
    if patient_count <= 0:
        return 0
    return min(patient_count, max(10, math.ceil(math.sqrt(patient_count))))


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
    medication.pop("diseaseRationale", None)
    medication.pop("evidence", None)
    for field in REQUIRED_MEDICATION_FIELDS:
        if field not in medication or medication[field] in (None, ""):
            raise ValueError(f'{patient["userid"]}药品{medication.get("drugName", "")}缺少{field}')
    if "displayName" in medication:
        if not isinstance(medication["displayName"], str) or not medication["displayName"].strip():
            raise ValueError(
                f'{patient["userid"]}药品{medication.get("drugName", "")}的displayName必须为非空字符串'
            )
        medication["displayName"] = medication["displayName"].strip()
    else:
        medication["displayName"] = str(medication["drugName"]).strip()
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
        for group in plan.get("medicationGroups", []):
            for medication in group.get("alternatives", []):
                drug_name = str(medication.get("drugName", "")).strip()
                if (
                    medication.get("role") != "diseaseTreatment"
                    or not str(medication.get("diseaseRationale", "")).strip()
                    or not medication.get("evidence")
                ):
                    raise ValueError(f"{plan_id}中的{drug_name}必须声明diseaseTreatment角色、疾病关联理由和药品依据")
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


def safe_group_alternatives(disease_plan, patient):
    selected_groups = []
    for group in disease_plan.get("medicationGroups", []):
        if not matches(patient, group.get("when", {})):
            continue
        alternatives = [
            item for item in group.get("alternatives", [])
            if safe_for_allergy(item, patient["allergyHistory"])
        ]
        if not alternatives:
            if group.get("required", False):
                raise ValueError(f'{patient["userid"]}条件组{group.get("id", "")}无安全替代药')
            continue
        selected_groups.append((group, alternatives))
    return selected_groups


def choose_medication_combination(selected_groups, combination_index):
    medications = []
    remaining_index = combination_index
    for _, alternatives in selected_groups:
        medications.append(alternatives[remaining_index % len(alternatives)])
        remaining_index //= len(alternatives)
    return medications


def _valid_search_candidate(candidate):
    if not isinstance(candidate, dict):
        return False
    if (
        candidate.get("role") != "diseaseTreatment"
        or not str(candidate.get("drugName", "")).strip()
        or not str(candidate.get("diseaseRationale", "")).strip()
        or not candidate.get("evidence")
    ):
        return False
    if not all(candidate.get(field) not in (None, "") for field in REQUIRED_MEDICATION_FIELDS):
        return False
    if not re.fullmatch(r"每日\d+次", str(candidate["frequency"])):
        return False
    if not isinstance(candidate["treatmentDays"], int) or candidate["treatmentDays"] <= 0:
        return False
    if ROUTE_WORDS.search(str(candidate["medicationTime"])):
        return False
    return all(
        isinstance(item, dict)
        and is_allowed_url(str(item.get("url", "")))
        and str(item.get("title", "")).strip()
        and str(item.get("scope", "")).strip()
        for item in candidate["evidence"]
    )


def maybe_search_and_extend_profile(profile, patients, search_fn=None, audit_path=None):
    search_enabled = os.environ.get("AUTO_MEDICATION_SEARCH", "1") != "0"
    updated_profile = copy.deepcopy(profile)
    audit = []
    if not search_enabled:
        audit.append({"status": "disabled"})
        return updated_profile, audit

    search_fn = search_fn or search_candidates
    searched_plans = set()
    for patient in patients:
        disease_plan = choose_disease_plan(updated_profile, patient)
        plan_id = str(disease_plan["id"])
        if plan_id in searched_plans:
            continue
        searched_plans.add(plan_id)
        selected_groups = safe_group_alternatives(disease_plan, patient)
        if len(selected_groups) >= MIN_DISEASE_MEDICATION_COUNT:
            audit.append({"planId": plan_id, "disease": patient["disease"], "status": "not_needed"})
            continue

        try:
            result = search_fn(updated_profile["productName"], patient["disease"])
        except Exception as exc:
            result = {"status": "error", "candidates": [], "sources": [], "errors": [f"检索器异常：{exc}"]}
        record = {
            "planId": plan_id,
            "disease": patient["disease"],
            "status": result.get("status", "error") if isinstance(result, dict) else "error",
            "candidateCount": 0,
            "incompleteCandidateCount": len(result.get("incompleteCandidates", [])) if isinstance(result, dict) else 0,
            "sources": result.get("sources", []) if isinstance(result, dict) else [],
            "errors": result.get("errors", []) if isinstance(result, dict) else ["检索器返回结果无效"],
        }
        if isinstance(result, dict):
            valid_candidates = [candidate for candidate in result.get("candidates", []) if _valid_search_candidate(candidate)]
            record["candidateCount"] = len(valid_candidates)
            if valid_candidates:
                existing_names = {
                    str(item.get("drugName", ""))
                    for group in disease_plan.get("medicationGroups", [])
                    for item in group.get("alternatives", [])
                }
                for index, candidate in enumerate(valid_candidates, start=1):
                    if candidate["drugName"] in existing_names:
                        continue
                    disease_plan["medicationGroups"].append({
                        "id": f"auto-search-{plan_id}-{index}",
                        "when": {},
                        "required": True,
                        "alternatives": [candidate],
                    })
                    existing_names.add(candidate["drugName"])
                record["status"] = "success" if record["candidateCount"] else "incomplete"
            elif record["status"] == "success":
                record["status"] = "incomplete"
        audit.append(record)

    if audit_path:
        target = Path(audit_path).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"searchEnabled": search_enabled, "searchAudit": audit}, ensure_ascii=False, indent=2), encoding="utf-8")
    return updated_profile, audit


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--patients", required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    extracted = load_json(args.patients)
    profile = load_json(args.profile)
    patients = extracted["patients"]

    audit_path = Path(args.output).expanduser().resolve().with_name("search-audit.json")

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

    profile, search_audit = maybe_search_and_extend_profile(profile, patients, audit_path=audit_path)
    validate_profile(profile)

    records, medication_items, reviewed_patients = [], [], []
    disease_medication_names_by_userid = {}
    combination_counters = defaultdict(int)
    for patient in patients:
        raw_medications = []
        if profile.get("baseMedication"):
            raw_medications.append(profile["baseMedication"])
        raw_medications.extend(profile.get("directProductAdjuncts", []))

        disease_plan = choose_disease_plan(profile, patient)
        selected_groups = safe_group_alternatives(disease_plan, patient)
        combination_key = (
            disease_plan["id"],
            tuple(
                (str(group.get("id", "")), tuple(item["drugName"] for item in alternatives))
                for group, alternatives in selected_groups
            ),
        )
        combination_index = combination_counters[combination_key]
        combination_counters[combination_key] += 1
        disease_medications = choose_medication_combination(selected_groups, combination_index)
        if profile["productType"] == "用药" and len(disease_medications) < MIN_DISEASE_MEDICATION_COUNT:
            raise ValueError(
                f'{patient["userid"]}（疾病：{patient["disease"]}）匹配疾病方案{disease_plan["id"]}后'
                f'仅生成疾病治疗药{len(disease_medications)}种，至少需要{MIN_DISEASE_MEDICATION_COUNT}种；'
                "直接产品辅助品不计入数量，请补充有疾病依据且通过过敏/禁忌筛选的候选药"
            )
        if profile["productType"] != "用药" and not disease_medications and not disease_plan["allowProductOnly"]:
            raise ValueError(f'{patient["userid"]}的疾病方案{disease_plan["id"]}未生成联合药且未允许产品单药')
        disease_medication_names_by_userid[patient["userid"]] = [item["drugName"] for item in disease_medications]
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
                    "drugName", "displayName", "specification", "singleDose", "frequency",
                    "medicationTime", "treatmentDays", "precautions",
                ]},
            })
        if patient.get("sourceConfirmationTime"):
            try:
                confirmed_at = datetime.fromisoformat(patient["sourceConfirmationTime"])
            except ValueError as exc:
                raise ValueError(f'{patient["userid"]}用药方案确认时间无效：{patient["sourceConfirmationTime"]}') from exc
        else:
            if not patient.get("activateTime"):
                raise ValueError(f'{patient["userid"]}缺少激活日期或用药方案确认时间')
            activated_at = datetime.fromisoformat(patient["activateTime"])
            confirmed_at = confirmation_time(patient["userid"], activated_at)
        days = sorted(set(item["treatmentDays"] for item in medications))
        cycle = "、".join(f"{value}天" for value in days)
        reviewed_patients.append({
            **patient,
            "confirmationTime": confirmed_at.strftime("%Y-%m-%d %H:%M:%S"),
            "medicationPlan": "、".join(
                f'{item["displayName"]}{str(item["singleDose"]).strip()}'
                for item in medications
            ),
            "medicationCycle": cycle,
        })

    unique_medication_plan_count = len({patient["medicationPlan"] for patient in reviewed_patients})
    minimum_unique_plan_count = minimum_unique_medication_plan_count(len(patients))
    unique_plan_target_met = unique_medication_plan_count >= minimum_unique_plan_count

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
            "inputFormat": extracted.get("inputFormat", "monthlyPatient18"),
            "searchEnabled": os.environ.get("AUTO_MEDICATION_SEARCH", "1") != "0",
            "searchAudit": search_audit,
            "monthLabel": max(
                (
                    extracted["summary"].get("activationMonths")
                    or extracted["summary"].get("confirmationMonths")
                    or {"": 0}
                ),
                key=(
                    extracted["summary"].get("activationMonths")
                    or extracted["summary"].get("confirmationMonths")
                    or {"": 0}
                ).get,
            ),
            "evidence": profile["evidence"],
            "minimumCombinedMedicationCount": MIN_COMBINED_MEDICATION_COUNT,
            "minimumDiseaseMedicationCount": MIN_DISEASE_MEDICATION_COUNT,
            "minimumUniqueMedicationPlanCount": minimum_unique_plan_count,
            "uniqueMedicationPlanCount": unique_medication_plan_count,
            "uniqueMedicationPlanPriority": "recommended",
            "uniqueMedicationPlanTargetMet": unique_plan_target_met,
            "uniqueMedicationPlanShortfall": max(minimum_unique_plan_count - unique_medication_plan_count, 0),
            "diseaseMedicationNamesByUserid": disease_medication_names_by_userid,
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
