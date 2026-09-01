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
