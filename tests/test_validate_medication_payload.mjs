import assert from "node:assert/strict";

import { validateMedicationMinimums } from "../scripts/validate_medication_payload.mjs";

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

console.log("validate_medication_payload tests passed");
