import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "generate_adverse_reactions.py"
BUILDER = SKILL_DIR / "scripts" / "build_adverse_reaction_workbook.mjs"
VERIFIER = SKILL_DIR / "scripts" / "verify_adverse_reaction_workbook.mjs"
TEMPLATE = SKILL_DIR / "assets" / "adverse-reaction-template.xlsx"
NODE = os.environ.get("CODEX_NODE") or shutil.which("node")
NODE_MODULES = os.environ.get("CODEX_NODE_MODULES")


def patient(
    userid,
    tag,
    *,
    disease="脑梗死",
    activated="2026-04-10 10:00:00",
    gender="男",
    age=60,
    allergy="无",
):
    return {
        "sequence": 1,
        "userid": userid,
        "patientName": f"患者{userid}",
        "activateTime": activated,
        "gender": gender,
        "age": age,
        "disease": disease,
        "allergyHistory": allergy,
        "adverseEvent": "否",
        "adverseEventGrade": "",
        "patientTags": tag,
    }


def extracted(patients):
    return {
        "source": "/tmp/月度患者清单.xlsx",
        "title": "2026-04-月度患者清单",
        "headers": [],
        "patients": patients,
        "summary": {
            "patientCount": len(patients),
            "distinctUseridCount": len({item["userid"] for item in patients}),
            "activationMonths": {"2026-04": len(patients)},
        },
    }


