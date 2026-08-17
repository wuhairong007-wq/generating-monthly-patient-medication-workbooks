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
  "序号", "患者ID", "疾病", "不良反应发生时间", "发现途径", "不良反应症状描述",
  "不良反应严重程度分级", "与用药关系分析", "处理措施", "处理结果/转归",
  "是否触发人工干预", "关联随访记录", "备注",
];
const DISCOVERY_METHODS = new Set(["AI用药随访发现", "患者自评反馈"]);

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

function parseDateTime(value) {
  const parsed = new Date(String(value).replace(" ", "T") + "+08:00");
  assert(!Number.isNaN(parsed.getTime()), `日期时间无效：${value}`);
  return parsed;
}

const args = parseArgs(process.argv.slice(2));
for (const key of ["payload", "workbook", "report"]) {
  if (!args[key]) throw new Error(`缺少--${key}`);
}
const payload = JSON.parse(await fs.readFile(path.resolve(args.payload), "utf8"));
const workbookPath = path.resolve(args.workbook);
const reportPath = path.resolve(args.report);
const records = payload.records ?? [];
const sourcePatients = payload.sourcePatients ?? [];
const productName = String(payload.meta?.productName ?? "").trim();
const expectedUserids = records.map((record) => record.userid);
const patientByUserid = new Map(sourcePatients.map((patient) => [patient.userid, patient]));

const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(workbookPath));
const sheet = workbook.worksheets.getItemAt(0);
const values = sheet.getUsedRange(true).values;
assert(productName, "产品名称不能为空");
assert(String(values[0]?.[0] ?? "") === "不良反应（AE）记录清单", "不良反应清单标题不符合要求");
assert(values.length === records.length + 2, `不良反应清单行数错误：${values.length}`);
const headers = values[1].map((value) => String(value ?? "").trim());
assert(JSON.stringify(headers) === JSON.stringify(HEADERS), "不良反应清单表头不匹配");
const rows = values.slice(2);
const actualUserids = rows.map((row) => String(row[1] ?? ""));
assert(JSON.stringify(actualUserids) === JSON.stringify(expectedUserids), "userid集合或顺序与payload不一致");
assert(new Set(actualUserids).size === actualUserids.length, "不良反应清单userid存在重复");

for (let index = 0; index < rows.length; index += 1) {
  const row = rows[index];
  const record = records[index];
  const patient = patientByUserid.get(record.userid);
  assert(Number(row[0]) === index + 1, `${record.userid}序号错误`);
  assert(String(row[2] ?? "") === record.disease, `${record.userid}疾病不一致`);
  assert(DISCOVERY_METHODS.has(String(row[4] ?? "")), `${record.userid}发现途径不符合枚举`);
  assert(["中度（2级）", "重度（3级）"].includes(String(row[6] ?? "")), `${record.userid}严重程度不符合枚举`);
  assert(
    (row[6] === "重度（3级）" && row[10] === "是") || (row[6] === "中度（2级）" && row[10] === "否"),
    `${record.userid}严重程度与人工干预映射错误`,
  );
  assert(String(row[11] ?? "") === "", `${record.userid}关联随访记录应为空`);
  assert(patient, `${record.userid}缺少源患者`);
  assert(parseDateTime(row[3]) < parseDateTime(patient.activateTime), `${record.userid}发生时间未早于激活时间`);
  assert(String(row[5] ?? "") === record.symptomDescription, `${record.userid}症状描述与payload不一致`);
  assert(String(row[7] ?? "") === record.medicationRelationship, `${record.userid}关系分析与payload不一致`);
  assert(String(row[8] ?? "") === record.treatmentMeasures, `${record.userid}处理措施与payload不一致`);
  assert(String(row[9] ?? "") === record.treatmentOutcome, `${record.userid}转归与payload不一致`);
  assert(String(row[12] ?? "") === record.remark, `${record.userid}备注与payload不一致`);
  assert(String(row[5] ?? "").includes(productName), `${record.userid}症状描述缺少产品名称`);
  assert(String(row[7] ?? "").includes(productName), `${record.userid}关系分析缺少产品名称`);
  assert(!String(row[5] ?? "").includes("草案"), `${record.userid}症状描述包含草案标签`);
  assert(!String(row[12] ?? "").includes("草案"), `${record.userid}备注包含草案标签`);
}
assert(sheet.tables.items.length === 1, "不良反应清单必须且只能包含一个表格对象");

const first = await workbook.inspect({ kind: "region", sheetId: sheet.name, range: `A1:M${Math.min(rows.length + 2, 7)}`, maxChars: 6000 });
const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100 },
  summary: "final adverse reaction formula error scan",
});
assert(errors.ndjson.includes("matched 0 entries"), "不良反应清单存在公式错误");

const report = {
  status: "passed",
  rowCount: rows.length,
  distinctUseridCount: new Set(actualUserids).size,
  exactUseridOrderMatch: true,
  validDiscoveryMethods: true,
  validSeverityAndInterventionMapping: true,
  occurrenceTimesPrecedeActivation: true,
  blankFollowupRecords: true,
  productName,
  productAwareContent: true,
  noDraftPrefixes: true,
  tableObjects: sheet.tables.items.length,
  formulaErrors: "matched 0 entries",
  inspectedFirstRange: first.ndjson,
};
await fs.mkdir(path.dirname(reportPath), { recursive: true });
await fs.writeFile(reportPath, JSON.stringify(report, null, 2), "utf8");
console.log(JSON.stringify({
  status: report.status,
  rowCount: report.rowCount,
  distinctUseridCount: report.distinctUseridCount,
  exactUseridOrderMatch: report.exactUseridOrderMatch,
  formulaErrors: report.formulaErrors,
}));
