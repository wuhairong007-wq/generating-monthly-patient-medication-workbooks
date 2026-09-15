import assert from 'node:assert/strict';
import { parseDeepInterviewRequest } from '../scripts/insight_request_parser.mjs';
const base = `生成深度访谈
调研时间：2026年6月
调研数量：10人
依据以下文件：
/a/patients.xlsx
/a/plans.xlsx
/a/tracking.xlsx
/a/followups.xlsx
/a/symptoms.xlsx
/a/ae.xlsx
输出文件模板：
/a/report.docx
/a/details.docx`;
assert.equal(parseDeepInterviewRequest(base).includeMild, false);
assert.equal(parseDeepInterviewRequest(base.replace('依据以下文件：', '是否轻度：是\n依据以下文件：')).includeMild, true);
assert.equal(parseDeepInterviewRequest(base.replace('依据以下文件：', '是否轻度：否\n依据以下文件：')).includeMild, false);
assert.equal(parseDeepInterviewRequest(base).count, 10);
assert.equal(parseDeepInterviewRequest(base).templatePaths.length, 2);
for (const value of ['', 'true', '轻度', 'yes']) {
  assert.throws(() => parseDeepInterviewRequest(base.replace('依据以下文件：', `是否轻度：${value}\n依据以下文件：`)), /是否轻度只能/);
}
const withMethod = (value, separator = '=') => base.replace('依据以下文件：', `调研方式${separator}${value}\n依据以下文件：`);
const defaultRequest = parseDeepInterviewRequest(base);
assert.equal(defaultRequest.researchMethod, '深度访谈');
assert.deepEqual(defaultRequest.outputKinds, ['analysis', 'records']);
for (const separator of ['=', '：', ':']) {
  const phone = parseDeepInterviewRequest(withMethod('电话随访', separator));
  assert.equal(phone.researchMethod, '电话随访');
  assert.deepEqual(phone.outputKinds, ['records']);
  assert.equal(phone.templatePaths.length, 2); // Existing paired templates remain valid input.
  const deep = parseDeepInterviewRequest(withMethod('深度访谈', separator));
  assert.equal(deep.researchMethod, '深度访谈');
  assert.deepEqual(deep.outputKinds, ['analysis', 'records']);
}
assert.equal(parseDeepInterviewRequest(withMethod(' 电话随访 ', ' = ')).researchMethod, '电话随访');
const noTemplates = withMethod('电话随访').split('输出文件模板：')[0];
assert.deepEqual(parseDeepInterviewRequest(noTemplates).templatePaths, []);
assert.deepEqual(parseDeepInterviewRequest(`${noTemplates}输出文件模板：\n/a/details.docx`).templatePaths, ['/a/details.docx']);
assert.throws(() => parseDeepInterviewRequest(`${noTemplates}输出文件模板：\n/a/details.pdf`), /输出文件模板/);
assert.throws(() => parseDeepInterviewRequest(`${noTemplates}输出文件模板：\n/a/1.docx\n/a/2.docx\n/a/3.docx`), /输出文件模板/);
assert.throws(() => parseDeepInterviewRequest(base.replace('/a/report.docx\n', '')), /输出文件模板/);
for (const value of ['', '线上随访', '电话随访 | 深度访谈', 'phone']) {
  assert.throws(() => parseDeepInterviewRequest(withMethod(value)), /调研方式只能/);
}
assert.throws(() => parseDeepInterviewRequest(withMethod('电话随访\n调研方式：深度访谈')), /调研方式.*重复/);
console.log('Deep interview severity, research method and deliverable routing tests passed');

assert.deepEqual(parseDeepInterviewRequest(base.replace('生成深度访谈', '生成患者调研访谈')), parseDeepInterviewRequest(base));

assert.equal(defaultRequest.dialogueMode, 'simulated');
assert.equal(defaultRequest.simulationAuthorized, true);
for (const [label, mode] of [['真实访谈','actual'],['访谈提纲','outline']]) {
  const request = parseDeepInterviewRequest(base.replace('依据以下文件：', `内容模式：${label}\n依据以下文件：`));
  assert.equal(request.dialogueMode, mode);
  assert.equal(request.simulationAuthorized, false);
}
assert.throws(() => parseDeepInterviewRequest(base.replace('依据以下文件：', '内容模式：错误\n依据以下文件：')), /内容模式/);
const escapedMonthly = String.raw`生成深度访谈\
调研时间：2026年4月\
调研数量：10人
依据以下文件：
/a/月度患者清单\\\_4月\\.xlsx\
/a/患者随访\_4月\.xlsx\
/a/症状自评\_4月\.xlsx\
/a/用药提醒\_4月\.xlsx\
/a/不良反应清单\_4月\.xlsx`;
const monthly = parseDeepInterviewRequest(escapedMonthly);
assert.equal(monthly.researchTime, '2026年4月');
assert.equal(monthly.simulationAuthorized, true);
assert.equal(monthly.sourcePaths.length, 5);
assert.equal(monthly.sourcePaths[0], '/a/月度患者清单_4月.xlsx');
