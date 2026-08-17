import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]


class SkillContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        cls.contract = (SKILL_DIR / "references" / "input-output-contract.md").read_text(encoding="utf-8")
        cls.rules = (SKILL_DIR / "references" / "adverse-reaction-generation-rules.md").read_text(encoding="utf-8")
        cls.agent = (SKILL_DIR / "agents" / "openai.yaml").read_text(encoding="utf-8")

    def test_description_triggers_adverse_reaction_workflow(self):
        frontmatter = self.skill.split("---", 2)[1]
        self.assertIn("生成不良反应清单", frontmatter)

    def test_adverse_reaction_trigger_requires_product(self):
        self.assertIn("产品：", self.skill)
        self.assertIn("产品：", self.contract)
        self.assertIn("产品：", self.agent)
        self.assertNotIn("不要求产品类型或产品名称", self.skill)
        self.assertNotIn("不要求产品类型或产品名称", self.contract)

    def test_rules_do_not_force_draft_prefixes(self):
        self.assertNotIn("备注必须标注“人工审核草案”", self.rules)
        self.assertIn("不得添加固定", self.rules)

    def test_skill_references_all_adverse_reaction_resources(self):
        for expected in [
            "references/adverse-reaction-generation-rules.md",
            "scripts/generate_adverse_reactions.py",
            "scripts/build_adverse_reaction_workbook.mjs",
            "scripts/verify_adverse_reaction_workbook.mjs",
            "assets/adverse-reaction-template.xlsx",
        ]:
            self.assertIn(expected, self.skill)

    def test_contract_contains_required_fields_and_filtered_coverage_rule(self):
        for field in [
            "userid",
            "symptomDescription",
            "severityGrade",
            "treatmentMeasures",
            "treatmentOutcome",
            "remark",
        ]:
            self.assertIn(field, self.contract)
        self.assertIn("只输出", self.contract)
        self.assertIn("中度患者", self.contract)
        self.assertIn("重度患者", self.contract)

    def test_adverse_reaction_rules_require_age_disease_and_diversity(self):
        for expected in ["实际年龄", "年龄段", "主要症状", "伴随表现", "userid"]:
            self.assertIn(expected, self.rules)
        self.assertIn("重复率", self.rules)
        self.assertIn("实际年龄", self.skill)
        self.assertIn("重复率", self.skill)

    def test_agent_metadata_mentions_adverse_reaction_workbook(self):
        self.assertIn("不良反应", self.agent)


if __name__ == "__main__":
    unittest.main()
