import importlib.util
import os
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(SKILL_DIR / "scripts"))
MODULE_PATH = SKILL_DIR / "scripts" / "generate_payload.py"
SPEC = importlib.util.spec_from_file_location("generate_payload", MODULE_PATH)
generate_payload = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(generate_payload)


def patient(userid="u1", disease="功能性便秘"):
    return {
        "userid": userid,
        "disease": disease,
        "gender": "女",
        "age": 40,
        "allergyHistory": "无",
        "adverseEvent": "否",
    }


def profile():
    return {
        "schemaVersion": 2,
        "productType": "用药",
        "productName": "测试产品",
        "evidence": [{"title": "产品说明书", "url": "https://example.test/label", "scope": "产品用法"}],
        "baseMedication": {
            "drugName": "测试产品",
            "specification": "10mg/片",
            "singleDose": "10mg",
            "route": "口服",
            "frequency": "每日1次",
            "medicationTime": "早餐后",
            "treatmentDays": 30,
            "precautions": "需经医师或药师审核",
        },
        "directProductAdjuncts": [],
        "diseasePlans": [{
            "id": "便秘方案",
            "when": {"diseaseEqualsAny": ["功能性便秘"]},
            "evidence": [{"title": "指南", "url": "https://example.test/guide", "scope": "便秘治疗"}],
            "allowProductOnly": False,
            "medicationGroups": [],
        }],
        "surgeryRules": [],
    }


def candidate(name):
    return {
        "drugName": name,
        "specification": "10mg/片",
        "singleDose": "10mg",
        "route": "口服",
        "frequency": "每日1次",
        "medicationTime": "早餐后",
        "treatmentDays": 30,
        "precautions": "仅在医师确认疾病指征后启用",
        "role": "diseaseTreatment",
        "diseaseRationale": "用于功能性便秘治疗",
        "evidence": [{"title": "官方指南", "url": "https://www.nhc.gov.cn/guide", "scope": "功能性便秘候选药"}],
    }


class SearchFallbackTest(unittest.TestCase):
    def test_extends_empty_plan_from_complete_search_candidates(self):
        calls = []

        def search_fn(product_name, disease):
            calls.append((product_name, disease))
            return {"status": "success", "candidates": [candidate("候选药A"), candidate("候选药B")], "sources": []}

        original = profile()
        extended, audit = generate_payload.maybe_search_and_extend_profile(
            original, [patient()], search_fn=search_fn,
        )

        self.assertEqual(calls, [("测试产品", "功能性便秘")])
        self.assertEqual(len(extended["diseasePlans"][0]["medicationGroups"]), 2)
        self.assertEqual(extended["diseasePlans"][0]["medicationGroups"][0]["alternatives"][0]["drugName"], "候选药A")
        self.assertEqual(audit[0]["status"], "success")
        self.assertEqual(original["diseasePlans"][0]["medicationGroups"], [])

    def test_incomplete_search_result_keeps_plan_empty(self):
        def search_fn(product_name, disease):
            return {"status": "incomplete", "candidates": [], "incompleteCandidates": [{"drugName": "候选药A"}], "sources": []}

        extended, audit = generate_payload.maybe_search_and_extend_profile(
            profile(), [patient()], search_fn=search_fn,
        )

        self.assertEqual(extended["diseasePlans"][0]["medicationGroups"], [])
        self.assertEqual(audit[0]["status"], "incomplete")

    def test_search_can_be_disabled_explicitly(self):
        def search_fn(product_name, disease):
            raise AssertionError("search should be disabled")

        original = profile()
        old = os.environ.get("AUTO_MEDICATION_SEARCH")
        os.environ["AUTO_MEDICATION_SEARCH"] = "0"
        try:
            extended, audit = generate_payload.maybe_search_and_extend_profile(
                original, [patient()], search_fn=search_fn,
            )
        finally:
            if old is None:
                os.environ.pop("AUTO_MEDICATION_SEARCH", None)
            else:
                os.environ["AUTO_MEDICATION_SEARCH"] = old

        self.assertEqual(extended["diseasePlans"][0]["medicationGroups"], [])
        self.assertEqual(audit[0]["status"], "disabled")


if __name__ == "__main__":
    unittest.main()
