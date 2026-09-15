import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const script = fileURLToPath(new URL('../scripts/parse_report_request.mjs', import.meta.url));
const work = fs.mkdtempSync(path.join(os.tmpdir(), 'report-request-'));
try {
  for (const method of ['电话随访', '深度访谈']) {
    const input = path.join(work, `${method}.txt`);
    const output = path.join(work, `${method}.json`);
    fs.writeFileSync(input, `生成患者调研访谈
调研时间：2026年9月
调研数量：2人
调研方式=${method}
依据以下文件：
/a/patients.xlsx
/a/plans.xlsx
/a/tracking.xlsx
/a/followups.xlsx
/a/symptoms.xlsx
/a/ae.xlsx`);
    const result = spawnSync(process.execPath, [script, '--input', input, '--output', output], { encoding: 'utf8' });
    assert.equal(result.status, 0, result.stderr);
    const request = JSON.parse(fs.readFileSync(output, 'utf8'));
    assert.equal(request.workflow, 'interview');
    assert.equal(request.count, 2);
    assert.equal(request.includeMild, false);
    assert.deepEqual(request.outputKinds, method === '电话随访' ? ['records'] : ['analysis', 'records']);
    const original = fs.readFileSync(output);
    const overwrite = spawnSync(process.execPath, [script, '--input', input, '--output', output], { encoding: 'utf8' });
    assert.notEqual(overwrite.status, 0);
    assert.deepEqual(fs.readFileSync(output), original);
  }
} finally {
  fs.rmSync(work, { recursive: true, force: true });
}
console.log('Report CLI routing and output protection passed');
