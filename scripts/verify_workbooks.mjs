import fs from "node:fs/promises";
import path from "node:path";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";

import {
  validateMedicationMinimums,
  validateMedicationPlanFields,
} from "./validate_medication_payload.mjs";
import { validateReminderConfirmation } from "./validate_confirmation_time.mjs";

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
for (const key of ["payload", "reminder", "medication", "report"]) {
  if (!args[key]) throw new Error(`缺少--${key}`);
}
const payload = JSON.parse(await fs.readFile(path.resolve(args.payload), "utf8"));
validateMedicationMinimums(payload);
validateMedicationPlanFields(payload);
const patientCount = payload.patients.length;
const expectedUserids = payload.patients.map((patient) => patient.userid);
const expectedProduct = payload.meta.productName;
const reminderPath = path.resolve(args.reminder);
const medicationPath = path.resolve(args.medication);
const reportPath = path.resolve(args.report);

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

const reminderWorkbook = await SpreadsheetFile.importXlsx(await FileBlob.load(reminderPath));
const reminderSheet = reminderWorkbook.worksheets.getItemAt(0);
const reminderValues = reminderSheet.getUsedRange(true).values;
assert(reminderValues.length === patientCount + 2, `用药提醒行数错误：${reminderValues.length}`);
const reminderRows = reminderValues.slice(2);
const reminderUserids = reminderRows.map((row) => String(row[1] ?? ""));
assert(JSON.stringify(reminderUserids) === JSON.stringify(expectedUserids), "用药提醒userid集合或顺序与源数据不一致");
assert(reminderRows.every((row, index) => row[7] === payload.records[index].combinedMedication.join("、")), "用药提醒联合用药与生成记录不一致");
assert(reminderRows.every((row, index) => row[9] === payload.patients[index].medicationPlan), "用药提醒用药方案与生成记录不一致");
if (payload.meta.productType === "用药") {
  assert(reminderRows.every((row) => String(row[7]).split("、")[0] === expectedProduct), "用药提醒联合用药首项缺少当前产品");
  assert(payload.records.every((record) => record.surgeryName === ""), "用药场景surgeryName必须为空");
} else {
  assert(payload.records.every((record) => record.surgeryName), "器械场景surgeryName不能为空");
}
assert(reminderSheet.tables.items.length === 1, "用药提醒必须且只能包含一个表格对象");
for (let index = 0; index < reminderRows.length; index += 1) {
  const patient = payload.patients[index];
  validateReminderConfirmation({
    patient,
    reminderValue: reminderRows[index][8],
    inputFormat: payload.meta.inputFormat,
  });
}

const medicationWorkbook = await SpreadsheetFile.importXlsx(await FileBlob.load(medicationPath));
const medicationSheet = medicationWorkbook.worksheets.getItemAt(0);
const medicationValues = medicationSheet.getUsedRange(true).values;
assert(medicationValues.length === payload.medicationItems.length + 2, `用药方案行数错误：${medicationValues.length}`);
const medicationRows = medicationValues.slice(2);
const medicationUserids = medicationRows.map((row) => String(row[1] ?? ""));
assert(JSON.stringify([...new Set(medicationUserids)]) === JSON.stringify(expectedUserids), "用药方案userid覆盖或患者顺序与源数据不一致");
assert(medicationRows.every((row, index) => row[3] === payload.medicationItems[index].drugName), "用药方案药物与联合用药顺序不一致");
if (payload.meta.productType === "用药") {
  assert(expectedUserids.every((userid) => medicationRows.some((row) => row[1] === userid && row[3] === expectedProduct)), "用药方案有患者缺少当前产品");
}
assert(medicationRows.every((row) => /^每日\d+次$/.test(String(row[6]))), "用药方案频次不是中文定量格式");
assert(medicationRows.every((row) => !/(肌肉注射|肌内注射|静脉滴注|静脉注射|皮下注射|口服)/.test(String(row[7]))), "用药时间包含给药途径");
assert(medicationRows.every((row) => Number.isInteger(row[8]) && row[8] > 0), "疗程天数存在非正整数");
assert(medicationSheet.tables.items.length === 1, "用药方案必须且只能包含一个表格对象");

