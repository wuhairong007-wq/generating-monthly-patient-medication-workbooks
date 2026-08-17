import fs from "node:fs/promises";
import path from "node:path";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";

const nodeModules = process.env.CODEX_NODE_MODULES;
if (!nodeModules) throw new Error("CODEX_NODE_MODULES is required");
const runtimeRequire = createRequire(path.join(nodeModules, "package.json"));
const artifactToolPath = runtimeRequire.resolve("@oai/artifact-tool");
const { FileBlob, SpreadsheetFile } = await import(pathToFileURL(artifactToolPath).href);

function parseArgs(argv) {
  const result = {};
  for (let index = 0; index < argv.length; index += 2) {
    if (!argv[index]?.startsWith("--") || argv[index + 1] === undefined) throw new Error(`参数错误：${argv[index] ?? ""}`);
    result[argv[index].slice(2)] = argv[index + 1];
  }
  return result;
}

const args = parseArgs(process.argv.slice(2));
for (const key of ["payload", "reminder-template", "medication-template", "output-dir"]) {
  if (!args[key]) throw new Error(`缺少--${key}`);
}
const payloadPath = path.resolve(args.payload);
const reminderTemplatePath = path.resolve(args["reminder-template"]);
const medicationTemplatePath = path.resolve(args["medication-template"]);
const outputDir = path.resolve(args["output-dir"]);
const earlyPayload = JSON.parse(await fs.readFile(payloadPath, "utf8"));
const safeProductName = earlyPayload.meta.productName.replace(/[\\/:*?"<>|]/g, "_");
const reminderOutputPath = path.join(outputDir, `用药提醒_${safeProductName}.xlsx`);
const medicationOutputPath = path.join(outputDir, `用药方案_${safeProductName}.xlsx`);
const progressPath = path.join(outputDir, "progress.log");

async function progress(message) {
  await fs.mkdir(outputDir, { recursive: true });
  await fs.appendFile(progressPath, `${new Date().toISOString()} ${message}\n`, "utf8");
}

const reminderHeaders = [
  "序号", "患者唯一标识", "姓名", "性别", "年龄", "疾病", "既往过敏史", "联合用药",
  "用药方案确认时间", "用药方案", "用药周期", "方案链接", "本月是否发生不良反应（AE）",
];
const medicationHeaders = [
  "序号", "患者唯一标识", "姓名", "药品名称", "规格", "每次用量", "用药频次", "用药时间", "疗程（天）", "注意事项",
];

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function columnName(columnCount) {
  let value = columnCount;
  let name = "";
  while (value > 0) {
    const remainder = (value - 1) % 26;
    name = String.fromCharCode(65 + remainder) + name;
    value = Math.floor((value - 1) / 26);
  }
  return name || "A";
}

async function savePreview(workbook, sheet, range, fileName) {
  const preview = await workbook.render({ sheetName: sheet.name, range, scale: 1, format: "png" });
  await fs.writeFile(path.join(outputDir, fileName), new Uint8Array(await preview.arrayBuffer()));
}

async function writeRowsInChunks(sheet, startRowIndex, rows, columnCount, label, chunkSize = 1500) {
  for (let offset = 0; offset < rows.length; offset += chunkSize) {
    const chunk = rows.slice(offset, offset + chunkSize);
    sheet.getRangeByIndexes(startRowIndex + offset, 0, chunk.length, columnCount).values = chunk;
    await progress(`${label} values ${offset + 1}-${offset + chunk.length}`);
  }
}

async function formatRowsInChunks(sheet, startRowNumber, rowCount, endColumn, label, rowHeight, chunkSize = 1500) {
  for (let offset = 0; offset < rowCount; offset += chunkSize) {
    const count = Math.min(chunkSize, rowCount - offset);
    const first = startRowNumber + offset;
    const last = first + count - 1;
    const range = sheet.getRange(`A${first}:${endColumn}${last}`);
    range.format = {
      font: { name: "Calibri", size: 11 },
      wrapText: true,
      verticalAlignment: "center",
      borders: { preset: "all", style: "thin", color: "#D9D9D9" },
    };
    range.format.rowHeight = rowHeight;
    await progress(`${label} formats ${first}-${last}`);
  }
}

const payload = earlyPayload;
await progress("payload loaded");
const { patients, records, medicationItems, meta } = payload;
assert(["用药", "器械"].includes(meta.productType), "产品类型仅支持用药或器械");
assert(patients.length === meta.patientCount, "患者数量与元数据不一致");
assert(records.length === patients.length, "生成记录数量与患者数量不一致");

const sourceUserids = patients.map((patient) => patient.userid);
assert(new Set(sourceUserids).size === sourceUserids.length, "源userid存在重复");
assert(JSON.stringify(records.map((record) => record.userid)) === JSON.stringify(sourceUserids), "生成记录userid顺序不一致");
const medicationFirstOccurrenceUserids = [...new Set(medicationItems.map((item) => item.userid))];
assert(JSON.stringify(medicationFirstOccurrenceUserids) === JSON.stringify(sourceUserids), "用药清单userid覆盖或患者顺序不一致");

const patientByUserid = new Map(patients.map((patient) => [patient.userid, patient]));
const recordByUserid = new Map(records.map((record) => [record.userid, record]));
const itemsByUserid = new Map(sourceUserids.map((userid) => [userid, []]));
for (const item of medicationItems) itemsByUserid.get(item.userid)?.push(item);
for (const record of records) {
  assert(JSON.stringify(Object.keys(record)) === JSON.stringify(["userid", "combinedMedication", "prescriptionList", "surgeryName"]), `${record.userid}生成记录字段不符合四键约束`);
  assert(record.combinedMedication.length >= 1 && record.combinedMedication.length <= 5, `${record.userid}联合用药数量不符合1～5项约束`);
  if (meta.productType === "用药") {
    assert(record.combinedMedication[0] === meta.productName, `${record.userid}联合用药首项不是当前产品`);
    assert(record.prescriptionList.includes(meta.productName), `${record.userid}处方清单缺少产品名称`);
    assert(record.surgeryName === "", `${record.userid}药品场景手术名称必须为空`);
  } else {
    assert(record.surgeryName, `${record.userid}器械场景缺少手术名称`);
  }
  const prescriptionEntries = record.prescriptionList.split(" + ");
  assert(prescriptionEntries.length === record.combinedMedication.length, `${record.userid}处方条目数量与联合用药不一致`);
  assert(prescriptionEntries.every((entry, index) => entry.startsWith(record.combinedMedication[index])), `${record.userid}处方顺序与联合用药不一致`);
  const reviewedItems = itemsByUserid.get(record.userid) ?? [];
  assert(JSON.stringify(reviewedItems.map((item) => item.drugName)) === JSON.stringify(record.combinedMedication), `${record.userid}用药清单与联合用药不一致`);
}
for (const item of medicationItems) {
  assert(recordByUserid.get(item.userid)?.combinedMedication.includes(item.drugName), `${item.userid}用药清单出现联合用药外药物`);
  assert(/^每日\d+次$/.test(item.frequency), `${item.userid}用药频次不是中文定量格式`);
  assert(!/(肌肉注射|肌内注射|静脉滴注|静脉注射|皮下注射|口服)/.test(item.medicationTime), `${item.userid}用药时间包含给药途径`);
  assert(Number.isInteger(item.treatmentDays) && item.treatmentDays > 0, `${item.userid}疗程天数不是正整数`);
}
await progress("payload validated");

await fs.mkdir(outputDir, { recursive: true });

const reminderWorkbook = await SpreadsheetFile.importXlsx(await FileBlob.load(reminderTemplatePath));
await progress("reminder template imported");
const reminderSheet = reminderWorkbook.worksheets.getItemAt(0);
assert(JSON.stringify(reminderSheet.getRange("A2:M2").values[0].map((value) => String(value ?? "").trim())) === JSON.stringify(reminderHeaders), "用药提醒模板表头不匹配");
const reminderRows = patients.map((patient, index) => {
  const record = recordByUserid.get(patient.userid);
  return [
    index + 1,
    patient.userid,
    patient.patientName,
    patient.gender,
    patient.age,
    patient.disease,
    patient.allergyHistory,
    record.combinedMedication.join("、"),
    patient.confirmationTime,
    patient.medicationPlan,
    patient.medicationCycle,
    "",
    patient.adverseEvent,
  ];
});
await progress("reminder rows prepared");
const reminderExistingRows = reminderSheet.getUsedRange(true).values.length;
if (reminderExistingRows >= 3) reminderSheet.getRange(`A3:M${reminderExistingRows}`).clear({ applyTo: "contents" });
const titlePrefix = meta.monthLabel ? `${meta.monthLabel}-` : "";
reminderSheet.getRange("A1").values = [[`${titlePrefix}${meta.productName}用药提醒服务明细`]];
reminderSheet.getRangeByIndexes(2, 0, reminderRows.length, reminderHeaders.length).values = reminderRows;
await progress("reminder values written");
const reminderDataRange = reminderSheet.getRange(`A3:M${reminderRows.length + 2}`);
reminderDataRange.format = {
  font: { name: "Calibri", size: 11 },
  wrapText: true,
  verticalAlignment: "center",
  borders: { preset: "all", style: "thin", color: "#D9D9D9" },
};
reminderSheet.getRange(`A3:A${reminderRows.length + 2}`).format.horizontalAlignment = "center";
reminderSheet.getRange(`D3:E${reminderRows.length + 2}`).format.horizontalAlignment = "center";
reminderSheet.getRange(`I3:I${reminderRows.length + 2}`).format.horizontalAlignment = "center";
reminderSheet.getRange(`K3:M${reminderRows.length + 2}`).format.horizontalAlignment = "center";
reminderSheet.getRange(`A3:M${reminderRows.length + 2}`).format.rowHeight = 72;
const reminderWidths = [8, 34, 12, 8, 8, 18, 20, 24, 22, 68, 12, 18, 20];
reminderWidths.forEach((width, index) => reminderSheet.getRange(`${columnName(index + 1)}:${columnName(index + 1)}`).format.columnWidth = width);
for (const table of [...(reminderSheet.tables.items ?? [])]) table.delete();
const reminderTable = reminderSheet.tables.add(`A2:M${reminderRows.length + 2}`, true, "MedicationReminderTable");
reminderTable.style = "TableStyleMedium2";
reminderSheet.freezePanes.freezeRows(2);
reminderSheet.showGridLines = false;
await progress("reminder formatted");
await (await SpreadsheetFile.exportXlsx(reminderWorkbook)).save(reminderOutputPath);
await progress("reminder exported");

const medicationWorkbook = await SpreadsheetFile.importXlsx(await FileBlob.load(medicationTemplatePath));
await progress("medication template imported");
const medicationSheet = medicationWorkbook.worksheets.getItemAt(0);
assert(JSON.stringify(medicationSheet.getRange("A2:J2").values[0].map((value) => String(value ?? "").trim())) === JSON.stringify(medicationHeaders), "用药方案模板表头不匹配");
const medicationRows = medicationItems.map((item, index) => {
  const patient = patientByUserid.get(item.userid);
  return [
    index + 1,
    item.userid,
    patient.patientName,
    item.drugName,
    item.specification,
    item.singleDose,
    item.frequency,
    item.medicationTime,
    item.treatmentDays,
    item.precautions,
  ];
});
await progress("medication rows prepared");
const medicationExistingRows = medicationSheet.getUsedRange(true).values.length;
if (medicationExistingRows >= 3) medicationSheet.getRange(`A3:J${medicationExistingRows}`).clear({ applyTo: "contents" });
medicationSheet.getRange("A1").values = [[`${titlePrefix}${meta.productName}用药方案`]];
await writeRowsInChunks(medicationSheet, 2, medicationRows, medicationHeaders.length, "medication");
await progress("medication values written");
await formatRowsInChunks(medicationSheet, 3, medicationRows.length, "J", "medication", 96);
medicationSheet.getRange(`A3:A${medicationRows.length + 2}`).format.horizontalAlignment = "center";
medicationSheet.getRange(`D3:I${medicationRows.length + 2}`).format.horizontalAlignment = "center";
const medicationWidths = [8, 34, 12, 22, 18, 16, 14, 14, 12, 90];
medicationWidths.forEach((width, index) => medicationSheet.getRange(`${columnName(index + 1)}:${columnName(index + 1)}`).format.columnWidth = width);
medicationSheet.getRange(`I3:I${medicationRows.length + 2}`).format.numberFormat = "0";
for (const table of [...(medicationSheet.tables.items ?? [])]) table.delete();
const medicationTable = medicationSheet.tables.add(`A2:J${medicationRows.length + 2}`, true, "MedicationListTable");
medicationTable.style = "TableStyleMedium2";
medicationSheet.freezePanes.freezeRows(2);
medicationSheet.showGridLines = false;
await progress("medication formatted");
await (await SpreadsheetFile.exportXlsx(medicationWorkbook)).save(medicationOutputPath);
await progress("medication exported");

const reminderLastRow = reminderRows.length + 2;
const medicationLastRow = medicationRows.length + 2;
const reminderMiddle = Math.floor(reminderLastRow / 2);
const medicationMiddle = Math.floor(medicationLastRow / 2);
await savePreview(reminderWorkbook, reminderSheet, "A1:M10", "reminder-first.png");
await savePreview(reminderWorkbook, reminderSheet, `A${reminderMiddle - 3}:M${reminderMiddle + 3}`, "reminder-middle.png");
await savePreview(reminderWorkbook, reminderSheet, `A${reminderLastRow - 6}:M${reminderLastRow}`, "reminder-last.png");
await savePreview(medicationWorkbook, medicationSheet, "A1:J10", "medication-first.png");
await savePreview(medicationWorkbook, medicationSheet, `A${medicationMiddle - 3}:J${medicationMiddle + 3}`, "medication-middle.png");
await savePreview(medicationWorkbook, medicationSheet, `A${medicationLastRow - 6}:J${medicationLastRow}`, "medication-last.png");
await progress("previews saved");

const reminderErrors = await reminderWorkbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100 },
  summary: "reminder formula errors",
});
const medicationErrors = await medicationWorkbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100 },
  summary: "medication formula errors",
});

