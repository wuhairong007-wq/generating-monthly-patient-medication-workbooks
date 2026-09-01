import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "generate_payload.py"


def medication(name, *, avoid=None, precautions=None):
    item = {
        "drugName": name,
        "specification": "10mg/片",
        "singleDose": "10mg",
        "route": "口服",
        "frequency": "每日1次",
        "medicationTime": "早餐后",
        "treatmentDays": 30,
        "precautions": precautions or f"{name}仅在医师确认对应疾病指征后启用",
        "role": "diseaseTreatment",
        "diseaseRationale": f"{name}用于当前疾病方案对应疾病的治疗或风险管理",
        "evidence": [{"title": f"{name}疾病用药依据", "url": "https://example.test/drug", "scope": "当前疾病方案用药"}],
    }
    if avoid:
        item["avoidIfAllergyContains"] = avoid
    return item


def patient(userid, disease, *, allergy="无", gender="男", age=60):
    return {
        "sequence": 1,
        "userid": userid,
        "patientName": f"患者{userid}",
        "activateTime": "2026-04-10 10:00:00",
        "gender": gender,
        "age": age,
        "disease": disease,
        "allergyHistory": allergy,
        "adverseEvent": "否",
        "adverseEventGrade": "",
        "patientTags": "",
    }


def extracted(patients):
    return {
        "source": "/tmp/patients.xlsx",
        "title": "2026-04-患者清单",
        "headers": [],
        "patients": patients,
        "summary": {
            "patientCount": len(patients),
            "distinctUseridCount": len({item["userid"] for item in patients}),
            "diseaseCounts": {},
            "genderCounts": {},
            "allergyCounts": {},
            "adverseEventCounts": {},
            "ageMin": min(item["age"] for item in patients),
            "ageMax": max(item["age"] for item in patients),
            "activationMonths": {"2026-04": len(patients)},
        },
    }


def disease_plan(plan_id, diseases, groups, *, allow_product_only=False, contains=False):
    condition = "diseaseContainsAny" if contains else "diseaseEqualsAny"
    return {
        "id": plan_id,
        "when": {condition: diseases},
        "evidence": [{"title": f"{plan_id}指南", "url": "https://example.test/guideline", "scope": "疾病用药"}],
        "allowProductOnly": allow_product_only,
        "medicationGroups": groups,
    }


def group(group_id, alternatives, *, when=None, required=False):
    return {
        "id": group_id,
        "when": when or {},
        "required": required,
        "alternatives": alternatives,
    }


def profile(plans, **overrides):
    value = {
        "schemaVersion": 2,
        "productType": "用药",
        "productName": "测试产品",
        "evidence": [{"title": "产品说明书", "url": "https://example.test/label", "scope": "产品用法"}],
        "baseMedication": medication("测试产品"),
        "directProductAdjuncts": [],
        "diseasePlans": plans,
        "surgeryRules": [],
        "globalNotes": ["候选方案需经医师或药师审核"],
    }
    value.update(overrides)
    return value


