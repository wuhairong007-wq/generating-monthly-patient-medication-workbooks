import fs from 'node:fs/promises';
import { parseArgs } from 'node:util';
import { parseInsightRequest, parseDeepInterviewRequest } from './insight_request_parser.mjs';

const { values } = parseArgs({ options: { input: { type: 'string' }, output: { type: 'string' } } });
if (!values.input || !values.output) throw new Error('需要 --input 请求文本文件和 --output JSON文件');
const text = await fs.readFile(values.input, 'utf8');
const insight = text.includes('生成洞察报告');
const interview = ['生成患者调研访谈', '生成深度访谈'].some(trigger => text.includes(trigger));
if (insight === interview) throw new Error('请求必须且只能包含一种报告/访谈触发词');
const request = insight ? parseInsightRequest(text) : parseDeepInterviewRequest(text);
await fs.writeFile(values.output, JSON.stringify({ workflow: insight ? 'insight' : 'interview', ...request }, null, 2), { flag: 'wx' });
console.log(values.output);
