import assert from "node:assert/strict";
import { validateMedicationPlanFields } from "../scripts/validate_medication_payload.mjs";

const names = ["出院药A", "出院药B", "出院药C"];
const payload = {
  meta: { productType: "器械" },
  patients: [{ userid: "u1", medicationPlan: names.map(name => `${name}10mg`).join("、") }],
  records: [{ userid: "u1", combinedMedication: names }],
  medicationItems: names.map(drugName => ({
    userid: "u1", drugName, displayName: drugName, singleDose: "10mg",
    medicationTime: "08:00",
    precautions: "饮食禁忌：测试；合并用药：测试；用药观察：测试；储存保存：测试",
    careStage: "postDischarge", dischargeRationale: "测试出院后给药依据",
    dischargeEvidence: [{ title: "测试依据", url: "https://example.test", scope: "测试出院方案" }],
  })),
};

assert.doesNotThrow(() => validateMedicationPlanFields(payload));
for (const [field, value] of [
  ["careStage", undefined], ["careStage", "inpatientOnly"],
  ["dischargeRationale", ""], ["dischargeEvidence", []],
  ["dischargeEvidence", [{ title: "", url: "", scope: "" }]],
]) {
  const invalid = structuredClone(payload);
  invalid.medicationItems[0][field] = value;
  assert.throws(() => validateMedicationPlanFields(invalid), /u1.*出院后/);
}

const fixedSource = structuredClone(payload);
fixedSource.meta.combinedMedicationSource = "关联厂家用药";
fixedSource.patients[0].sourceCombinedMedication = names.join("；");
fixedSource.medicationItems[0].careStage = "inpatientOnly";
assert.throws(() => validateMedicationPlanFields(fixedSource), /u1.*出院后/);
console.log("device discharge validation tests passed");