class AdverseReactionGeneratorTest(unittest.TestCase):
    def run_generator(self, patients, product="血栓通胶囊", include_product=True):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            patients_path = temp / "patients.json"
            output_path = temp / "adverse-reactions.json"
            patients_path.write_text(json.dumps(extracted(patients), ensure_ascii=False), encoding="utf-8")
            command = [
                sys.executable,
                str(SCRIPT),
                "--patients",
                str(patients_path),
                "--output",
                str(output_path),
            ]
            if include_product:
                command.extend(["--product", product])
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
            )
            payload = json.loads(output_path.read_text(encoding="utf-8")) if output_path.exists() else None
            return result, payload

    def test_filters_target_tags_and_preserves_userid_order(self):
        result, payload = self.run_generator(
            [
                patient("u0", "无"),
                patient("u1", "中度患者"),
                patient("u2", "重度患者"),
                patient("u3", "轻度患者"),
            ]
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([item["userid"] for item in payload["records"]], ["u1", "u2"])
        self.assertEqual([item["userid"] for item in payload["sourcePatients"]], ["u1", "u2"])
        self.assertEqual(payload["meta"]["sourcePatientCount"], 4)
        self.assertEqual(payload["meta"]["targetPatientCount"], 2)
        self.assertEqual(payload["meta"]["productName"], "血栓通胶囊")

    def test_requires_nonempty_product_name(self):
        missing_result, missing_payload = self.run_generator(
            [patient("u1", "中度患者")], include_product=False
        )
        blank_result, blank_payload = self.run_generator(
            [patient("u1", "中度患者")], product="   "
        )

        self.assertNotEqual(missing_result.returncode, 0)
        self.assertIsNone(missing_payload)
        self.assertIn("--product", missing_result.stderr)
        self.assertNotEqual(blank_result.returncode, 0)
        self.assertIsNone(blank_payload)
        self.assertIn("产品名称不能为空", blank_result.stderr)

    def test_maps_grade_and_manual_intervention_from_patient_tag(self):
        result, payload = self.run_generator(
            [patient("u1", "中度患者"), patient("u2", "重度患者")]
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(payload["records"][0]["severityGrade"], "中度（2级）")
        self.assertEqual(payload["records"][0]["manualIntervention"], "否")
        self.assertEqual(payload["records"][1]["severityGrade"], "重度（3级）")
        self.assertEqual(payload["records"][1]["manualIntervention"], "是")

    def test_time_precedes_activation_and_generation_is_deterministic(self):
        patients = [patient("stable-user", "中度患者", activated="2026-04-01 01:00:00")]

        first_result, first = self.run_generator(patients)
        second_result, second = self.run_generator(patients)

        self.assertEqual(first_result.returncode, 0, first_result.stderr)
        self.assertEqual(second_result.returncode, 0, second_result.stderr)
        self.assertEqual(first["records"], second["records"])
        occurrence = datetime.fromisoformat(first["records"][0]["occurrenceTime"])
        activation = datetime.fromisoformat(patients[0]["activateTime"])
        self.assertLess(occurrence, activation)

    def test_uses_only_allowed_discovery_methods_and_blank_followup(self):
        result, payload = self.run_generator(
            [patient("u1", "中度患者"), patient("u2", "重度患者")]
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(
            all(
                item["discoveryMethod"] in {"AI用药随访发现", "患者自评反馈"}
                for item in payload["records"]
            )
        )
        self.assertTrue(all(item["followupRecord"] == "" for item in payload["records"]))

    def test_records_include_nonempty_required_structured_fields(self):
        result, payload = self.run_generator([patient("u1", "中度患者")])

        self.assertEqual(result.returncode, 0, result.stderr)
        required = {
            "userid",
            "symptomDescription",
            "severityGrade",
            "treatmentMeasures",
            "treatmentOutcome",
            "remark",
        }
        record = payload["records"][0]
        self.assertTrue(required.issubset(record))
        self.assertTrue(all(record[field] for field in required))

    def test_symptom_description_includes_disease_and_exact_age(self):
        patients = [
            patient("brain-58", "中度患者", disease="脑梗死", age=58),
            patient("heart-76", "重度患者", disease="冠心病心绞痛", age=76),
        ]

        result, payload = self.run_generator(patients)

        self.assertEqual(result.returncode, 0, result.stderr)
        for source, record in zip(patients, payload["records"]):
            self.assertIn(source["disease"], record["symptomDescription"])
            self.assertIn(f"{source['age']}岁", record["symptomDescription"])

    def test_symptom_description_uses_age_band_context(self):
        patients = [
            patient("age-58", "中度患者", age=58),
            patient("age-68", "中度患者", age=68),
            patient("age-78", "中度患者", age=78),
        ]

        result, payload = self.run_generator(patients)

        self.assertEqual(result.returncode, 0, result.stderr)
        descriptions = [item["symptomDescription"] for item in payload["records"]]
        self.assertIn("中年阶段", descriptions[0])
        self.assertIn("老年阶段", descriptions[1])
        self.assertIn("高龄阶段", descriptions[2])

    def test_symptom_descriptions_are_varied_within_same_disease_and_age(self):
        patients = [
            patient(f"same-cohort-{index:02d}", "中度患者", disease="脑梗死", age=66)
            for index in range(24)
        ]

        result, payload = self.run_generator(patients)

        self.assertEqual(result.returncode, 0, result.stderr)
        descriptions = {item["symptomDescription"] for item in payload["records"]}
        self.assertGreaterEqual(len(descriptions), 12)

    def test_content_is_product_and_disease_sensitive_without_claiming_outcome(self):
        result, payload = self.run_generator(
            [
                patient("u1", "中度患者", disease="脑梗死"),
                patient("u2", "中度患者", disease="冠心病心绞痛"),
            ]
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        first, second = payload["records"]
        self.assertNotEqual(first["symptomDescription"], second["symptomDescription"])
        self.assertNotEqual(first["treatmentMeasures"], second["treatmentMeasures"])
        self.assertNotEqual(first["treatmentOutcome"], second["treatmentOutcome"])
        for record in payload["records"]:
            self.assertIn("血栓通胶囊", record["symptomDescription"])
            self.assertIn("血栓通胶囊", record["medicationRelationship"])
            self.assertIn("人工核实", record["medicationRelationship"])
            self.assertNotIn("结构化草案：", record["symptomDescription"])
            self.assertNotIn("人工审核草案：", record["remark"])
            self.assertNotIn("草案", record["symptomDescription"])
            self.assertNotIn("草案", record["remark"])
            self.assertNotRegex(record["treatmentMeasures"], r"停药|减量|加用|继续原方案")
            self.assertRegex(record["treatmentOutcome"], r"待.*核实|未提供")
            self.assertNotRegex(record["treatmentOutcome"], r"痊愈|好转|恢复正常")
            self.assertLessEqual(len(record["treatmentOutcome"]), 160)

        for record in (first, second):
            symptom_tail = record["symptomDescription"].split("反馈可能出现", 1)[1]
            selected_symptoms = "，".join(symptom_tail.split("，")[:2])
            self.assertIn(selected_symptoms, record["treatmentMeasures"])
        self.assertIn("血栓通胶囊", first["treatmentOutcome"])
        self.assertIn("血栓通胶囊", second["treatmentOutcome"])

    def test_notes_include_product_age_sex_disease_allergy_without_draft_prefix(self):
        result, payload = self.run_generator(
            [
                patient(
                    "u1",
                    "重度患者",
                    disease="冠心病心绞痛",
                    gender="女",
                    age=72,
                    allergy="青霉素过敏",
                )
            ]
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        remark = payload["records"][0]["remark"]
        for expected in ["血栓通胶囊", "女", "72岁", "冠心病心绞痛", "青霉素过敏"]:
            self.assertIn(expected, remark)
        self.assertNotIn("草案", remark)

    def test_rejects_input_without_medium_or_severe_patients(self):
        result, payload = self.run_generator(
            [patient("u0", "无"), patient("u1", "轻度患者")]
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIsNone(payload)
        self.assertIn("患者标签中没有中度患者或重度患者", result.stderr)


@unittest.skipUnless(NODE and NODE_MODULES, "需要CODEX_NODE和CODEX_NODE_MODULES运行工作簿测试")
class AdverseReactionWorkbookTest(unittest.TestCase):
    def test_builds_and_independently_verifies_workbook(self):
        source_patients = [
            patient("u1", "中度患者", disease="脑梗死"),
            patient("u2", "重度患者", disease="冠心病心绞痛", gender="女", age=72),
        ]
        records = [
            {
                "userid": "u1",
                "disease": "脑梗死",
                "occurrenceTime": "2026-04-09 09:00:00",
                "discoveryMethod": "AI用药随访发现",
                "symptomDescription": "患者在使用血栓通胶囊期间反馈可能出现头晕或乏力，具体情况需人工核实。",
                "severityGrade": "中度（2级）",
                "medicationRelationship": "上述表现与血栓通胶囊存在时间关联的可能性，具体因果关系需人工核实。",
                "treatmentMeasures": "建议人工复核症状和当前用药，必要时联系医师，不自行调整用药。",
                "treatmentOutcome": "当前资料未提供处理后转归，需在后续随访中核实并记录。",
                "manualIntervention": "否",
                "followupRecord": "",
                "remark": "涉及血栓通胶囊的相关信息需复核，不构成诊断、处方调整或疗效结论。",
            },
            {
                "userid": "u2",
                "disease": "冠心病心绞痛",
                "occurrenceTime": "2026-04-09 08:00:00",
                "discoveryMethod": "患者自评反馈",
                "symptomDescription": "患者在使用血栓通胶囊期间反馈可能出现明显乏力或胃部不适，具体情况需人工核实。",
                "severityGrade": "重度（3级）",
                "medicationRelationship": "上述表现与血栓通胶囊存在时间关联的可能性，具体因果关系需人工核实。",
                "treatmentMeasures": "建议尽快人工干预并复核当前用药，出现紧急情况及时就医，不自行调整用药。",
                "treatmentOutcome": "当前资料未提供处理后转归，需在后续随访中核实并记录。",
                "manualIntervention": "是",
                "followupRecord": "",
                "remark": "涉及血栓通胶囊的相关信息需复核，不构成诊断、处方调整或疗效结论。",
            },
        ]
        payload = {
            "meta": {
                "source": "/tmp/月度患者清单.xlsx",
                "sourceTitle": "测试清单",
                "sourcePatientCount": 2,
                "targetPatientCount": 2,
                "targetTags": ["中度患者", "重度患者"],
                "productName": "血栓通胶囊",
            },
            "sourcePatients": source_patients,
            "records": records,
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            payload_path = temp / "payload.json"
            workbook_path = temp / "不良反应清单.xlsx"
            preview_dir = temp / "previews"
            report_path = temp / "verification.json"
            payload_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            env = {**os.environ, "CODEX_NODE_MODULES": NODE_MODULES}

            build = subprocess.run(
                [
                    NODE,
                    str(BUILDER),
                    "--payload",
                    str(payload_path),
                    "--template",
                    str(TEMPLATE),
                    "--output",
                    str(workbook_path),
                    "--preview-dir",
                    str(preview_dir),
                ],
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(build.returncode, 0, build.stderr)
            self.assertTrue(workbook_path.is_file())
            rendered = load_workbook(workbook_path, read_only=True, data_only=True)
            sheet = rendered.worksheets[0]
            self.assertEqual(sheet["A1"].value, "不良反应（AE）记录清单")
            self.assertNotIn("草案", sheet["F3"].value)
            self.assertNotIn("草案", sheet["M3"].value)
            self.assertEqual(
                {path.name for path in preview_dir.glob("*.png")},
                {"adverse-first.png", "adverse-middle.png", "adverse-last.png"},
            )

            verify = subprocess.run(
                [
                    NODE,
                    str(VERIFIER),
                    "--payload",
                    str(payload_path),
                    "--workbook",
                    str(workbook_path),
                    "--report",
                    str(report_path),
                ],
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(verify.returncode, 0, verify.stderr)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["rowCount"], 2)
            self.assertEqual(report["distinctUseridCount"], 2)
            self.assertTrue(report["exactUseridOrderMatch"])
            self.assertTrue(report["formulaErrors"].endswith("matched 0 entries"))


if __name__ == "__main__":
    unittest.main()
