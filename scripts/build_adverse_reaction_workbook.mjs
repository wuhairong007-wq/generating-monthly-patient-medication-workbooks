import fs from "node:fs/promises";
import path from "node:path";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";

const nodeModules = process.env.CODEX_NODE_MODULES;
if (!nodeModules) throw new Error("CODEX_NODE_MODULES is required");
const runtimeRequire = createRequire(path.join(nodeModules, "package.json"));
const artifactToolPath = runtimeRequire.resolve("@oai/artifact-tool");
const { FileBlob, SpreadsheetFile } = await import(pathToFileURL(artifactToolPath).href);

const HEADERS = [
  "序号", "患者ID", "疾病", "不良反应发生时间", "不良反应症状描述",
  "不良反应严重程度分级", "与用药关系分析", "处理措施", "处理结果/转归",
  "是否触发人工干预", "备注",
];
const REQUIRED_FIELDS = [
  "userid", "symptomDescription", "severityGrade", "treatmentMeasures", "treatmentOutcome", "remark",
];
const SEVERITY_GRADES = new Set(["轻度", "中度", "重度"]);

function parseArgs(argv) {
  const result = {};
  for (let index = 0; index < argv.length; index += 2) {
    if (!argv[index]?.startsWith("--") || argv[index + 1] === undefined) throw new Error(`参数错误：${argv[index] ?? ""}`);
    result[argv[index].slice(2)] = argv[index + 1];
  }
  return result;
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function parseDateTime(value, label = "日期时间") {
  const normalized = String(value).replace(" ", "T");
  assert(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/.test(normalized), `${label}无效：${value}`);
  const parsed = new Date(normalized + "+08:00");
  assert(!Number.isNaN(parsed.getTime()), `${label}无效：${value}`);
  assert(new Date(parsed.getTime() + 8 * 3600000).toISOString().slice(0, 19) === normalized, `${label}无效：${value}`);
  return parsed;
}

function parseServicePeriod(period) {
  assert(/^\d{4}-\d{2}-\d{2}$/.test(period?.start) && /^\d{4}-\d{2}-\d{2}$/.test(period?.end), "服务周期缺失或格式无效，必须为YYYY-MM-DD");
  const start = parseDateTime(`${period.start} 00:00:00`, "服务周期开始日期");
  const end = parseDateTime(`${period.end} 23:59:59`, "服务周期结束日期");
  assert(start <= end, "服务周期开始日期不得晚于结束日期");
  return { start, end };
}

function isWithinDailyOccurrenceWindow(value) {
  const hours = (value.getUTCHours() + 8) % 24;
  const minutes = value.getUTCMinutes();
  const seconds = value.getUTCSeconds();
  const total = hours * 3600 + minutes * 60 + seconds;
  return total >= 7 * 3600 + 30 * 60 && total <= 21 * 3600 + 59 * 60 + 59;
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

async function writeRowsInChunks(sheet, rows, chunkSize = 1000) {
  for (let offset = 0; offset < rows.length; offset += chunkSize) {
    const chunk = rows.slice(offset, offset + chunkSize);
    sheet.getRangeByIndexes(2 + offset, 0, chunk.length, HEADERS.length).values = chunk;
  }
}

async function savePreview(workbook, sheet, firstRow, lastRow, outputPath) {
  const safeFirst = Math.max(1, firstRow);
  const safeLast = Math.max(safeFirst, lastRow);
  const preview = await workbook.render({
    sheetName: sheet.name,
    range: `A${safeFirst}:K${safeLast}`,
    scale: 1,
    format: "png",
  });
  await fs.writeFile(outputPath, new Uint8Array(await preview.arrayBuffer()));
}

const args = parseArgs(process.argv.slice(2));
for (const key of ["payload", "template", "output", "preview-dir"]) {
  if (!args[key]) throw new Error(`缺少--${key}`);
}
const payloadPath = path.resolve(args.payload);
const templatePath = path.resolve(args.template);
const outputPath = path.resolve(args.output);
const previewDir = path.resolve(args["preview-dir"]);
const payload = JSON.parse(await fs.readFile(payloadPath, "utf8"));
const sourcePatients = payload.sourcePatients ?? [];
const records = payload.records ?? [];
const productName = String(payload.meta?.productName ?? "").trim();
const servicePeriod = parseServicePeriod(payload.meta?.servicePeriod);

assert(records.length > 0, "不良反应记录为空");
assert(productName, "产品名称不能为空");
assert(records.length === sourcePatients.length, "记录数量与筛选患者数量不一致");
assert(payload.meta?.targetPatientCount === records.length, "记录数量与元数据不一致");
const expectedUserids = sourcePatients.map((patient) => patient.userid);
const recordUserids = records.map((record) => record.userid);
assert(new Set(expectedUserids).size === expectedUserids.length, "筛选患者userid存在重复");
assert(JSON.stringify(recordUserids) === JSON.stringify(expectedUserids), "记录userid集合或顺序不一致");

const patientByUserid = new Map(sourcePatients.map((patient) => [patient.userid, patient]));
for (const record of records) {
  for (const field of REQUIRED_FIELDS) assert(String(record[field] ?? "").trim(), `${record.userid}缺少必填字段${field}`);
  assert(String(record.symptomDescription).includes(productName), `${record.userid}症状描述缺少产品名称`);
  assert(String(record.medicationRelationship).includes(productName), `${record.userid}关系分析缺少产品名称`);
  assert(!String(record.symptomDescription).includes("结构化草案："), `${record.userid}症状描述包含旧草案前缀`);
  assert(!String(record.remark).includes("人工审核草案："), `${record.userid}备注包含旧草案前缀`);
  assert(!String(record.symptomDescription).includes("草案"), `${record.userid}症状描述包含草案标签`);
  assert(!String(record.remark).includes("草案"), `${record.userid}备注包含草案标签`);
  assert(SEVERITY_GRADES.has(record.severityGrade), `${record.userid}严重程度不符合枚举`);
  assert(
    (record.severityGrade === "重度" && record.manualIntervention === "是")
      || (record.severityGrade === "中度" && record.manualIntervention === "否")
      || (record.severityGrade === "轻度" && record.manualIntervention === "否"),
    `${record.userid}严重程度与人工干预映射错误`,
  );
  const patient = patientByUserid.get(record.userid);
  assert(patient, `${record.userid}缺少源患者`);
  const occurrence = parseDateTime(record.occurrenceTime);
  assert(occurrence > parseDateTime(patient.activateTime, `${record.userid}激活时间`), `${record.userid}发生时间未晚于激活时间`);
  assert(occurrence >= servicePeriod.start && occurrence <= servicePeriod.end, `${record.userid}发生时间不在服务周期内`);
  assert(isWithinDailyOccurrenceWindow(occurrence), `${record.userid}发生时间不在每日07:30至21:59:59窗口内`);
}

const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(templatePath));
const sheet = workbook.worksheets.getItemAt(0);
const templateHeaders = sheet.getRange("A2:K2").values[0].map((value) => String(value ?? "").trim());
assert(JSON.stringify(templateHeaders) === JSON.stringify(HEADERS), "不良反应模板表头不匹配");

const existingRows = sheet.getUsedRange(true).values.length;
if (existingRows >= 3) sheet.getRange(`A3:K${existingRows}`).clear({ applyTo: "contents" });
for (const table of [...(sheet.tables.items ?? [])]) table.delete();

const rows = records.map((record, index) => [
  index + 1,
  record.userid,
  record.disease,
  record.occurrenceTime,
  record.symptomDescription,
  record.severityGrade,
  record.medicationRelationship,
  record.treatmentMeasures,
  record.treatmentOutcome,
  record.manualIntervention,
  record.remark,
]);
await writeRowsInChunks(sheet, rows);

const lastRow = rows.length + 2;
sheet.getRange("A1").values = [["不良反应（AE）记录清单"]];
const dataRange = sheet.getRange(`A3:K${lastRow}`);
dataRange.format = {
  font: { name: "Calibri", size: 11 },
  wrapText: true,
  verticalAlignment: "center",
  borders: { preset: "all", style: "thin", color: "#D9D9D9" },
};
dataRange.format.rowHeight = 96;
sheet.getRange(`A3:D${lastRow}`).format.horizontalAlignment = "center";
sheet.getRange(`F3:F${lastRow}`).format.horizontalAlignment = "center";
sheet.getRange(`J3:J${lastRow}`).format.horizontalAlignment = "center";
sheet.getRange(`D3:D${lastRow}`).format.numberFormat = "@";

const widths = [8, 34, 22, 22, 52, 20, 62, 64, 42, 18, 64];
widths.forEach((width, index) => {
  sheet.getRange(`${columnName(index + 1)}:${columnName(index + 1)}`).format.columnWidth = width;
});
const table = sheet.tables.add(`A2:K${lastRow}`, true, "AdverseReactionDraftTable");
table.style = "TableStyleMedium2";
sheet.freezePanes.freezeRows(2);
sheet.showGridLines = false;

await fs.mkdir(path.dirname(outputPath), { recursive: true });
await fs.mkdir(previewDir, { recursive: true });
await (await SpreadsheetFile.exportXlsx(workbook)).save(outputPath);

const middleRow = Math.max(3, Math.floor((3 + lastRow) / 2));
await savePreview(workbook, sheet, 1, Math.min(lastRow, 8), path.join(previewDir, "adverse-first.png"));
await savePreview(workbook, sheet, middleRow - 3, Math.min(lastRow, middleRow + 3), path.join(previewDir, "adverse-middle.png"));
await savePreview(workbook, sheet, Math.max(1, lastRow - 6), lastRow, path.join(previewDir, "adverse-last.png"));

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100 },
  summary: "adverse reaction formula errors",
});
console.log(JSON.stringify({
  status: "passed",
  rowCount: rows.length,
  distinctUseridCount: new Set(recordUserids).size,
  outputPath,
  formulaErrors: errors.ndjson,
}));
