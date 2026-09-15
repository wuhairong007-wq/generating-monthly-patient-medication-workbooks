import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from prepare_interview_sources import prepare_interview, parse_research_period
import test_extract_insight_sources as source_tests


class PrepareInterviewSourcesTest(unittest.TestCase):
    def setUp(self):
        self.fixture = source_tests.ExtractInsightSourcesTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.root = Path(self.fixture.temp_dir.name)
        self.paths = [path for path in self.fixture.paths if not path.endswith('medications.xlsx')]
        source_tests.write_book(self.root / 'patients.xlsx', ['患者唯一标识', '性别', '年龄', '所属地区', '疾病'], [
            ['mild', '女', 50, '武汉', '疾病A'],
            ['medium', '男', 60, '武汉', '疾病A'],
            ['high', '女', 70, '武汉', '疾病A'],
        ])
        source_tests.write_book(self.root / 'ae.xlsx', ['患者ID', '不良反应发生时间', '不良反应严重程度分级'], [
            ['mild', '2026-07-12', '轻度'],
            ['medium', '2026-07-12', '中度'],
            ['high', '2026-07-12', '轻度'],
            ['high', '2026-07-14', '重度'],
            ['mild', '2026-08-01', '高度'],
        ])

    def request(self, **changes):
        return dict(researchTime='2026年7月', researchMethod='深度访谈',
                    outputKinds=['analysis', 'records'], count=2, includeMild=False,
                    sourcePaths=self.paths, templatePaths=[], **changes)

    def test_deduplicates_highest_severity_and_prioritizes_high_then_medium(self):
        result = prepare_interview(self.request())
        self.assertEqual([row['userid'] for row in result['selectedPatients']], ['high', 'medium'])
        self.assertEqual(result['eligiblePatientCount'], 2)
        self.assertEqual(result['selectedPatients'][0]['severity'], '高度')
        self.assertEqual(len(result['selectedPatients'][0]['evidence']['adverseEvents']), 2)
        self.assertEqual(result['period'], {'start': '2026-07-01', 'end': '2026-07-31'})
        self.assertNotIn('quotations', result)

    def test_mild_only_fills_after_higher_severities(self):
        request = self.request()
        request.update(includeMild=True, count=3, researchMethod='电话随访', outputKinds=['records'])
        result = prepare_interview(request)
        self.assertEqual([row['userid'] for row in result['selectedPatients']], ['high', 'medium', 'mild'])
        self.assertEqual(result['outputKinds'], ['records'])

    def test_stops_for_shortage_and_missing_adverse_event_evidence(self):
        request = self.request()
        request['count'] = 3
        with self.assertRaisesRegex(ValueError, '可选2人.*需要3人'):
            prepare_interview(request)
        request['sourcePaths'] = [path for path in self.paths if not path.endswith('ae.xlsx')]
        with self.assertRaisesRegex(ValueError, '不良反应.*资格'):
            prepare_interview(request)

    def test_stops_for_duplicate_master_ids(self):
        source_tests.write_book(self.root / 'patients.xlsx', ['userid', '性别', '年龄', '地区', '疾病'], [
            ['high', '女', 70, '武汉', '疾病A'], ['high', '女', 70, '武汉', '疾病A']])
        with self.assertRaisesRegex(ValueError, 'userid.*重复'):
            prepare_interview(self.request())

    def test_defaults_to_simulated_and_respects_explicit_mode(self):
        result = prepare_interview(self.request())
        self.assertEqual(result['dialogueMode'], 'simulated')
        self.assertTrue(result['simulationAuthorized'])
        for mode in ['actual', 'outline']:
            result = prepare_interview(self.request(dialogueMode=mode))
            self.assertEqual(result['dialogueMode'], mode)
            self.assertFalse(result['simulationAuthorized'])
        with self.assertRaisesRegex(ValueError, 'dialogueMode'):
            prepare_interview(self.request(dialogueMode='invalid'))

    def test_monthly_five_sources_keep_severity_period_and_patient_scope(self):
        reminder = self.root/'reminders.xlsx'
        source_tests.write_book(reminder, ['患者唯一标识','联合用药','用药方案确认时间','用药方案','用药周期'], [
            ['high','产品甲','2026-07-01','源方案','21天'],
            ['high','产品甲','2026-08-01','下月方案','21天'],
            ['outsider','产品甲','2026-07-01','外部患者','21天'],
        ])
        source_tests.write_book(self.root/'ae.xlsx', ['患者ID','不良反应发生时间','不良反应严重程度分级'], [
            ['high','2026-07-12','高度（3级）'], ['medium','2026-07-14','中度（2级）'],
            ['mild','2026-07-14','轻度（1级）'], ['outsider','2026-07-14','高度（3级）'],
        ])
        paths=[path for path in self.paths if Path(path).name not in {'plans.xlsx','tracking.xlsx'}]+[str(reminder)]
        request=self.request();request['sourcePaths']=paths
        result=prepare_interview(request)
        self.assertEqual(result['inputMode'],'monthly')
        self.assertEqual(result['eligiblePatientCount'],2)
        self.assertEqual([p['userid'] for p in result['selectedPatients']], ['high','medium'])
        self.assertEqual(len(result['selectedPatients'][0]['evidence']['medicationReminders']),1)
        self.assertEqual(result['sourceDiagnostics']['medicationReminders']['unmatchedRows'],1)
        request['researchTime']='2026年4月'
        with self.assertRaisesRegex(ValueError,'可选0人'):
            prepare_interview(request)
        request['researchTime']='2026年7月'
        request['sourcePaths']=paths+[str(self.root/'plans.xlsx')]
        with self.assertRaisesRegex(ValueError,'混合'):
            prepare_interview(request)

    def test_period_supports_month_single_day_and_inclusive_range(self):
        for value, expected in [
            ('2026年7月', ('2026-07-01', '2026-07-31')),
            ('2026-07', ('2026-07-01', '2026-07-31')),
            ('2026-07-12', ('2026-07-12', '2026-07-12')),
            ('2026-07-12 至 2026-08-01', ('2026-07-12', '2026-08-01')),
        ]:
            self.assertEqual(tuple(day.isoformat() for day in parse_research_period(value)), expected)
        for value in ['2026-02-30', '2026-07-31 至 2026-07-01', '某个月']:
            with self.assertRaises(ValueError):
                parse_research_period(value)


if __name__ == '__main__':
    unittest.main()
