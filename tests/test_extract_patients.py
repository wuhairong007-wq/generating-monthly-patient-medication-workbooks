import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "extract_patients.py"

REMINDER_HEADERS = [
    "序号", "患者唯一标识", "姓名", "性别", "年龄", "疾病", "既往过敏史", "联合用药",
    "用药方案确认时间", "用药方案", "用药周期", "方案链接", "本月是否发生不良反应（AE）",
]


def write_workbook(path, headers, rows):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["测试输入"])
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    workbook.save(path)


class ExtractPatientsTest(unittest.TestCase):
    def run_extractor(self, headers, rows):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.xlsx"
            output = Path(temp_dir) / "patients.json"
            write_workbook(source, headers, rows)
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--source", str(source), "--output", str(output)],
                capture_output=True,
                text=True,
                check=False,
            )
            payload = json.loads(output.read_text(encoding="utf-8")) if output.exists() else None
            return result, payload

    def test_accepts_medication_reminder_thirteen_column_format(self):
        row = [
            1, "u1", "张*", "女", 42, "创伤后局部水肿、积血", "无",
            "旧联合用药", "2026-08-26 16:16:07", "旧用药方案", "7天", "https://example.test", "否",
        ]

        result, payload = self.run_extractor(REMINDER_HEADERS, [row])

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(payload["inputFormat"], "medicationReminder13")
        self.assertEqual(payload["headers"], REMINDER_HEADERS)
        patient = payload["patients"][0]
        self.assertEqual(patient["userid"], "u1")
        self.assertEqual(patient["sourceConfirmationTime"], "2026-08-26 16:16:07")
        self.assertEqual(patient["confirmationTime"], "2026-08-26 16:16:07")
        self.assertEqual(patient["activateTime"], "")
        self.assertEqual(patient["patientName"], "张*")
        self.assertEqual(patient["disease"], "创伤后局部水肿、积血")
        self.assertEqual(payload["summary"]["activationMonths"], {})

    def test_rejects_reminder_row_without_confirmation_time(self):
        row = [
            1, "u1", "张*", "女", 42, "创伤后局部水肿、积血", "无",
            "", "", "", "", "", "否",
        ]

        result, payload = self.run_extractor(REMINDER_HEADERS, [row])

        self.assertNotEqual(result.returncode, 0)
        self.assertIsNone(payload)
        self.assertIn("用药方案确认时间无效", result.stderr)

    def test_reads_surgery_column_without_shifting_fields_or_reusing_old_surgery(self):
        headers = REMINDER_HEADERS[:7] + ["手术名称"] + REMINDER_HEADERS[7:]
        row = [1, "u-device", "测试患者", "女", 42, "腹腔粘连", "青霉素过敏",
               "旧产品的手术，不能沿用", "旧药", "2026-08-26 16:16:07", "旧方案", "7天", "", "是"]
        result, payload = self.run_extractor(headers, [row])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(payload["inputFormat"], "medicationReminder14")
        patient = payload["patients"][0]
        self.assertEqual(patient["allergyHistory"], "青霉素过敏")
        self.assertEqual(patient["adverseEvent"], "是")
        self.assertEqual(patient["sourceConfirmationTime"], "2026-08-26 16:16:07")
        self.assertEqual(patient["activateTime"], "")
        self.assertNotIn("surgeryName", patient)

    def test_accepts_fifteen_column_reminder_with_consumable_name(self):
        headers = REMINDER_HEADERS[:7] + ["手术名称", "耗材名称"] + REMINDER_HEADERS[7:]
        row = [1, "u-device", "测试患者", "女", 42, "腹腔粘连", "无",
               "腹腔粘连松解术", "测试耗材", "药A、药B、药C", "2026-08-26 16:16:07",
               "旧方案", "7天", "", "否"]

        result, payload = self.run_extractor(headers, [row])

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(payload["inputFormat"], "medicationReminder15")
        self.assertEqual(payload["patients"][0]["sourceConfirmationTime"], "2026-08-26 16:16:07")
        self.assertNotIn("consumableName", payload["patients"][0])

    def test_accepts_sixteen_column_reminder_with_source_metadata(self):
        headers = REMINDER_HEADERS[:7] + ["用户类型", "来源任务ID", "来源月份"] + REMINDER_HEADERS[7:]
        row = [1, "u-source", "来源患者", "女", 42, "腹腔粘连", "无",
               "续订用户", 16, "2026-08", "旧药", "2026-09-09 11:25:02",
               "旧方案", "1天", "", "否"]

        result, payload = self.run_extractor(headers, [row])

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(payload["inputFormat"], "medicationReminder16")
        patient = payload["patients"][0]
        self.assertEqual(patient["userType"], "续订用户")
        self.assertEqual(patient["sourceTaskId"], "16")
        self.assertEqual(patient["sourceMonth"], "2026-08")
        self.assertEqual(patient["sourceConfirmationTime"], "2026-09-09 11:25:02")

    def test_accepts_eighteen_column_generated_reminder_roundtrip(self):
        headers = REMINDER_HEADERS[:7] + ["用户类型", "来源任务ID", "来源月份", "手术名称", "耗材名称"] + REMINDER_HEADERS[7:]
        row = [1, "u-roundtrip", "回读患者", "男", 51, "粘连性肠梗阻", "无",
               "新用户", "", "", "粘连松解术", "赛必妥", "药A、药B、药C",
               "2026-09-10 12:00:00", "方案", "1天", "", "否"]

        result, payload = self.run_extractor(headers, [row])

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(payload["inputFormat"], "medicationReminder18")
        patient = payload["patients"][0]
        self.assertEqual((patient["userType"], patient["sourceTaskId"], patient["sourceMonth"]),
                         ("新用户", "", ""))

    def test_keeps_existing_eighteen_column_contract(self):
        headers = [
            "序号", "患者唯一标识", "姓名", "激活日期", "性别", "年龄", "联系电话", "所属地区",
            "疾病", "既往过敏史", "AI用药提醒次数", "AI随访次数", "症状自评完成次数",
            "患教内容阅读次数", "AI服务使用概况", "本月是否发生不良反应（AE）", "AE严重程度分级", "患者标签",
        ]
        row = [1, "u1", "张*", "2026-08-26 15:16:07", "女", 42, "", "", "脑梗死", "无", 0, 0, 0, 0, "", "否", "", ""]

        result, payload = self.run_extractor(headers, [row])

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(payload.get("inputFormat"), "monthlyPatient18")
        self.assertEqual(payload["patients"][0]["activateTime"], "2026-08-26 15:16:07")
        self.assertNotIn("sourceConfirmationTime", payload["patients"][0])

    def test_normalizes_legacy_and_current_normal_patient_tags(self):
        headers = [
            "序号", "患者唯一标识", "姓名", "激活日期", "性别", "年龄", "联系电话", "所属地区",
            "疾病", "既往过敏史", "AI用药提醒次数", "AI随访次数", "症状自评完成次数",
            "患教内容阅读次数", "AI服务使用概况", "本月是否发生不良反应（AE）", "AE严重程度分级", "患者标签",
        ]
        rows = [
            [1, "legacy", "旧值患者", "2026-08-26 15:16:07", "女", 42, "", "", "脑梗死", "无", 0, 0, 0, 0, "", "否", "", "无"],
            [2, "current", "新值患者", "2026-08-26 15:16:07", "男", 51, "", "", "冠心病", "无", 0, 0, 0, 0, "", "否", "", "正常"],
        ]

        result, payload = self.run_extractor(headers, rows)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            [patient["patientTags"] for patient in payload["patients"]],
            ["正常", "正常"],
        )


if __name__ == "__main__":
    unittest.main()
