import unittest
import test_disease_specific_plans as helpers
from test_disease_specific_plans import disease_plan, group, medication, patient, profile


class DeviceMedicationMinimumsTest(unittest.TestCase):
    run_generator = helpers.DiseaseSpecificPlansTest.run_generator

    def spec(self, count):
        plan = disease_plan('围手术期', ['腹腔粘连'], [group(f'g{i}', [medication(f'测试药{i}')]) for i in range(count)])
        return profile([plan], productType='器械', baseMedication=None,
                       surgeryRules=[{'when':{'diseaseEqualsAny':['腹腔粘连']},'surgeryName':'腹腔粘连松解术'}])

    def test_device_requires_three_distinct_disease_medications(self):
        for count in [1,2,3]:
            with self.subTest(count=count):
                result, payload = self.run_generator([patient('device-u1','腹腔粘连')], self.spec(count))
                if count < 3:
                    self.assertNotEqual(result.returncode,0)
                    self.assertIn('至少需要3',result.stderr)
                    self.assertIsNone(payload)
                else:
                    self.assertEqual(result.returncode,0,result.stderr)
                    self.assertEqual(len(payload['records'][0]['combinedMedication']),3)
                    self.assertEqual(payload['meta']['minimumCombinedMedicationCountByUserid']['device-u1'],3)
                    self.assertEqual(payload['meta']['minimumDiseaseMedicationCountByUserid']['device-u1'],3)

    def test_device_cannot_lower_minimum_even_with_rationale(self):
        spec=self.spec(1)
        spec['diseasePlans'][0].update(minimumCombinedMedicationCount=2, minimumDiseaseMedicationCount=1, medicationCountRationale='只需一种镇痛药')
        result,_=self.run_generator([patient('u1','腹腔粘连')],spec)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('器械',result.stderr)
