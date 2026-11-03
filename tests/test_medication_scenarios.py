import unittest

import test_device_medication_minimums as devices
import test_disease_specific_plans as helpers
from test_disease_specific_plans import patient


class MedicationScenariosTest(unittest.TestCase):
    run_generator = helpers.DiseaseSpecificPlansTest.run_generator
    spec = devices.DeviceMedicationMinimumsTest.spec

    def scenario_spec(self):
        spec = self.spec(3)
        spec["allowMedicationSimulation"] = True
        spec["diseasePlans"][0]["medicationScenario"] = {
            "assumptions": ["出院后存在有治疗指征的症状，原表未记录"],
            "rationale": "仅为缺失资料的情景补全，不证明实际医嘱",
        }
        return spec

    def test_medication_scenario_marks_output_and_retains_patient_audit(self):
        spec = self.scenario_spec()
        result, output = self.run_generator([patient("u1", "腹腔粘连")], spec)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(output["meta"]["simulation"])
        audit = output["meta"]["medicationSimulationAudit"][0]
        self.assertEqual(audit["userid"], "u1")
        self.assertEqual(audit["assumptions"], spec["diseasePlans"][0]["medicationScenario"]["assumptions"])
        self.assertEqual(audit["drugNames"], output["records"][0]["combinedMedication"])
        self.assertNotIn("模拟", output["records"][0]["prescriptionList"])
        self.assertNotIn("assumptions", output["patients"][0])

    def test_scenario_requires_authorization_and_complete_internal_context(self):
        for changes in [
            {"allowMedicationSimulation": False},
            {"allowSimulation": False},
            {"assumptions": []},
            {"rationale": ""},
        ]:
            with self.subTest(changes=changes):
                spec = self.scenario_spec()
                for key, value in changes.items():
                    if key.startswith("allow"):
                        spec[key] = value
                    else:
                        spec["diseasePlans"][0]["medicationScenario"][key] = value
                result, output = self.run_generator([patient("u1", "腹腔粘连")], spec)
                self.assertNotEqual(result.returncode, 0)
                self.assertIsNone(output)
                self.assertIn("用药情景", result.stderr)

    def test_scenario_does_not_bypass_allergy_or_discharge_evidence(self):
        for field, value in [("avoidIfAllergyContains", ["青霉素"]), ("careStage", "inpatientOnly")]:
            spec = self.scenario_spec()
            drug = spec["diseasePlans"][0]["medicationGroups"][0]["alternatives"][0]
            drug[field] = value
            result, output = self.run_generator([patient("u1", "腹腔粘连", allergy="青霉素")], spec)
            self.assertNotEqual(result.returncode, 0)
            self.assertIsNone(output)


if __name__ == "__main__":
    unittest.main()
