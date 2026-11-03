import copy
import unittest

import test_device_medication_minimums as devices
import test_disease_specific_plans as helpers
from test_disease_specific_plans import discharge_medication, patient
from generate_payload import maybe_search_and_extend_profile


class DeviceDischargeMedicationsTest(unittest.TestCase):
    run_generator = helpers.DiseaseSpecificPlansTest.run_generator
    spec = devices.DeviceMedicationMinimumsTest.spec

    def test_device_requires_explicit_discharge_stage_and_rationale(self):
        for field, value in [
            ("careStage", None), ("careStage", "inpatientOnly"),
            ("dischargeRationale", ""), ("dischargeRationale", None),
            ("evidence", [{"title": "测试", "url": "", "scope": "测试"}]),
        ]:
            with self.subTest(field=field, value=value):
                spec = self.spec(3)
                spec["diseasePlans"][0]["medicationGroups"][0]["alternatives"][0][field] = value
                result, output = self.run_generator([patient("u1", "腹腔粘连")], spec)
                self.assertNotEqual(result.returncode, 0)
                self.assertIsNone(output)
                self.assertIn("出院后", result.stderr)
                self.assertIn("测试药0", result.stderr)
                self.assertIn("u1", result.stderr)

    def test_device_payload_retains_discharge_evidence_for_every_drug(self):
        result, output = self.run_generator([patient("u1", "腹腔粘连")], self.spec(3))
        self.assertEqual(result.returncode, 0, result.stderr)
        for item in output["medicationItems"]:
            self.assertEqual(item.get("careStage"), "postDischarge")
            self.assertTrue(item.get("dischargeRationale"))
            self.assertTrue(item.get("dischargeEvidence"))
        self.assertEqual(
            output["records"][0]["combinedMedication"],
            [item["drugName"] for item in output["medicationItems"]],
        )

    def test_device_checks_adjuncts_and_selected_regimen_variants(self):
        spec = self.spec(3)
        variant = {"singleDose": "20mg", "evidence": [{"title": "测试变体", "url": "https://example.test", "scope": "测试"}]}
        spec["diseasePlans"][0]["medicationGroups"][0]["alternatives"][0]["regimenVariants"] = [variant]
        result, output = self.run_generator([patient("variant-u1", "腹腔粘连")], spec)
        self.assertNotEqual(result.returncode, 0)
        self.assertIsNone(output)
        self.assertIn("出院后", result.stderr)

        spec = self.spec(3)
        spec["directProductAdjuncts"] = [{
            **discharge_medication("住院辅助品"),
            "role": "directProductAdjunct", "rationale": "测试辅助品",
            "careStage": "inpatientOnly",
        }]
        result, output = self.run_generator([patient("adjunct-u1", "腹腔粘连")], spec)
        self.assertNotEqual(result.returncode, 0)
        self.assertIsNone(output)
        self.assertIn("adjunct-u1", result.stderr)
        self.assertIn("出院后", result.stderr)

    def test_selected_variant_retains_its_own_discharge_evidence(self):
        spec = self.spec(3)
        variant = {
            "singleDose": "20mg",
            "careStage": "postDischarge",
            "dischargeRationale": "该变体出院后使用的测试依据",
            "evidence": [{"title": "变体专属依据", "url": "https://example.test/variant", "scope": "出院剂量"}],
        }
        spec["diseasePlans"][0]["medicationGroups"][0]["alternatives"][0]["regimenVariants"] = [variant]
        result, output = self.run_generator([patient("variant-u1", "腹腔粘连")], spec)
        self.assertEqual(result.returncode, 0, result.stderr)
        item = output["medicationItems"][0]
        self.assertEqual(item["singleDose"], "20mg")
        self.assertEqual(item["dischargeRationale"], variant["dischargeRationale"])
        self.assertEqual(item["dischargeEvidence"], variant["evidence"])

    def test_device_search_does_not_accept_unreviewed_inpatient_candidates(self):
        spec = self.spec(2)
        valid = discharge_medication("检索出院药")
        valid["evidence"] = [{"title": "测试依据", "url": "https://www.nhc.gov.cn/test", "scope": "测试出院方案"}]
        for stage, expected_count in [("inpatientOnly", 2), (None, 2), ("postDischarge", 3)]:
            with self.subTest(stage=stage):
                candidate = copy.deepcopy(valid)
                candidate["careStage"] = stage
                updated, audit = maybe_search_and_extend_profile(
                    spec, [patient("search-u1", "腹腔粘连")],
                    search_fn=lambda *_: {"status": "success", "candidates": [candidate]},
                )
                self.assertEqual(len(updated["diseasePlans"][0]["medicationGroups"]), expected_count)
                self.assertEqual(audit[0]["candidateCount"], expected_count - 2)


if __name__ == "__main__":
    unittest.main()
