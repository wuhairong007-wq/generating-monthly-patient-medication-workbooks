import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from generate_insight_charts import _radar_chart, generate_charts


class ChartGenerationTest(unittest.TestCase):
    def test_generates_manifest_and_nonempty_pngs(self):
        insight = {
            "metadata": {"patientCount": 10, "product": "注射用胰蛋白酶"},
            "metrics": {
                "sexDistribution": [{"label": "男", "count": 6}, {"label": "女", "count": 4}],
                "ageDistribution": [{"label": "31–40岁", "count": 10}],
                "regionDistribution": [{"label": "湖北省武汉市", "count": 10}],
                "diseaseDistribution": [{"label": "软组织血肿", "count": 10}],
                "serviceExecution": {"medicationReminders": 30, "temperatureMonitoring": 20, "vitalMonitoring": 10, "followupRecords": 8, "symptomRecords": 9},
                "medications": {"drugDistribution": [{"label": "注射用胰蛋白酶", "count": 10}], "productCourseDistribution": [{"label": "3", "count": 10}]},
                "symptoms": {"dimensionMeans": [2, 2.5, 3, 1.5, 2, 1], "questions": ["1、肿胀", "2、疼痛", "3、渗出", "4、功能", "5、炎症", "6、活动"]},
                "adverseEvents": {"severityDistribution": [{"label": "轻度", "count": 1}]},
                "riskDistribution": [{"label": "低风险", "count": 9}, {"label": "中风险", "count": 1}],
                "serviceGoals": [{"label": "健康管理方案覆盖", "actual": {"value": 1.0}, "goal": "全量覆盖"}],
            },
        }
        with tempfile.TemporaryDirectory() as temp:
            manifest_path = generate_charts(insight, temp)
            manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
            self.assertGreaterEqual(len(manifest), 6)
            for item in manifest:
                with Image.open(Path(temp) / item["file"]) as image:
                    self.assertGreater(image.width, 100)
                    self.assertGreater(image.height, 100)
                    self.assertNotIn(item["caption"], image.info.get("Description", ""))

    def test_radar_chart_matches_reference_geometry(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "radar.png"
            _radar_chart(output, ["1、肿胀", "2、疼痛", "3、渗出", "4、炎症", "5、日常活动", "6、瘙痒"], [1, 2, 3, 2.5, 1.5, 2])
            with Image.open(output) as image:
                self.assertEqual(image.size, (1200, 820))
                colors = image.getcolors(maxcolors=1200 * 820)
                self.assertIsNotNone(colors)
                self.assertGreater(sum(count for count, color in colors if color != (255, 255, 255)), 1000)
                # A dark outer circle is a distinguishing feature of the reference style.
                outer_ring = [
                    image.getpixel((x, y))
                    for x in range(286, 835)
                    for y in (160, 161, 699, 700)
                ]
                self.assertTrue(any(max(pixel) < 100 for pixel in outer_ring))


if __name__ == "__main__":
    unittest.main()
