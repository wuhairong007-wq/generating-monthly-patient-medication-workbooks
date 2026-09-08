function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function medicationPlanSignature(items) {
  return JSON.stringify(items.map((item) => [
    item.drugName,
    item.displayName,
    item.specification ?? "",
    item.singleDose,
    item.frequency ?? "",
    item.medicationTime ?? "",
    item.treatmentDays ?? "",
  ]));
}

export function validateMedicationMinimums(payload) {
  const { meta, records } = payload;
  if (meta.productType !== "用药") return;

  const minimumCombined = meta.minimumCombinedMedicationCount ?? 3;
  const minimumDisease = meta.minimumDiseaseMedicationCount ?? 2;
  const combinedByUserid = meta.minimumCombinedMedicationCountByUserid ?? {};
  const diseaseByUserid = meta.minimumDiseaseMedicationCountByUserid ?? {};
  const rationaleByUserid = meta.medicationCountRationaleByUserid ?? {};
  const diseaseNamesByUserid = meta.diseaseMedicationNamesByUserid ?? {};

  for (const record of records) {
    const recordMinimumCombined = combinedByUserid[record.userid] ?? minimumCombined;
    const recordMinimumDisease = diseaseByUserid[record.userid] ?? minimumDisease;
    assert(Number.isInteger(recordMinimumCombined) && recordMinimumCombined >= 1 && recordMinimumCombined <= 5, `${record.userid}联合用药最低数量无效`);
    assert(Number.isInteger(recordMinimumDisease) && recordMinimumDisease >= 0 && recordMinimumDisease <= 4, `${record.userid}疾病治疗药最低数量无效`);
    assert(recordMinimumCombined >= 1 + recordMinimumDisease, `${record.userid}用药最低数量关系无效`);
    if (recordMinimumCombined < minimumCombined || recordMinimumDisease < minimumDisease) {
      assert(
        typeof rationaleByUserid[record.userid] === "string" && rationaleByUserid[record.userid].trim(),
        `${record.userid}降低用药最低数量缺少依据说明`,
      );
    }
    assert(record.combinedMedication.length >= recordMinimumCombined, `${record.userid}联合用药至少需要${recordMinimumCombined}项`);
    assert(record.combinedMedication[0] === meta.productName, `${record.userid}联合用药首项不是当前产品`);
    const diseaseNames = diseaseNamesByUserid[record.userid];
    assert(Array.isArray(diseaseNames) && new Set(diseaseNames).size >= recordMinimumDisease, `${record.userid}疾病治疗药至少需要${recordMinimumDisease}种`);
    assert(!diseaseNames.includes(meta.productName), `${record.userid}疾病治疗药来源不能包含当前产品`);
    assert(diseaseNames.every((name) => record.combinedMedication.includes(name)), `${record.userid}疾病治疗药来源与联合用药不一致`);
  }
}

export function validateMedicationPlanFields(payload) {
  const patients = payload.patients ?? [];
  const records = payload.records ?? [];
  const medicationItems = payload.medicationItems ?? [];
  const patientUserids = new Set(patients.map((patient) => patient.userid));
  const recordByUserid = new Map(records.map((record) => [record.userid, record]));
  const itemsByUserid = new Map(patients.map((patient) => [patient.userid, []]));

  for (const item of medicationItems) {
    assert(patientUserids.has(item.userid), `${item.userid}用药清单存在未知患者`);
    itemsByUserid.get(item.userid).push(item);
  }

  for (const patient of patients) {
    const record = recordByUserid.get(patient.userid);
    assert(record, `${patient.userid}缺少生成记录`);
    const items = itemsByUserid.get(patient.userid) ?? [];
    const itemDrugNames = items.map((item) => item.drugName);
    assert(
      JSON.stringify(itemDrugNames) === JSON.stringify(record.combinedMedication),
      `${patient.userid}用药清单与联合用药不一致`,
    );
    for (const item of items) {
      assert(
        typeof item.displayName === "string" && item.displayName.trim() && item.displayName === item.displayName.trim(),
        `${patient.userid}用药方案格式不符合：displayName必须为规范非空字符串`,
      );
      assert(
        item.singleDose !== null && item.singleDose !== undefined && String(item.singleDose).trim(),
        `${patient.userid}用药方案格式不符合：singleDose不能为空`,
      );
    }
    const expectedPlan = items
      .map((item) => `${item.displayName}${String(item.singleDose).trim()}`)
      .join("、");
    assert(
      patient.medicationPlan === expectedPlan,
      `${patient.userid}用药方案格式不符合：应为${expectedPlan}`,
    );
  }

  if (payload.meta?.productType === "用药") {
    const actualUniqueCount = new Set(
      patients.map((patient) => medicationPlanSignature(itemsByUserid.get(patient.userid) ?? [])),
    ).size;
    const declaredUniqueCount = payload.meta.uniqueMedicationPlanCount;
    const minimumUniqueCount = payload.meta.minimumUniqueMedicationPlanCount;
    assert(
      Number.isInteger(declaredUniqueCount) && declaredUniqueCount === actualUniqueCount,
      `用药方案去重数量与元数据不一致：实际${actualUniqueCount}种，元数据${declaredUniqueCount}种`,
    );
    assert(Number.isInteger(minimumUniqueCount), "用药方案最低去重目标必须为整数");
  }
}
