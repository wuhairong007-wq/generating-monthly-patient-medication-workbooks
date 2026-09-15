import assert from 'node:assert/strict';
import { parseInsightRequest } from '../scripts/insight_request_parser.mjs';

const prompt = `生成洞察报告
产品：注射用胰蛋白酶
服务周期：2026-07-01 至 2026-07-31
依据以下文件：
患者全病程数据.xlsx
健康管理方案.xlsx
跟踪提醒.xlsx
智能随访明细.xlsx
症状自评明细.xlsx
用药清单.xlsx
不良反应清单.xlsx
输出Word文件模板：06-患者洞察报告.docx`;

const request = parseInsightRequest(prompt);
assert.equal(request.product, '注射用胰蛋白酶');
assert.deepEqual(request.period, { start: '2026-07-01', end: '2026-07-31' });
assert.equal(request.sourcePaths.length, 7);
assert.equal(request.templatePath, '06-患者洞察报告.docx');
assert.equal(request.client, null);
assert.equal(request.provider, null);

const coverPrompt = `生成洞察报告
委托方：山东利赛医药有限公司
服务商：福建健康之路健康科技有限公司
产品：注射用胰蛋白酶
服务周期：2026-07-01 至 2026-07-31
依据以下文件：
患者全病程数据.xlsx
健康管理方案.xlsx
跟踪提醒.xlsx
智能随访明细.xlsx
症状自评明细.xlsx
用药清单.xlsx
不良反应清单.xlsx`;
const coverRequest = parseInsightRequest(coverPrompt);
assert.equal(coverRequest.client, '山东利赛医药有限公司');
assert.equal(coverRequest.provider, '福建健康之路健康科技有限公司');

const noTemplatePrompt = `生成洞察报告
产品：注射用胰蛋白酶
服务周期： 2026-07-01 至 2026-07-31
依据以下文件：
/绝对路径/患者主表.xlsx
/绝对路径/健康管理方案.xlsx
/绝对路径/跟踪提醒.xlsx
/绝对路径/智能随访.xlsx
/绝对路径/症状自评.xlsx
/绝对路径/用药清单.xlsx
/绝对路径/不良反应清单.xlsx`;
const noTemplateRequest = parseInsightRequest(noTemplatePrompt);
assert.equal(noTemplateRequest.templatePath, null);
assert.deepEqual(noTemplateRequest.period, { start: '2026-07-01', end: '2026-07-31' });

assert.throws(() => parseInsightRequest(prompt.replace('产品：注射用胰蛋白酶', '产品：')), /产品/);
assert.throws(() => parseInsightRequest(prompt.replace('2026-07-01 至 2026-07-31', '2026-07-31 至 2026-07-01')), /服务周期/);
assert.equal(parseInsightRequest(prompt.replace('不良反应清单.xlsx\n', '')).sourcePaths.length, 6);
assert.throws(() => parseInsightRequest(prompt.replace('不良反应清单.xlsx\n', '').replace('用药清单.xlsx\n', '').replace('健康管理方案.xlsx\n', '').replace('跟踪提醒.xlsx\n', '')), /4/);
assert.throws(() => parseInsightRequest(prompt.replace('不良反应清单.xlsx', '不良反应清单.xlsx\n额外.xlsx')), /7/);
assert.throws(() => parseInsightRequest(prompt.replace('患者全病程数据.xlsx', '重复.xlsx\n重复.xlsx')), /重复/);

console.log('insight request parser tests passed');

const monthlyPrompt = String.raw`生成洞察报告
产品：产品名称
服务周期：2026-09-01 至 2026-09-30
委托方：委托方名称
服务商：服务商名称
依据以下文件：
/Users/a11/Downloads/AI智能随访/月度患者清单\_江苏畅达-4月-300w\.xlsx
/Users/a11/Downloads/AI智能随访/患者随访\_江苏畅达-4月-300w\.xlsx
/Users/a11/Downloads/AI智能随访/症状自评\_江苏畅达-4月-300w\.xlsx
/Users/a11/Downloads/AI智能随访/用药提醒\_江苏畅达-4月-300w\.xlsx
/Users/a11/Downloads/AI智能随访/不良反应清单\_江苏畅达-4月-300w\.xlsx
输出Word文件模板：/绝对路径/视觉参考.docx`;
const monthly = parseInsightRequest(monthlyPrompt);
assert.equal(monthly.sourcePaths.length, 5);
assert.equal(monthly.sourcePaths[0], '/Users/a11/Downloads/AI智能随访/月度患者清单_江苏畅达-4月-300w.xlsx');
assert.equal(monthly.client, '委托方名称');
assert.equal(monthly.provider, '服务商名称');
assert.equal(monthly.templatePath, '/绝对路径/视觉参考.docx');
