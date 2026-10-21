import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from search_disease_medications import search_candidates


class SearchDiseaseMedicationsTest(unittest.TestCase):
    def test_fetches_whitelist_page_and_parses_complete_candidate(self):
        search_html = """
        <html><body>
          <a href="https://www.example.com/marketing">营销页</a>
          <a href="https://www.nhc.gov.cn/guide/constipation">慢性便秘诊疗指南</a>
        </body></html>
        """
        source_html = """
        <article>
          <h1>慢性便秘诊疗指南</h1>
          <p>疾病：功能性便秘。药品名称：聚乙二醇4000散；规格：10g/袋；
          每次用量：10g；给药途径：口服；频次：每日1次；用药时间：08:00；
          疗程：30天；疾病关联：用于功能性便秘的渗透性通便治疗；
          饮食禁忌：测试饮食依据；合并用药：测试相互作用依据；
          用药观察：测试观察依据；储存保存：测试包装贮藏依据。</p>
        </article>
        """

        def opener(url, timeout):
            if "bing.com" in url:
                return search_html.encode("utf-8")
            return source_html.encode("utf-8")

        result = search_candidates("测试产品", "功能性便秘", opener=opener)

        self.assertEqual(result["status"], "success")
        self.assertEqual(len(result["candidates"]), 1)
        candidate = result["candidates"][0]
        self.assertEqual(candidate["drugName"], "聚乙二醇4000散")
        self.assertEqual(candidate["role"], "diseaseTreatment")
        self.assertEqual(candidate["precautions"]["储存保存"], "测试包装贮藏依据")
        self.assertIn("功能性便秘", candidate["diseaseRationale"])
        self.assertEqual(candidate["evidence"][0]["url"], "https://www.nhc.gov.cn/guide/constipation")
        self.assertEqual(result["sources"][0]["status"], "parsed")

    def test_search_snippet_alone_never_becomes_evidence(self):
        search_html = """
        <a href="https://www.nhc.gov.cn/guide/constipation">
          功能性便秘可用聚乙二醇4000散，每日1次
        </a>
        """

        def opener(url, timeout):
            return search_html.encode("utf-8")

        result = search_candidates("测试产品", "功能性便秘", opener=opener)

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["incompleteCandidates"], [])
        self.assertTrue(any("来源页" in error for error in result["errors"]))

    def test_incomplete_source_is_reported_without_candidate(self):
        search_html = '<a href="https://www.nmpa.gov.cn/label">国家药品说明书</a>'
        source_html = """
        <p>疾病：功能性便秘。药品名称：聚乙二醇4000散；疾病关联：便秘通便。</p>
        """

        def opener(url, timeout):
            return search_html.encode("utf-8") if "bing.com" in url else source_html.encode("utf-8")

        result = search_candidates("测试产品", "功能性便秘", opener=opener)

        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["incompleteCandidates"][0]["drugName"], "聚乙二醇4000散")
        self.assertIn("specification", result["incompleteCandidates"][0]["missingFields"])

    def test_network_error_returns_structured_failure(self):
        def opener(url, timeout):
            raise TimeoutError("timeout")

        result = search_candidates("测试产品", "功能性便秘", opener=opener)

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["candidates"], [])
        self.assertTrue(result["errors"])

    def test_complete_dose_without_four_precaution_sources_is_incomplete(self):
        from search_disease_medications import parse_source_page
        page = ("功能性便秘用于治疗。药品名称：测试药；规格：10mg；每次用量：10mg；"
                "给药途径：口服；频次：每日1次；用药时间：08:00；疗程：7天；")
        complete, incomplete, _ = parse_source_page(page, "https://www.nhc.gov.cn/test", "测试指南", "功能性便秘")
        self.assertEqual(complete, [])
        self.assertIn("precautions.储存保存", incomplete[0]["missingFields"])


if __name__ == "__main__":
    unittest.main()