class DiseaseSpecificPlansTest(unittest.TestCase):
    def run_generator(self, patients, product_profile):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            patients_path = temp / "patients.json"
            profile_path = temp / "profile.json"
            output_path = temp / "payload.json"
            patients_path.write_text(json.dumps(extracted(patients), ensure_ascii=False), encoding="utf-8")
            profile_path.write_text(json.dumps(product_profile, ensure_ascii=False), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--patients", str(patients_path),
                    "--profile", str(profile_path),
                    "--output", str(output_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            payload = json.loads(output_path.read_text(encoding="utf-8")) if output_path.exists() else None
            return result, payload

    def test_requires_schema_version_two(self):
        product_profile = profile([
            disease_plan("脑梗死方案", ["脑梗死"], [], allow_product_only=True),
        ])
        product_profile["schemaVersion"] = 1

        result, _ = self.run_generator([patient("u1", "脑梗死")], product_profile)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("schemaVersion必须为2", result.stderr)

    def test_rejects_global_disease_medication_fields(self):
        product_profile = profile([
            disease_plan("脑梗死方案", ["脑梗死"], [], allow_product_only=True),
        ], baseCompanions=[medication("全局疾病治疗药")])

        result, _ = self.run_generator([patient("u1", "脑梗死")], product_profile)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("不得使用baseCompanions或顶层conditionalGroups", result.stderr)

    def test_disease_plan_requires_disease_predicate(self):
        invalid_plan = disease_plan("年龄方案", ["脑梗死"], [], allow_product_only=True)
        invalid_plan["when"] = {"ageMin": 60}

        result, _ = self.run_generator([patient("u1", "脑梗死")], profile([invalid_plan]))

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("diseasePlan.when必须包含疾病条件", result.stderr)

    def test_disease_plan_requires_independent_evidence(self):
        invalid_plan = disease_plan("脑梗死方案", ["脑梗死"], [], allow_product_only=True)
        invalid_plan["evidence"] = []

        result, _ = self.run_generator([patient("u1", "脑梗死")], profile([invalid_plan]))

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("疾病方案缺少权威依据", result.stderr)

    def test_patient_must_match_one_disease_plan(self):
        plans = [disease_plan("脑梗死方案", ["脑梗死"], [], allow_product_only=True)]

        result, _ = self.run_generator([patient("u1", "冠心病心绞痛")], profile(plans))

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("没有匹配的diseasePlan", result.stderr)

    def test_patient_must_not_match_multiple_disease_plans(self):
        plans = [
            disease_plan("冠心病方案", ["冠心病"], [], allow_product_only=True, contains=True),
            disease_plan("心绞痛方案", ["心绞痛"], [], allow_product_only=True, contains=True),
        ]

        result, _ = self.run_generator([patient("u1", "冠心病心绞痛")], profile(plans))

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("同时匹配多个diseasePlan", result.stderr)

    def test_plan_without_selected_companion_requires_explicit_product_only(self):
        plans = [disease_plan("脑梗死方案", ["脑梗死"], [], allow_product_only=False)]

        result, _ = self.run_generator([patient("u1", "脑梗死")], profile(plans))

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("疾病治疗药0种，至少需要2种", result.stderr)

    def test_direct_product_adjunct_requires_role_and_rationale(self):
        adjunct = medication("复溶液")
        plans = [disease_plan("脑梗死方案", ["脑梗死"], [], allow_product_only=True)]

        result, _ = self.run_generator(
            [patient("u1", "脑梗死")],
            profile(plans, directProductAdjuncts=[adjunct]),
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("直接产品辅助品必须声明role和rationale", result.stderr)

    def test_disease_medication_requires_role_rationale_and_evidence(self):
        unlinked = medication("无关联元数据药")
        unlinked.pop("role")
        unlinked.pop("diseaseRationale")
        unlinked.pop("evidence")
        plans = [disease_plan("脑梗死方案", ["脑梗死"], [
            group("疾病用药A", [unlinked]),
            group("疾病用药B", [medication("疾病药B")]),
        ])]

        result, _ = self.run_generator([patient("u1", "脑梗死")], profile(plans))

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("无关联元数据药必须声明diseaseTreatment角色、疾病关联理由和药品依据", result.stderr)

    def test_direct_product_adjunct_cannot_be_used_as_disease_medication(self):
        disguised_adjunct = medication("复溶液")
        disguised_adjunct["role"] = "directProductAdjunct"
        plans = [disease_plan("脑梗死方案", ["脑梗死"], [
            group("伪装疾病药", [disguised_adjunct]),
            group("疾病用药B", [medication("疾病药B")]),
        ])]

        result, _ = self.run_generator([patient("u1", "脑梗死")], profile(plans))

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("复溶液必须声明diseaseTreatment角色", result.stderr)

    def test_each_disease_uses_its_own_plan(self):
        plans = [
            disease_plan("脑梗死方案", ["脑梗死"], [
                group("卒中用药A", [medication("脑梗死候选药A")]),
                group("卒中用药B", [medication("脑梗死候选药B")]),
            ]),
            disease_plan("冠心病心绞痛方案", ["冠心病心绞痛"], [
                group("冠心病用药A", [medication("冠心病候选药A")]),
                group("冠心病用药B", [medication("冠心病候选药B")]),
            ]),
        ]

        result, payload = self.run_generator(
            [patient("u1", "脑梗死"), patient("u2", "冠心病心绞痛")],
            profile(plans),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([record["userid"] for record in payload["records"]], ["u1", "u2"])
        self.assertEqual(payload["records"][0]["combinedMedication"], ["测试产品", "脑梗死候选药A", "脑梗死候选药B"])
        self.assertEqual(payload["records"][1]["combinedMedication"], ["测试产品", "冠心病候选药A", "冠心病候选药B"])

    def test_same_combination_is_allowed_when_configured_per_disease(self):
        shared_a = medication("两病均可候选药A")
        shared_b = medication("两病均可候选药B")
        plans = [
            disease_plan("脑梗死方案", ["脑梗死"], [
                group("脑梗死依据组A", [shared_a]),
                group("脑梗死依据组B", [shared_b]),
            ]),
            disease_plan("冠心病方案", ["冠心病心绞痛"], [
                group("冠心病依据组A", [shared_a]),
                group("冠心病依据组B", [shared_b]),
            ]),
        ]

        result, payload = self.run_generator(
            [patient("u1", "脑梗死"), patient("u2", "冠心病心绞痛")],
            profile(plans),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(payload["records"][0]["combinedMedication"], ["测试产品", "两病均可候选药A", "两病均可候选药B"])
        self.assertEqual(payload["records"][1]["combinedMedication"], ["测试产品", "两病均可候选药A", "两病均可候选药B"])

    def test_product_only_plan_fails_minimum_disease_medication_rule(self):
        plans = [disease_plan("脑梗死单药方案", ["脑梗死"], [], allow_product_only=True)]

        result, payload = self.run_generator([patient("u1", "脑梗死")], profile(plans))

        self.assertNotEqual(result.returncode, 0)
        self.assertIsNone(payload)
        self.assertIn("u1", result.stderr)
        self.assertIn("脑梗死", result.stderr)
        self.assertIn("疾病治疗药0种，至少需要2种", result.stderr)

    def test_direct_product_adjunct_does_not_count_as_disease_medication(self):
        adjunct = {**medication("复溶液"), "role": "directProductAdjunct", "rationale": "说明书要求"}
        plans = [disease_plan("脑梗死方案", ["脑梗死"], [
            group("疾病用药", [medication("疾病药A")]),
        ])]

        result, _ = self.run_generator(
            [patient("u1", "脑梗死")],
            profile(plans, directProductAdjuncts=[adjunct]),
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("疾病治疗药1种，至少需要2种", result.stderr)

    def test_two_disease_medications_succeed_and_product_is_first(self):
        plans = [disease_plan("脑梗死方案", ["脑梗死"], [
            group("疾病机制A", [medication("疾病药A")]),
            group("疾病机制B", [medication("疾病药B")]),
        ])]

        result, payload = self.run_generator([patient("u1", "脑梗死")], profile(plans))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(payload["records"][0]["combinedMedication"], ["测试产品", "疾病药A", "疾病药B"])
        self.assertEqual(payload["meta"]["diseaseMedicationNamesByUserid"], {"u1": ["疾病药A", "疾病药B"]})

    def test_allergy_uses_safe_alternative_within_matched_disease_plan(self):
        antiplatelets = group("抗血小板候选", [
            medication("阿司匹林肠溶片", avoid=["阿司匹林"]),
            medication("硫酸氢氯吡格雷片", avoid=["氯吡格雷"]),
        ])
        second_group = group("脑保护候选", [medication("脑保护药")])
        plans = [disease_plan("脑梗死方案", ["脑梗死"], [antiplatelets, second_group])]

        result, payload = self.run_generator(
            [patient("u1", "脑梗死", allergy="阿司匹林过敏")],
            profile(plans),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(payload["records"][0]["combinedMedication"], ["测试产品", "硫酸氢氯吡格雷片", "脑保护药"])

    def test_allergy_without_safe_alternative_fails_minimum_rule(self):
        plans = [disease_plan("脑梗死方案", ["脑梗死"], [
            group("疾病用药A", [medication("药A", avoid=["青霉素"])]),
            group("疾病用药B", [medication("药B", avoid=["青霉素"])]),
        ])]

        result, _ = self.run_generator(
            [patient("u1", "脑梗死", allergy="青霉素过敏")],
            profile(plans),
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("疾病治疗药0种，至少需要2种", result.stderr)


if __name__ == "__main__":
    unittest.main()
