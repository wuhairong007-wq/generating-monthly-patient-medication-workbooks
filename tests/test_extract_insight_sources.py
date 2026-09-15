import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import json
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from extract_insight_sources import build_insight


def write_book(path, headers, rows, title=None):
    workbook = Workbook()
    sheet = workbook.active
    if title:
        sheet.append([title])
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    workbook.save(path)


class ExtractInsightSourcesTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        patient_id = "P001"
        write_book(root / "patients.xlsx", ["序号", "userid", "性别", "年龄", "地区", "疾病"], [[1, patient_id, "女", 42, "湖北省武汉市", "软组织血肿"]], "患者全病程数据")
        write_book(root / "plans.xlsx", ["userid", "AI健康管理师介绍", "AI健康管理方案", "AI状态", "审核状态"], [[patient_id, "介绍", "方案", "已生成", "已审核"]])
        write_book(root / "tracking.xlsx", ["序号", "患者ID", "体温监测次数", "血压、心率监测次数", "用药提醒次数", "患者响应率", "是否触发人工干预"], [[1, patient_id, 2, 1, 3, 50, "否"]], "AI跟踪提醒服务明细")
        followup_headers = ["序号", "患者ID", "随访时间"] + [f"{index}、问题" for index in range(1, 11)]
        write_book(root / "followups.xlsx", followup_headers, [[1, patient_id, "2026-07-15"] + ["A、良好"] * 10], "AI智能随访服务明细")
        symptom_headers = ["序号", "患者ID", "自评时间"] + [f"{index}、症状" for index in range(1, 7)]
        write_book(root / "symptoms.xlsx", symptom_headers, [[1, patient_id, "2026-07-10"] + ["B、轻微（2 分）"] * 6, [2, patient_id, "2026-08-01"] + ["E、严重（5 分）"] * 6], "AI症状自评服务明细")
        write_book(root / "medications.xlsx", ["userid", "用药方案确认时间", "药品名称", "规格", "用药频率", "疗程天数"], [[patient_id, "2026-07-01", "注射用胰蛋白酶", "2.5万单位", "每日1次", 3]])
        write_book(root / "ae.xlsx", ["序号", "患者ID", "疾病", "不良反应发生时间", "不良反应严重程度分级", "处理结果/转归", "是否触发人工干预"], [[1, patient_id, "软组织血肿", "2026-07-20", "轻度", "好转", "否"]], "不良反应（AE）记录清单")
        self.paths = [str(path) for path in root.glob("*.xlsx")]

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_builds_auditable_metrics_and_filters_dates(self):
        insight = build_insight(self.paths, "注射用胰蛋白酶", "2026-07-01", "2026-07-31")
        self.assertEqual(insight["metadata"]["patientCount"], 1)
        self.assertEqual(insight["metadata"]["serviceRegion"], "湖北省武汉市")
        self.assertEqual(insight["metadata"]["client"], "")
        self.assertEqual(insight["metadata"]["provider"], "")
        self.assertEqual(insight["sourceDiagnostics"]["roles"]["symptomAssessments"]["includedRows"], 1)
        self.assertEqual(insight["metrics"]["followupCoverage"], {"numerator": 1, "denominator": 1, "value": 1.0, "display": "100.0%"})
        self.assertEqual(insight["metrics"]["trackingCoverage"], {"numerator": 1, "denominator": 1, "value": 1.0, "display": "100.0%"})
        self.assertEqual(insight["metrics"]["symptoms"]["dimensionMeans"], [2.0] * 6)
        self.assertEqual(insight["metrics"]["adverseEventRate"]["numerator"], 1)

    def test_optional_adverse_events_are_not_treated_as_zero_events(self):
        paths = [path for path in self.paths if not path.endswith("ae.xlsx")]
        insight = build_insight(paths, "注射用胰蛋白酶", "2026-07-01", "2026-07-31")
        self.assertFalse(insight["sourceDiagnostics"]["roles"]["adverseEvents"]["provided"])
        self.assertIsNone(insight["metrics"]["adverseEventRate"])
        self.assertIsNone(insight["metrics"]["adverseEvents"]["patientCount"])
        self.assertIsNone(insight["metrics"]["adverseEvents"]["recordCount"])
        self.assertEqual(insight["metrics"]["riskDistribution"], [])
        self.assertEqual(len(insight["metrics"]["serviceGoals"]), 3)
        self.assertEqual(insight["metrics"]["followupCoverage"]["numerator"], 1)

    def test_six_files_cannot_omit_any_other_required_role(self):
        for omitted in ["patients.xlsx", "plans.xlsx", "tracking.xlsx", "followups.xlsx", "symptoms.xlsx", "medications.xlsx"]:
            with self.subTest(omitted=omitted), self.assertRaisesRegex(ValueError, "缺少工作簿角色"):
                build_insight([path for path in self.paths if not path.endswith(omitted)], "注射用胰蛋白酶", "2026-07-01", "2026-07-31")

    def test_optional_file_still_rejects_duplicate_roles(self):
        duplicate = Path(self.temp_dir.name) / "ae-copy.xlsx"
        duplicate.write_bytes(next(Path(path) for path in self.paths if path.endswith("ae.xlsx")).read_bytes())
        paths = [path for path in self.paths if not path.endswith("plans.xlsx")] + [str(duplicate)]
        with self.assertRaisesRegex(ValueError, "角色重复"):
            build_insight(paths, "注射用胰蛋白酶", "2026-07-01", "2026-07-31")

    def test_optional_file_is_not_silently_ignored_when_invalid(self):
        ae_path = next(Path(path) for path in self.paths if path.endswith("ae.xlsx"))
        original = ae_path.read_bytes()
        ae_path.unlink()
        with self.assertRaisesRegex(ValueError, "文件不存在"):
            build_insight(self.paths, "注射用胰蛋白酶", "2026-07-01", "2026-07-31")
        write_book(ae_path, ["任意字段"], [["不是不良反应表"]])
        with self.assertRaisesRegex(ValueError, "表头"):
            build_insight(self.paths, "注射用胰蛋白酶", "2026-07-01", "2026-07-31")
        write_book(ae_path, ["患者ID", "不良反应发生时间", "不良反应严重程度分级"], [["P001", "错误日期", "轻度"]])
        with self.assertRaisesRegex(ValueError, "无法解析"):
            build_insight(self.paths, "注射用胰蛋白酶", "2026-07-01", "2026-07-31")
        ae_path.write_bytes(original)

    def test_rejects_duplicate_source_paths(self):
        with self.assertRaisesRegex(ValueError, "重复"):
            build_insight(self.paths[:-1] + [self.paths[0]], "注射用胰蛋白酶", "2026-07-01", "2026-07-31")

    def test_empty_adverse_events_keep_patient_denominator(self):
        ae_path = next(path for path in self.paths if path.endswith("ae.xlsx"))
        write_book(Path(ae_path), ["序号", "患者ID", "疾病", "不良反应发生时间", "不良反应严重程度分级", "处理结果/转归", "是否触发人工干预"], [], "不良反应（AE）记录清单")
        insight = build_insight(self.paths, "注射用胰蛋白酶", "2026-07-01", "2026-07-31")
        self.assertEqual(insight["metrics"]["adverseEventRate"], {"numerator": 0, "denominator": 1, "value": 0.0, "display": "0.0%"})

    def test_accepts_cover_parties(self):
        insight = build_insight(self.paths, "注射用胰蛋白酶", "2026-07-01", "2026-07-31", "甲方", "乙方")
        self.assertEqual(insight["metadata"]["client"], "甲方")
        self.assertEqual(insight["metadata"]["provider"], "乙方")

    def test_accepts_monthly_patient_master_header_aliases(self):
        patient_path = next(Path(path) for path in self.paths if path.endswith('patients.xlsx'))
        write_book(patient_path, ['患者唯一标识', '性别', '年龄', '所属地区', '疾病'],
                   [['P001', '女', 58, '湖北省武汉市', '软组织血肿']])
        insight = build_insight(self.paths, '注射用胰蛋白酶', '2026-07-01', '2026-07-31')
        self.assertEqual(insight['records']['patients'][0]['userid'], 'P001')
        self.assertEqual(insight['metadata']['serviceRegion'], '湖北省武汉市')

    def test_medication_list_requires_actual_confirmation_date(self):
        medication_path = next(Path(path) for path in self.paths if path.endswith('medications.xlsx'))
        write_book(medication_path, ['userid', '药品名称', '规格'], [['P001', '测试药品', '10mg']])
        with self.assertRaisesRegex(ValueError, '表头'):
            build_insight(self.paths, '注射用胰蛋白酶', '2026-07-01', '2026-07-31')

    def test_rejects_empty_patient_master(self):
        patient_path = next(path for path in self.paths if path.endswith("patients.xlsx"))
        write_book(Path(patient_path), ["序号", "userid", "性别", "年龄", "地区", "疾病"], [], "患者全病程数据")
        with self.assertRaisesRegex(ValueError, "患者主表为空"):
            build_insight(self.paths, "注射用胰蛋白酶", "2026-07-01", "2026-07-31")


if __name__ == "__main__":
    unittest.main()
