import assert from "node:assert/strict";
import { validateMedicationPlanFields } from "../scripts/validate_medication_payload.mjs";

const notes = "饮食禁忌：测试饮食要求；合并用药：测试配伍要求；用药观察：测试观察项目；储存保存：测试包装贮藏要求";
const payload = {
  meta: { productType: "用药", minimumUniqueMedicationPlanCount: 1, uniqueMedicationPlanCount: 1 },
  patients: [{ userid: "u1", medicationPlan: "测试药10mg" }],
  records: [{ userid: "u1", combinedMedication: ["测试药"] }],
  medicationItems: [{
    userid: "u1", drugName: "测试药", displayName: "测试药", singleDose: "10mg",
    medicationTime: "06:00、14:00、22:00", precautions: notes,
  }],
};
assert.doesNotThrow(() => validateMedicationPlanFields(payload));
for (const punctuation of ["。；", "；；", "，。", "、，", "！！", "?!", ".;", "：：", "。 \n；"]) {
  for (const precautions of [
    notes.replace("；合并用药", `${punctuation}合并用药`),
    notes.replace("测试观察项目", `先核对${punctuation}再观察`),
  ]) {
    const invalid = structuredClone(payload);
    invalid.medicationItems[0].precautions = precautions;
    assert.throws(() => validateMedicationPlanFields(invalid), /注意事项.*连续标点/);
  }
}
const normalPunctuation = structuredClone(payload);
normalPunctuation.medicationItems[0].precautions = notes.replace(
  "测试观察项目", "单次0.5mg（按说明书）；06:00观察“皮疹”等表现");
assert.doesNotThrow(() => validateMedicationPlanFields(normalPunctuation));
for (const section of ["饮食禁忌", "合并用药", "用药观察", "储存保存"]) {
  for (const wording of ["需医师审核、药房核对", "**需医师审核、药房核对**", "需医师审核", "药房核对"]) {
    const invalid = structuredClone(payload);
    invalid.medicationItems[0].precautions = notes.replace(`${section}：`, `${section}：${wording}；`);
    assert.throws(() => validateMedicationPlanFields(invalid), /注意事项.*不得包含/);
  }
}
for (const value of ["06:00、14:00、22:00（随餐或餐后）", "早餐后", "06:00备注", "24:00"]) {
  const invalid = structuredClone(payload);
  invalid.medicationItems[0].medicationTime = value;
  assert.throws(() => validateMedicationPlanFields(invalid), /用药时间/);
}
for (const value of [
  "需经医师或药师审核",
  notes.replace("储存保存：测试包装贮藏要求", "储存保存："),
  notes.replace("储存保存：测试包装贮藏要求", ""),
  notes.replace("饮食禁忌：", "储存保存："),
  `额外前缀${notes}`,
]) {
  const invalid = structuredClone(payload);
  invalid.medicationItems[0].precautions = value;
  assert.throws(() => validateMedicationPlanFields(invalid), /注意事项/);
}
console.log("Medication clock-only time and four-section precautions tests passed");
