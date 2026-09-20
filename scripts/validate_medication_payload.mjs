function assert(condition, message) {
  if (!condition) throw new Error(message);
}

const SPECIAL_DEVICE_COMPANY = "商联医药(河南)有限公司（器械）";

export function validateCompanyConsumableRules(payload) {
  const { meta, records = [] } = payload;
  assert(typeof meta.companyName === "string" && meta.companyName.trim(), "公司名称不能为空");
  const special = meta.companyName === SPECIAL_DEVICE_COMPANY && meta.productType === "器械";
  if (special) {
    assert(meta.consumableName === meta.productName, "特殊器械场景耗材名称必须等于当前产品名称");
    for (const record of records) {
      assert(!String(record.prescriptionList ?? "").includes(meta.productName), `${record.userid}处方清单不能包含当前产品名称`);
    }
  } else {
    assert(String(meta.consumableName ?? "") === "", "非特殊场景耗材名称必须为空");
  }
}

export function validateSurgeryNames(payload) {
  const uncertain = /待确认|待核实|待核对|待明确|待定|未详|不详|未明确|不明确|未确定|不确定|未核实|尚未核实|适用性不明|需确认|需核实|需明确|可能|疑似|暂不确定|无法确定|模拟候选/;
  const patients = new Map((payload.patients ?? []).map(patient => [patient.userid, patient]));
  for (const record of payload.records ?? []) {
    const label = `${record.userid}（产品：${payload.meta.productName}；疾病：${patients.get(record.userid)?.disease ?? ""}）手术名称`;
    if (payload.meta.productType === "用药") {
      assert(record.surgeryName === "", `${label}必须为空`);
    } else {
      assert(typeof record.surgeryName === "string" && record.surgeryName.trim(), `${label}不能为空`);
      assert(!uncertain.test(record.surgeryName), `${label}包含不确定或模拟标识：${record.surgeryName}；须核对依据重新匹配，不得仅删除限定语`);
    }
  }
}

export function validateSimulationPresentation(payload, outputPaths, sheets = []) {
  const audit = payload.meta.surgerySimulationAudit ?? [];
  assert(!audit.length || payload.meta.simulation === true, "存在情景补全记录但缺少meta.simulation标记");
  if (payload.meta.simulation !== true) return;
  for (const outputPath of outputPaths) {
    const fileName = String(outputPath).split(/[\\/]/).pop();
    assert(fileName.includes("模拟"), "情景工作簿文件名必须包含模拟");
  }
  for (const sheet of sheets) {
    assert(!String(sheet.name).includes("模拟"), "工作表名称不能包含模拟文案");
    for (const row of sheet.values) {
      assert(row.every(value => typeof value !== "string" || !value.includes("模拟")), "工作簿内容不能包含模拟文案，请重写展示内容并保留临床注意事项");
    }
  }
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
  if (meta.productType === "器械") {
    for (const record of records) {
      const combined = meta.minimumCombinedMedicationCountByUserid?.[record.userid] ?? 3;
      const disease = meta.minimumDiseaseMedicationCountByUserid?.[record.userid] ?? 3;
      assert(Number.isInteger(combined) && combined >= 3 && combined <= 5 && Number.isInteger(disease) && disease >= 3 && disease <= combined, `${record.userid}器械最低药品数量必须至少3种且疾病治疗药数量不大于总数`);
      const names = record.combinedMedication;
      assert(!names.includes(meta.productName), `${record.userid}器械产品不能计入联合用药药品数`);
      assert(new Set(names).size === names.length, `${record.userid}器械联合用药存在重复药品`);
      assert(names.length >= combined, `${record.userid}联合用药至少需要${combined}项`);
      const diseaseNames = meta.diseaseMedicationNamesByUserid?.[record.userid];
      assert(Array.isArray(diseaseNames) && new Set(diseaseNames).size >= disease, `${record.userid}疾病治疗药至少需要${disease}种`);
      assert(diseaseNames.every(name => names.includes(name)), `${record.userid}疾病治疗药来源与联合用药不一致`);
    }
    return;
  }

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
