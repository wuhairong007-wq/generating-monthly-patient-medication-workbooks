import assert from "node:assert/strict";
import test from "node:test";

import {
  productNameCandidates,
  validateAdverseReactionWording,
} from "../scripts/adverse_reaction_wording.mjs";

function record(overrides = {}) {
  return {
    userid: "U001",
    severityGrade: "轻度",
    symptomDescription: "患者反馈出现短暂头晕，建议记录持续时间。",
    medicationRelationship: "上述表现与用药时间可能存在先后关联，现有信息不足以确认因果关系。",
    treatmentMeasures: "建议记录症状变化，必要时联系医师或药师评估。",
    ...overrides,
  };
}

test("轻度患者三个目标字段拒绝人工核验措辞", () => {
  for (const [field, value] of [
    ["symptomDescription", "具体情况需人工核实。"],
    ["medicationRelationship", "因果关系需人工确认。"],
    ["treatmentMeasures", "建议人工复核当前用药。"],
  ]) {
    assert.throws(
      () => validateAdverseReactionWording(record({ [field]: value }), "注射用胰蛋白酶"),
      /轻度患者/,
    );
  }
});

test("中度患者可保留风险相称的人工复核措辞", () => {
  assert.doesNotThrow(() => validateAdverseReactionWording(record({
    severityGrade: "中度",
    treatmentMeasures: "建议人工复核症状及当前用药，必要时联系医师。",
  }), "注射用胰蛋白酶"));
});

test("关系分析拒绝正式产品名、简称、空格变体和产品代词", () => {
  for (const medicationRelationship of [
    "上述表现与注射用胰蛋白酶可能有关。",
    "上述表现与胰蛋白酶可能有关。",
    "上述表现与注射用 胰蛋白酶可能有关。",
    "上述表现与该产品可能有关。",
  ]) {
    assert.throws(
      () => validateAdverseReactionWording(record({ medicationRelationship }), "注射用胰蛋白酶"),
      /推广产品/,
    );
  }
});

test("关系分析拒绝括号中的商品名和去剂型简称", () => {
  const candidates = productNameCandidates("双歧杆菌四联活菌片(思连康)");
  assert.ok(candidates.includes("思连康"));
  assert.ok(candidates.includes("双歧杆菌四联活菌"));
  for (const medicationRelationship of [
    "思连康使用后可能存在时间关联。",
    "双歧杆菌四联活菌相关性尚不能确认。",
  ]) {
    assert.throws(
      () => validateAdverseReactionWording(record({ medicationRelationship }), "双歧杆菌四联活菌片(思连康)"),
      /推广产品/,
    );
  }
});

test("中性关系分析通过校验", () => {
  assert.doesNotThrow(() => validateAdverseReactionWording(record(), "注射用胰蛋白酶"));
});