const qc = {
  status: "passed",
  patientCount: patients.length,
  sourceDistinctUserids: new Set(sourceUserids).size,
  reminderDistinctUserids: new Set(reminderRows.map((row) => row[1])).size,
  medicationDistinctUserids: new Set(medicationRows.map((row) => row[1])).size,
  reminderRows: reminderRows.length,
  medicationRows: medicationRows.length,
  productName: meta.productName,
  surgeryNameValid: meta.productType === "用药" ? records.every((record) => record.surgeryName === "") : records.every((record) => record.surgeryName),
  productIncludedFirst: meta.productType === "用药" ? records.every((record) => record.combinedMedication[0] === meta.productName) : null,
  medicationListMatchesCombinedMedication: records.every((record) => JSON.stringify((itemsByUserid.get(record.userid) ?? []).map((item) => item.drugName)) === JSON.stringify(record.combinedMedication)),
  medicationCountDistribution: Object.fromEntries([...new Set(records.map((record) => record.combinedMedication.length))].sort().map((count) => [count, records.filter((record) => record.combinedMedication.length === count).length])),
  chineseFrequency: medicationItems.every((item) => /^每日\d+次$/.test(item.frequency)),
  timingOnly: medicationItems.every((item) => !/(肌肉注射|肌内注射|静脉滴注|静脉注射|皮下注射|口服)/.test(item.medicationTime)),
  integerTreatmentDays: medicationItems.every((item) => Number.isInteger(item.treatmentDays)),
  reminderFormulaErrors: reminderErrors.ndjson,
  medicationFormulaErrors: medicationErrors.ndjson,
  outputs: { reminderOutputPath, medicationOutputPath },
};
await fs.writeFile(path.join(outputDir, "qc.json"), JSON.stringify(qc, null, 2), "utf8");
await progress("qc saved");
console.log(JSON.stringify(qc));
