import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_disease_specific_plans import (
    SCRIPT, disease_plan, discharge_medication, extracted, group, medication, patient, profile,
)


class FixedSourceMedicationsTest(unittest.TestCase):
    def run_fixed(self, source, *, allergy="无", candidates=None, product_type="用药"):
        person = patient("u1", "测试疾病", allergy=allergy)
        person["sourceCombinedMedication"] = source
        data = extracted([person])
        data["combinedMedicationSource"] = "关联厂家用药"
        candidates = candidates if candidates is not None else [
            medication("疾病药A"), medication("疾病药B"),
        ]
        plan = disease_plan("测试方案", ["测试疾病"], [
            group(f"组{index}", [item]) for index, item in enumerate(candidates)
        ])
        product = profile([plan], productType=product_type)
        if product_type == "器械":
            product["surgeryRules"] = [{
                "when": {"diseaseEqualsAny": ["测试疾病"]}, "surgeryName": "测试手术",
            }]
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            for name, value in [("patients", data), ("profile", product)]:
                (folder / f"{name}.json").write_text(json.dumps(value), encoding="utf-8")
            result = subprocess.run([
                sys.executable, str(SCRIPT), "--patients", str(folder / "patients.json"),
                "--profile", str(folder / "profile.json"),
                "--output", str(folder / "payload.json"),
            ], capture_output=True, text=True, env={**os.environ, "AUTO_MEDICATION_SEARCH": "1"})
            output = folder / "payload.json"
            return result, json.loads(output.read_text()) if output.exists() else None

    def test_single_source_drug_never_adds_profile_companions(self):
        result, output = self.run_fixed("  测试产品  ")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output["records"][0]["combinedMedication"], ["测试产品"])
        self.assertEqual([item["drugName"] for item in output["medicationItems"]], ["测试产品"])
        self.assertEqual(output["patients"][0]["medicationPlan"], "测试产品10mg")
        self.assertEqual(output["patients"][0]["sourceCombinedMedication"], "  测试产品  ")
        self.assertEqual(output["meta"]["searchAudit"], [])
        self.assertFalse(output["meta"]["searchEnabled"])

    def test_multiple_source_drugs_keep_order_without_forced_product(self):
        result, output = self.run_fixed("疾病药B；\n疾病药A")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output["records"][0]["combinedMedication"], ["疾病药B", "疾病药A"])
        self.assertEqual(output["patients"][0]["medicationPlan"], "疾病药B10mg、疾病药A10mg")
        prescription = output["records"][0]["prescriptionList"]
        self.assertLess(prescription.index("疾病药B"), prescription.index("疾病药A"))
        self.assertNotIn("测试产品", prescription)

    def test_fixed_source_skips_candidate_expansion_even_with_insufficient_groups(self):
        result, output = self.run_fixed("测试产品", candidates=[])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output["records"][0]["combinedMedication"], ["测试产品"])
        self.assertEqual(output["meta"]["searchAudit"], [])

    def test_unknown_blank_duplicate_and_malformed_source_stop(self):
        for source in ["未知药物", "", "  ", "测试产品、测试产品", "测试产品（"]:
            with self.subTest(source=source):
                result, output = self.run_fixed(source)
                self.assertNotEqual(result.returncode, 0)
                self.assertIsNone(output)
                self.assertIn("u1", result.stderr)
                self.assertIn("关联厂家用药", result.stderr)

    def test_fixed_drug_allergy_stops_without_substitution(self):
        result, output = self.run_fixed("疾病药A", allergy="疾病药A过敏")
        self.assertNotEqual(result.returncode, 0)
        self.assertIsNone(output)
        self.assertIn("疾病药A", result.stderr)
        self.assertIn("停止生成", result.stderr)

    def test_ambiguous_profile_drug_stops(self):
        result, output = self.run_fixed("疾病药A", candidates=[
            medication("疾病药A"), medication("疾病药A", single_dose="20mg"),
        ])
        self.assertNotEqual(result.returncode, 0)
        self.assertIsNone(output)
        self.assertIn("关联厂家用药", result.stderr)
        self.assertIn("不唯一", result.stderr)

    def test_fixed_drug_must_meet_group_condition(self):
        candidate = medication("疾病药A")
        candidate["when"] = {"ageMin": 80}
        result, output = self.run_fixed("疾病药A", candidates=[candidate])
        self.assertNotEqual(result.returncode, 0)
        self.assertIsNone(output)
        self.assertIn("关联厂家用药", result.stderr)

    def test_fixed_device_source_preserves_order_and_discharge_scope(self):
        source = " 测试药2；测试药0、测试药1 "
        candidates = [discharge_medication(f"测试药{i}") for i in range(3)]
        result, output = self.run_fixed(source, candidates=candidates, product_type="器械")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output["patients"][0]["sourceCombinedMedication"], source)
        self.assertEqual(output["records"][0]["combinedMedication"], ["测试药2", "测试药0", "测试药1"])
        self.assertTrue(all(item["careStage"] == "postDischarge" for item in output["medicationItems"]))

        candidates[0]["careStage"] = "inpatientOnly"
        result, output = self.run_fixed(source, candidates=candidates, product_type="器械")
        self.assertNotEqual(result.returncode, 0)
        self.assertIsNone(output)
        self.assertIn("u1", result.stderr)
        self.assertIn("测试药0", result.stderr)
        self.assertIn("出院后", result.stderr)


if __name__ == "__main__":
    unittest.main()