const reminderFirst = await reminderWorkbook.inspect({ kind: "region", sheetId: reminderSheet.name, range: "A1:M6", maxChars: 5000 });
const reminderMiddle = await reminderWorkbook.inspect({ kind: "region", sheetId: reminderSheet.name, range: `A${Math.floor(patientCount / 2)}:M${Math.floor(patientCount / 2) + 3}`, maxChars: 5000 });
const reminderLast = await reminderWorkbook.inspect({ kind: "region", sheetId: reminderSheet.name, range: `A${patientCount}:M${patientCount + 2}`, maxChars: 5000 });
const medicationFirst = await medicationWorkbook.inspect({ kind: "region", sheetId: medicationSheet.name, range: "A1:J6", maxChars: 5000 });
const medicationMiddleRow = Math.floor(medicationRows.length / 2);
const medicationLastRow = medicationRows.length + 2;
const medicationMiddle = await medicationWorkbook.inspect({ kind: "region", sheetId: medicationSheet.name, range: `A${medicationMiddleRow}:J${medicationMiddleRow + 3}`, maxChars: 5000 });
const medicationLast = await medicationWorkbook.inspect({ kind: "region", sheetId: medicationSheet.name, range: `A${medicationLastRow - 2}:J${medicationLastRow}`, maxChars: 5000 });
const reminderErrors = await reminderWorkbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A", options: { useRegex: true, maxResults: 100 }, summary: "final reminder formula error scan" });
const medicationErrors = await medicationWorkbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A", options: { useRegex: true, maxResults: 100 }, summary: "final medication formula error scan" });
assert(reminderErrors.ndjson.includes("matched 0 entries"), "用药提醒存在公式错误");
assert(medicationErrors.ndjson.includes("matched 0 entries"), "用药方案存在公式错误");

const verification = {
  status: "passed",
  patientCount,
  reminderRows: reminderRows.length,
  medicationRows: medicationRows.length,
  distinctSourceUserids: new Set(expectedUserids).size,
  distinctReminderUserids: new Set(reminderUserids).size,
  distinctMedicationUserids: new Set(medicationUserids).size,
  exactUseridOrderMatch: true,
  medicationMappingMatch: true,
  medicationCountDistribution: Object.fromEntries([...new Set(payload.records.map((record) => record.combinedMedication.length))].sort().map((count) => [count, payload.records.filter((record) => record.combinedMedication.length === count).length])),
  uniqueMedicationPlanCount: new Set(payload.patients.map((patient) => patient.medicationPlan)).size,
  minimumUniqueMedicationPlanCount: payload.meta.minimumUniqueMedicationPlanCount,
  surgeryNamesValid: payload.meta.productType === "用药" ? payload.records.every((record) => record.surgeryName === "") : payload.records.every((record) => record.surgeryName),
  chineseFrequencies: true,
  medicationTimesContainOnlyTiming: true,
  integerTreatmentDays: true,
  confirmationTimesValid: true,
  tableObjects: { reminder: reminderSheet.tables.items.length, medication: medicationSheet.tables.items.length },
  formulaErrors: { reminder: reminderErrors.ndjson, medication: medicationErrors.ndjson },
  inspectedRanges: {
    reminderFirst: reminderFirst.ndjson,
    reminderMiddle: reminderMiddle.ndjson,
    reminderLast: reminderLast.ndjson,
    medicationFirst: medicationFirst.ndjson,
    medicationMiddle: medicationMiddle.ndjson,
    medicationLast: medicationLast.ndjson,
  },
};
await fs.mkdir(path.dirname(reportPath), { recursive: true });
await fs.writeFile(reportPath, JSON.stringify(verification, null, 2), "utf8");
console.log(JSON.stringify({
  status: verification.status,
  patientCount,
  reminderRows: reminderRows.length,
  medicationRows: medicationRows.length,
  distinctReminderUserids: verification.distinctReminderUserids,
  distinctMedicationUserids: verification.distinctMedicationUserids,
  formulaErrors: verification.formulaErrors,
}));
