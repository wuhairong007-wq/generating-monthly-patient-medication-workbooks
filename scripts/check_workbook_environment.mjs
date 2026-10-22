import { loadWorkbookTools, runPortableWorkbook } from "./workbook_runtime.mjs";

try {
  if (Number(process.versions.node.split(".")[0]) < 20) throw new Error("需要Node.js 20或更高版本。");
  const { backend } = await loadWorkbookTools();
  const python = runPortableWorkbook("check", { preview: backend === "portable" });
  console.log(JSON.stringify({ ready: true, backend, node: process.versions.node, ...python }));
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
}
