import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath, pathToFileURL } from "node:url";
import { spawnSync } from "node:child_process";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));

export function runPortableWorkbook(operation, request) {
  const commands = process.env.PYTHON_BINARY
    ? [[process.env.PYTHON_BINARY]]
    : process.platform === "win32" ? [["py", "-3"], ["python"], ["python3"]] : [["python3"], ["python"]];
  for (const [binary, ...prefix] of commands) {
    const result = spawnSync(binary, [...prefix, path.join(scriptDir, "portable_workbook.py"), operation], {
      input: JSON.stringify(request), encoding: "utf8", maxBuffer: 128 * 1024 * 1024,
      env: { ...process.env, PYTHONIOENCODING: "utf-8" }, windowsHide: true,
    });
    if (result.error?.code === "ENOENT") continue;
    if (result.error) throw result.error;
    if (result.status !== 0) throw new Error(result.stderr || `Python workbook backend exited ${result.status}`);
    return JSON.parse(result.stdout);
  }
  throw new Error("未找到Python 3；安装Python并设置PYTHON_BINARY为解释器绝对路径。");
}

// A read-only snapshot lets both backends use exactly the same JS validators.
function portableSnapshot(snapshot) {
  const items = snapshot.sheets.map(sheet => ({
    name: sheet.name,
    getUsedRange: () => ({ values: sheet.values }),
    tables: { items: sheet.tables },
  }));
  return {
    worksheets: { items, getItemAt: index => items[index] },
    inspect: async request => {
      if (request.kind === "match") {
        const regex = new RegExp(request.searchTerm);
        const matches = snapshot.sheets.flatMap(sheet => sheet.values.flat()
          .filter(value => typeof value === "string" && regex.test(value)));
        const formulas = snapshot.sheets.flatMap(sheet => sheet.formulas);
        return { ndjson: `matched ${matches.length + formulas.length} entries` };
      }
      const sheet = snapshot.sheets.find(item => item.name === request.sheetId) ?? snapshot.sheets[0];
      const rows = [...request.range.matchAll(/\d+/g)].map(match => Number(match[0]));
      return { ndjson: JSON.stringify({ sheet: sheet.name, range: request.range,
        values: sheet.values.slice(rows[0] - 1, rows[1]) }).slice(0, request.maxChars ?? 6000) };
    },
  };
}

export async function loadWorkbookTools() {
  const requested = process.env.WORKBOOK_BACKEND ?? "auto";
  if (!["auto", "artifact", "portable"].includes(requested)) throw new Error("WORKBOOK_BACKEND必须为auto、artifact或portable");
  if (requested !== "portable") {
    let resolved;
    const anchors = [
      ...(process.env.CODEX_NODE_MODULES ? [path.join(process.env.CODEX_NODE_MODULES, "package.json")] : []),
      import.meta.url,
    ];
    for (const anchor of anchors) {
      try {
        resolved = createRequire(anchor).resolve("@oai/artifact-tool");
        break;
      } catch (error) {
        if (error.code !== "MODULE_NOT_FOUND") throw error;
      }
    }
    if (resolved) return { ...await import(pathToFileURL(resolved).href), backend: "artifact" };
    if (requested === "artifact") throw new Error("未找到@oai/artifact-tool；配置CODEX_NODE_MODULES或使用WORKBOOK_BACKEND=portable。");
  }
  return {
    backend: "portable",
    FileBlob: { load: async filePath => filePath },
    SpreadsheetFile: {
      importXlsx: async filePath => portableSnapshot(runPortableWorkbook("read", { path: filePath })),
    },
  };
}
