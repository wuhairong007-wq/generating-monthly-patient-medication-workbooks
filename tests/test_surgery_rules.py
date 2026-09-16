import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from generate_payload import choose_surgery, resolve_surgery


class SurgeryRulesTest(unittest.TestCase):
    patient = {"userid": "u1", "disease": "腹腔粘连"}

    def profile(self, name="产品甲", surgery="腹腔粘连松解术"):
        return {"productType": "器械", "productName": name, "surgeryRules": [
            {"when": {"diseaseEqualsAny": ["腹腔粘连"]}, "surgeryName": surgery},
            {"when": {"diseaseEqualsAny": ["宫腔粘连"]}, "surgeryName": "宫腔镜下宫腔粘连分离术"},
        ]}

    def test_current_product_profile_and_patient_disease_determine_surgery(self):
        self.assertEqual(choose_surgery(self.profile(), self.patient), "腹腔粘连松解术")
        self.assertEqual(choose_surgery(self.profile("产品乙", "产品乙适用的测试术式"), self.patient), "产品乙适用的测试术式")
        self.assertEqual(choose_surgery(self.profile(), {**self.patient, "disease": "宫腔粘连"}), "宫腔镜下宫腔粘连分离术")

    def test_drug_product_has_no_surgery(self):
        self.assertEqual(choose_surgery({**self.profile(), "productType": "用药"}, self.patient), "")

    def test_simulation_label_removed_from_supported_surgery(self):
        for value, expected in [
            ("腹腔粘连松解术（模拟候选）", "腹腔粘连松解术"),
            ("腹腔粘连松解术(模拟候选)", "腹腔粘连松解术"),
            ("腹腔粘连松解术（腹腔镜）", "腹腔粘连松解术（腹腔镜）"),
        ]:
            with self.subTest(value=value):
                self.assertEqual(choose_surgery(self.profile(surgery=value), self.patient), expected)
        with self.assertRaises(ValueError):
            choose_surgery(self.profile(surgery="（模拟候选）"), self.patient)

    def test_uncertain_surgery_is_rejected_instead_of_stripping_qualifier(self):
        for name in [
            "待确认（前列腺术后粘连部位未详）",
            "宫腔镜下宫腔粘连分离术（器械适用性待核实）",
            "宫腔镜下宫腔粘连分离术（模拟候选；器械适用性待核实）",
            "可能行腹腔粘连松解术", "腹腔粘连松解术（需确认）",
        ]:
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "u1.*产品甲.*腹腔粘连.*不确定"):
                choose_surgery(self.profile(surgery=name), self.patient)

    def test_unmatched_disease_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "没有匹配"):
            choose_surgery(self.profile(), {**self.patient, "disease": "其他疾病"})

    def test_insufficient_evidence_uses_declared_scenario_and_keeps_internal_audit(self):
        profile = self.profile(surgery="待确认（部位未详）")
        profile['simulatedSurgeryRules'] = [{
            'when': {'diseaseEqualsAny': ['腹腔粘连']}, 'surgeryName': '腹腔粘连松解术',
            'assumptions': ['假设粘连位于腹腔且具备松解指征'], 'rationale': '用于情景数据，不证明手术发生或产品获批适用',
        }]
        name, audit = resolve_surgery(profile, self.patient)
        self.assertEqual(name, '腹腔粘连松解术')
        self.assertEqual(audit['userid'], 'u1')
        self.assertEqual(audit['assumptions'], profile['simulatedSurgeryRules'][0]['assumptions'])
        with self.assertRaises(ValueError):
            choose_surgery({**profile, 'allowSimulation': False}, self.patient)
        profile['surgeryRules'] = []
        self.assertEqual(choose_surgery(profile, self.patient), '腹腔粘连松解术')
        profile['simulatedSurgeryRules'][0]['assumptions'] = []
        with self.assertRaisesRegex(ValueError, 'assumptions'):
            choose_surgery(profile, self.patient)

    def test_ambiguous_surgery_is_rejected(self):
        profile = self.profile()
        profile["surgeryRules"].append({"when": {"diseaseContainsAny": ["粘连"]}, "surgeryName": "另一术式"})
        with self.assertRaisesRegex(ValueError, "多个"):
            choose_surgery(profile, self.patient)

    def test_missing_disease_condition_and_blank_name_are_rejected(self):
        for rule in ({"when": {}, "surgeryName": "通用术式"},
                     {"when": {"diseaseEqualsAny": ["腹腔粘连"]}, "surgeryName": " "}):
            with self.subTest(rule=rule), self.assertRaises(ValueError):
                choose_surgery({**self.profile(), "surgeryRules": [rule]}, self.patient)
