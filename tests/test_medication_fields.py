import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from generate_payload import validated_medication
from test_disease_specific_plans import medication, patient


SECTIONS = {
    "饮食禁忌": "测试说明书的饮食要求",
    "合并用药": "测试说明书的相互作用及配伍要求",
    "用药观察": "测试说明书的观察项目；需经医师或药师审核",
    "储存保存": "测试包装标示的温度及避光要求",
}


def raw_medication():
    return {**medication("测试产品"), "medicationTime": "06:00、14:00、22:00",
            "frequency": "每日3次", "precautions": copy.deepcopy(SECTIONS)}


class MedicationFieldsTest(unittest.TestCase):
    def test_structured_precautions_render_four_sections_in_user_order(self):
        raw = raw_medication()
        raw["precautions"] = dict(reversed(list(SECTIONS.items())))
        output = validated_medication(raw, patient("u1", "测试疾病"))
        self.assertEqual(output["precautions"], "；".join(f"{key}：{value}" for key, value in SECTIONS.items()))
        self.assertIsInstance(raw["precautions"], dict)

    def test_formatted_precautions_remain_compatible(self):
        raw = raw_medication()
        raw["precautions"] = "；".join(f"{key}：{value}" for key, value in SECTIONS.items())
        output = validated_medication(raw, patient("u1", "测试疾病"))
        self.assertEqual(output["precautions"], raw["precautions"])

    def test_incomplete_or_unstructured_precautions_do_not_get_invented_content(self):
        missing = copy.deepcopy(SECTIONS)
        missing.pop("储存保存")
        for value in [missing, {**SECTIONS, "储存保存": " "}, "一般注意事项", {},
                      {**SECTIONS, "储存保存": 25}]:
            with self.subTest(value=value):
                raw = raw_medication()
                raw["precautions"] = value
                with self.assertRaisesRegex(ValueError, "u1.*注意事项"):
                    validated_medication(raw, patient("u1", "测试疾病"))

    def test_individual_safety_notes_stay_in_observation_not_storage(self):
        raw = raw_medication()
        raw["femalePrecautions"] = "测试女性复核事项"
        raw["ageDoseRules"] = [{"ageMin": 65, "precautions": "测试年龄复核事项"}]
        person = patient("u1", "测试疾病", allergy="花粉过敏", gender="女", age=70)
        person["adverseEvent"] = "是"
        notes = validated_medication(raw, person)["precautions"]
        observation = notes.split("用药观察：")[1].split("；储存保存：")[0]
        for value in ["测试女性复核事项", "测试年龄复核事项", "花粉过敏", "本月AE记录为是"]:
            self.assertIn(value, observation)
        self.assertTrue(notes.endswith("储存保存：" + SECTIONS["储存保存"]))

    def test_meal_remark_moves_out_of_time_field_without_losing_instruction(self):
        for value, expected in [
            ("06:00、14:00、22:00（随餐或餐后）", "06:00、14:00、22:00"),
            ("06:00、22:00 (餐后)", "06:00、22:00"),
        ]:
            with self.subTest(value=value):
                raw = raw_medication()
                raw["medicationTime"] = value
                output = validated_medication(raw, patient("u1", "测试疾病"))
                self.assertEqual(output["medicationTime"], expected)
                diet = output["precautions"].split("饮食禁忌：")[1].split("；合并用药：")[0]
                self.assertIn("餐后", diet)

    def test_unknown_or_invalid_time_is_not_guessed(self):
        for value in ["早餐后", "固定时间", "06:00至22:00", "24:00", "06:60", "6:00", "早06:00", "06:00、14:00备注"]:
            with self.subTest(value=value):
                raw = raw_medication()
                raw["medicationTime"] = value
                with self.assertRaisesRegex(ValueError, "用药时间"):
                    validated_medication(raw, patient("u1", "测试疾病"))


if __name__ == "__main__":
    unittest.main()
