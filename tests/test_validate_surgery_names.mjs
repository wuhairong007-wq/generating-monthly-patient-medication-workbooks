import assert from 'node:assert/strict';
import { validateSurgeryNames, validateSimulationPresentation } from '../scripts/validate_medication_payload.mjs';

function payload(name, productType = '器械') {
  return {meta:{productType, productName:'测试器械'},patients:[{userid:'u1',disease:'腹腔粘连'}],records:[{userid:'u1',surgeryName:name}]};
}
assert.doesNotThrow(()=>validateSurgeryNames(payload('腹腔粘连松解术')));
assert.doesNotThrow(()=>validateSurgeryNames(payload('腹腔粘连松解术（腹腔镜）')));
assert.doesNotThrow(()=>validateSurgeryNames(payload('', '用药')));
for (const name of ['待确认（前列腺术后粘连部位未详）','宫腔镜下宫腔粘连分离术（器械适用性待核实）','腹腔粘连松解术（模拟候选）','可能行腹腔粘连松解术','',null]) {
  assert.throws(()=>validateSurgeryNames(payload(name)), /u1.*手术名称/);
}
assert.throws(()=>validateSurgeryNames(payload('腹腔粘连松解术', '用药')), /手术名称必须为空/);
console.log('surgery name validation tests passed');
const simulated = payload('腹腔粘连松解术');
simulated.meta.simulation = true;
assert.doesNotThrow(()=>validateSimulationPresentation(simulated, ['/out/用药提醒_模拟.xlsx'], [{name:'清单',values:[['手术名称'],['腹腔粘连松解术']]}]));
assert.throws(()=>validateSimulationPresentation(simulated, ['/out/模拟/用药提醒.xlsx']), /文件名/);
assert.throws(()=>validateSimulationPresentation(simulated, ['/out/用药提醒_模拟.xlsx'], [{name:'清单',values:[['模拟数据']]}]), /内容不能/);
assert.throws(()=>validateSimulationPresentation(simulated, ['/out/用药提醒_模拟.xlsx'], [{name:'模拟清单',values:[]}]), /工作表名称/);
assert.throws(()=>validateSimulationPresentation({meta:{surgerySimulationAudit:[{userid:'u1'}]}}, []), /缺少/);
console.log('simulation presentation tests passed');
