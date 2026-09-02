function assert(condition, message) {
  if (!condition) throw new Error(message);
}

export function validateMedicationMinimums(payload) {
  const { meta, records } = payload;
  if (meta.productType !== "用药") return;

  const minimumCombined = meta.minimumCombinedMedicationCount ?? 3;
  const minimumDisease = meta.minimumDiseaseMedicationCount ?? 2;
  const diseaseNamesByUserid = meta.diseaseMedicationNamesByUserid ?? {};

  for (const record of records) {
    assert(record.combinedMedication.length >= minimumCombined, `${record.userid}联合用药至少需要${minimumCombined}项`);
    assert(record.combinedMedication[0] === meta.productName, `${record.userid}联合用药首项不是当前产品`);
    const diseaseNames = diseaseNamesByUserid[record.userid];
    assert(Array.isArray(diseaseNames) && new Set(diseaseNames).size >= minimumDisease, `${record.userid}疾病治疗药至少需要${minimumDisease}种`);
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
    const actualUniqueCount = new Set(patients.map((patient) => patient.medicationPlan)).size;
    const declaredUniqueCount = payload.meta.uniqueMedicationPlanCount;
    const minimumUniqueCount = payload.meta.minimumUniqueMedicationPlanCount;
    assert(
      Number.isInteger(declaredUniqueCount) && declaredUniqueCount === actualUniqueCount,
      `用药方案去重数量与元数据不一致：实际${actualUniqueCount}种，元数据${declaredUniqueCount}种`,
    );
    assert(
      Number.isInteger(minimumUniqueCount) && actualUniqueCount >= minimumUniqueCount,
      `用药方案去重后仅有${actualUniqueCount}种，至少需要${minimumUniqueCount}种`,
    );
  }
}
