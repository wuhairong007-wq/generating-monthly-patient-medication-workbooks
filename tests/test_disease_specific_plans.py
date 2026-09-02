import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "generate_payload.py"
UNSET = object()


def medication(
    name,
    *,
    avoid=None,
    precautions=None,
    display_name=UNSET,
    single_dose="10mg",
    age_dose_rules=None,
):
    item = {
        "drugName": name,
        "specification": "10mg/片",
        "singleDose": single_dose,
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
    if display_name is not UNSET:
        item["displayName"] = display_name
    if age_dose_rules is not None:
        item["ageDoseRules"] = age_dose_rules
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
    def run_generator(self, patients, product_profile, *, search_enabled=False):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            patients_path = temp / "patients.json"
            profile_path = temp / "profile.json"
            output_path = temp / "payload.json"
            patients_path.write_text(json.dumps(extracted(patients), ensure_ascii=False), encoding="utf-8")
            profile_path.write_text(json.dumps(product_profile, ensure_ascii=False), encoding="utf-8")
            environment = dict(os.environ)
            environment["AUTO_MEDICATION_SEARCH"] = "1" if search_enabled else "0"
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
                env=environment,
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

    def test_same_combination_across_diseases_counts_as_one_unique_plan(self):
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
        self.assertIsNotNone(payload)
        self.assertEqual(len({item["medicationPlan"] for item in payload["patients"]}), 1)
        self.assertEqual(payload["meta"]["uniqueMedicationPlanCount"], 1)
        self.assertEqual(payload["meta"]["minimumUniqueMedicationPlanCount"], 2)
        self.assertFalse(payload["meta"]["uniqueMedicationPlanTargetMet"])
        self.assertEqual(payload["meta"]["uniqueMedicationPlanShortfall"], 1)

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

    def test_reminder_input_reuses_source_confirmation_time(self):
        reminder_patient = patient("u1", "脑梗死")
        reminder_patient["activateTime"] = ""
        reminder_patient["sourceConfirmationTime"] = "2026-04-10 10:30:00"
        reminder_patient["confirmationTime"] = "2026-04-10 10:30:00"
        plans = [disease_plan("脑梗死方案", ["脑梗死"], [
            group("疾病机制A", [medication("疾病药A")]),
            group("疾病机制B", [medication("疾病药B")]),
        ])]

        result, payload = self.run_generator([reminder_patient], profile(plans))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(payload["patients"][0]["confirmationTime"], "2026-04-10 10:30:00")

    def test_medication_plan_lists_every_drug_as_display_name_and_single_dose(self):
        product_name = "双歧杆菌四联活菌片"
        medications = [
            medication("蒙脱石散", single_dose="3g"),
            medication("口服补液盐I", single_dose="5.125g"),
            medication("消旋卡多曲颗粒", single_dose="30mg"),
        ]
        plans = [disease_plan("腹泻方案", ["抗生素相关性腹泻"], [
            group(f"疾病用药{index}", [item])
            for index, item in enumerate(medications, start=1)
        ])]
        product_profile = profile(
            plans,
            productName=product_name,
            baseMedication=medication(
                product_name,
                display_name="双歧杆菌四联活菌片(思连康)",
                single_dose="1.0g",
            ),
        )

        result, payload = self.run_generator(
            [patient("u1", "抗生素相关性腹泻", gender="女", age=34)],
            product_profile,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            payload["patients"][0]["medicationPlan"],
            "双歧杆菌四联活菌片(思连康)1.0g、蒙脱石散3g、口服补液盐I5.125g、消旋卡多曲颗粒30mg",
        )
        self.assertEqual(
            payload["records"][0]["combinedMedication"],
            ["双歧杆菌四联活菌片", "蒙脱石散", "口服补液盐I", "消旋卡多曲颗粒"],
        )
        self.assertEqual(
            [item["displayName"] for item in payload["medicationItems"]],
            ["双歧杆菌四联活菌片(思连康)", "蒙脱石散", "口服补液盐I", "消旋卡多曲颗粒"],
        )

    def test_medication_plan_falls_back_to_drug_name(self):
        plans = [disease_plan("脑梗死方案", ["脑梗死"], [
            group("疾病机制A", [medication("疾病药A", single_dose="20mg")]),
            group("疾病机制B", [medication("疾病药B", single_dose="30mg")]),
        ])]

        result, payload = self.run_generator([patient("u1", "脑梗死")], profile(plans))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(payload["patients"][0]["medicationPlan"], "测试产品10mg、疾病药A20mg、疾病药B30mg")
        self.assertEqual(
            [item["displayName"] for item in payload["medicationItems"]],
            ["测试产品", "疾病药A", "疾病药B"],
        )

    def test_medication_plan_uses_age_adjusted_single_dose(self):
        adjusted = medication(
            "疾病药A",
            single_dose="20mg",
            age_dose_rules=[{"ageMin": 65, "singleDose": "10mg"}],
        )
        plans = [disease_plan("脑梗死方案", ["脑梗死"], [
            group("疾病机制A", [adjusted]),
            group("疾病机制B", [medication("疾病药B", single_dose="30mg")]),
        ])]

        result, payload = self.run_generator([patient("u1", "脑梗死", age=70)], profile(plans))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(payload["patients"][0]["medicationPlan"], "测试产品10mg、疾病药A10mg、疾病药B30mg")

    def test_medication_plan_displays_all_three_to_five_drugs(self):
        for total_count in (3, 4, 5):
            with self.subTest(total_count=total_count):
                disease_medications = [
                    medication(f"疾病药{index}", single_dose=f"{index}mg")
                    for index in range(1, total_count)
                ]
                plans = [disease_plan("脑梗死方案", ["脑梗死"], [
                    group(f"疾病机制{index}", [item])
                    for index, item in enumerate(disease_medications, start=1)
                ])]

                result, payload = self.run_generator([patient("u1", "脑梗死")], profile(plans))

                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(len(payload["records"][0]["combinedMedication"]), total_count)
                self.assertEqual(len(payload["patients"][0]["medicationPlan"].split("、")), total_count)

    def test_rejects_empty_or_non_string_display_name(self):
        for invalid_display_name in ("", "  ", 123):
            with self.subTest(display_name=invalid_display_name):
                plans = [disease_plan("脑梗死方案", ["脑梗死"], [
                    group("疾病机制A", [medication("疾病药A", display_name=invalid_display_name)]),
                    group("疾病机制B", [medication("疾病药B")]),
                ])]

                result, payload = self.run_generator([patient("u1", "脑梗死")], profile(plans))

                self.assertNotEqual(result.returncode, 0)
                self.assertIsNone(payload)
                self.assertIn("displayName必须为非空字符串", result.stderr)

    def test_unique_medication_plan_target_scales_with_patient_count(self):
        self.assertEqual(self.skill_module_target(1), 1)
        self.assertEqual(self.skill_module_target(9), 9)
        self.assertEqual(self.skill_module_target(10), 10)
        self.assertEqual(self.skill_module_target(100), 10)
        self.assertEqual(self.skill_module_target(101), 11)
        self.assertEqual(self.skill_module_target(251), 16)
        self.assertEqual(self.skill_module_target(400), 20)
        self.assertEqual(self.skill_module_target(2500), 50)
        self.assertLessEqual(self.skill_module_target(100), self.skill_module_target(251))
        self.assertLessEqual(self.skill_module_target(251), self.skill_module_target(400))

    @staticmethod
    def skill_module_target(patient_count):
        from importlib.util import module_from_spec, spec_from_file_location

        spec = spec_from_file_location("generate_payload", SCRIPT)
        module = module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.minimum_unique_medication_plan_count(patient_count)

    def test_generator_reaches_unique_plan_target_when_candidates_support_it(self):
        patients = [patient(f"u{index}", "脑梗死") for index in range(16)]
        alternatives_a = [medication(f"疾病药A{index}", single_dose=f"{index}mg") for index in range(1, 5)]
        alternatives_b = [medication(f"疾病药B{index}", single_dose=f"{index}mg") for index in range(1, 5)]
        plans = [disease_plan("脑梗死方案", ["脑梗死"], [
            group("疾病机制A", alternatives_a),
            group("疾病机制B", alternatives_b),
        ])]

        result, payload = self.run_generator(patients, profile(plans))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertGreaterEqual(len({item["medicationPlan"] for item in payload["patients"]}), 10)
        self.assertEqual(payload["meta"]["minimumUniqueMedicationPlanCount"], 10)

    def test_generator_allows_fewer_candidate_combinations_than_unique_target(self):
        patients = [patient(f"u{index}", "脑梗死") for index in range(251)]
        alternatives_a = [medication(f"疾病药A{index}") for index in range(1, 3)]
        alternatives_b = [medication(f"疾病药B{index}") for index in range(1, 3)]
        plans = [disease_plan("脑梗死方案", ["脑梗死"], [
            group("疾病机制A", alternatives_a),
            group("疾病机制B", alternatives_b),
        ])]

        result, payload = self.run_generator(patients, profile(plans))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIsNotNone(payload)
        self.assertEqual(len({item["medicationPlan"] for item in payload["patients"]}), 4)
        self.assertEqual(payload["meta"]["minimumUniqueMedicationPlanCount"], 16)
        self.assertEqual(payload["meta"]["uniqueMedicationPlanPriority"], "recommended")
        self.assertFalse(payload["meta"]["uniqueMedicationPlanTargetMet"])
        self.assertEqual(payload["meta"]["uniqueMedicationPlanShortfall"], 12)

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
