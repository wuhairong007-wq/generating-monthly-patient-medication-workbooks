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
