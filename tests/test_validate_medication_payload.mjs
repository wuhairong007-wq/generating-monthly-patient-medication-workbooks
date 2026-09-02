import assert from "node:assert/strict";

import {
  validateMedicationMinimums,
  validateMedicationPlanFields,
} from "../scripts/validate_medication_payload.mjs";

function payload({ combinedMedication, diseaseMedicationNames, productType = "用药" }) {
  return {
    meta: {
      productType,
      productName: "当前产品",
      minimumCombinedMedicationCount: 3,
      minimumDiseaseMedicationCount: 2,
      diseaseMedicationNamesByUserid: { u1: diseaseMedicationNames },
    },
    records: [
      {
        userid: "u1",
        combinedMedication,
        prescriptionList: combinedMedication.join(" + "),
        surgeryName: productType === "用药" ? "" : "测试手术",
      },
    ],
  };
}

function medicationPlanPayload(count = 4) {
  const allItems = [
    { drugName: "双歧杆菌四联活菌片", displayName: "双歧杆菌四联活菌片(思连康)", singleDose: "1.0g" },
    { drugName: "蒙脱石散", displayName: "蒙脱石散", singleDose: "3g" },
    { drugName: "口服补液盐I", displayName: "口服补液盐I", singleDose: "5.125g" },
    { drugName: "消旋卡多曲颗粒", displayName: "消旋卡多曲颗粒", singleDose: "30mg" },
    { drugName: "益生菌制剂", displayName: "益生菌制剂", singleDose: "2g" },
  ].slice(0, count).map((item) => ({ userid: "u1", ...item }));
  const combinedMedication = allItems.map((item) => item.drugName);
  return {
    meta: {
      productType: "用药",
      productName: "双歧杆菌四联活菌片",
      minimumCombinedMedicationCount: 3,
      minimumDiseaseMedicationCount: 2,
      minimumUniqueMedicationPlanCount: 1,
      uniqueMedicationPlanCount: 1,
      diseaseMedicationNamesByUserid: { u1: combinedMedication.slice(1) },
    },
    patients: [{
      userid: "u1",
      medicationPlan: allItems.map((item) => `${item.displayName}${item.singleDose}`).join("、"),
    }],
    records: [{
      userid: "u1",
      combinedMedication,
      prescriptionList: combinedMedication.join(" + "),
      surgeryName: "",
    }],
    medicationItems: allItems,
  };
}

assert.throws(
  () => validateMedicationMinimums(payload({
    combinedMedication: ["当前产品", "疾病药A"],
    diseaseMedicationNames: ["疾病药A"],
  })),
  /联合用药至少需要3项/,
);

assert.throws(
  () => validateMedicationMinimums(payload({
    combinedMedication: ["疾病药A", "当前产品", "疾病药B"],
    diseaseMedicationNames: ["疾病药A", "疾病药B"],
  })),
  /首项不是当前产品/,
);

assert.throws(
  () => validateMedicationMinimums(payload({
    combinedMedication: ["当前产品", "复溶液", "疾病药A"],
    diseaseMedicationNames: ["疾病药A"],
  })),
  /疾病治疗药至少需要2种/,
);

assert.throws(
  () => validateMedicationMinimums(payload({
    combinedMedication: ["当前产品", "疾病药A", "其他药"],
    diseaseMedicationNames: ["疾病药A", "疾病药B"],
  })),
  /疾病治疗药来源与联合用药不一致/,
);

assert.throws(
  () => validateMedicationMinimums(payload({
    combinedMedication: ["当前产品", "疾病药A", "疾病药B"],
    diseaseMedicationNames: ["当前产品", "疾病药A"],
  })),
  /疾病治疗药来源不能包含当前产品/,
);

assert.doesNotThrow(() => validateMedicationMinimums(payload({
  combinedMedication: ["当前产品", "疾病药A", "疾病药B"],
  diseaseMedicationNames: ["疾病药A", "疾病药B"],
})));

assert.doesNotThrow(() => validateMedicationMinimums(payload({
  productType: "器械",
  combinedMedication: ["围手术期药物"],
  diseaseMedicationNames: [],
})));

const exactPayload = medicationPlanPayload();
assert.doesNotThrow(() => validateMedicationPlanFields(exactPayload));
assert.equal(
  exactPayload.patients[0].medicationPlan,
  "双歧杆菌四联活菌片(思连康)1.0g、蒙脱石散3g、口服补液盐I5.125g、消旋卡多曲颗粒30mg",
);

const oldNarrativePayload = structuredClone(exactPayload);
oldNarrativePayload.patients[0].medicationPlan = "女，34岁，疾病为抗生素相关性腹泻。用药草案：双歧杆菌四联活菌片、蒙脱石散";
assert.throws(
  () => validateMedicationPlanFields(oldNarrativePayload),
  /用药方案格式不符合/,
);

const missingItemPayload = structuredClone(exactPayload);
missingItemPayload.medicationItems.pop();
assert.throws(
  () => validateMedicationPlanFields(missingItemPayload),
  /用药清单与联合用药不一致/,
);

const wrongOrderPayload = structuredClone(exactPayload);
[wrongOrderPayload.medicationItems[1], wrongOrderPayload.medicationItems[2]] = [
  wrongOrderPayload.medicationItems[2],
  wrongOrderPayload.medicationItems[1],
];
assert.throws(
  () => validateMedicationPlanFields(wrongOrderPayload),
  /用药清单与联合用药不一致/,
);

for (const count of [3, 4, 5]) {
  const dynamicPayload = medicationPlanPayload(count);
  assert.doesNotThrow(() => validateMedicationPlanFields(dynamicPayload));
  assert.equal(dynamicPayload.patients[0].medicationPlan.split("、").length, count);
}

const insufficientUniquePayload = structuredClone(exactPayload);
insufficientUniquePayload.meta.minimumUniqueMedicationPlanCount = 2;
insufficientUniquePayload.meta.uniqueMedicationPlanCount = 1;
assert.throws(
  () => validateMedicationPlanFields(insufficientUniquePayload),
  /用药方案去重后仅有1种，至少需要2种/,
);

const incorrectUniqueMetadataPayload = structuredClone(exactPayload);
incorrectUniqueMetadataPayload.meta.uniqueMedicationPlanCount = 2;
assert.throws(
  () => validateMedicationPlanFields(incorrectUniqueMetadataPayload),
  /用药方案去重数量与元数据不一致/,
);

console.log("validate_medication_payload tests passed");
