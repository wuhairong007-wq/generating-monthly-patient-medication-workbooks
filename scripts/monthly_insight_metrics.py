"""Metrics for monthly master, reminders, followups, assessments and optional AE."""
import calendar
import re
from collections import Counter, defaultdict

from extract_insight_sources import age_bucket, build_metrics, clean, normalize_patient_id, ratio


def build_monthly_metrics(data, product, start, end):
    # Reuse demographic/answer/event calculations, without inventing legacy source rows.
    metrics = build_metrics({**data, 'healthPlans': [], 'tracking': [], 'medications': []}, product)
    patients = data['patients']
    n = len(patients)
    missing_ages = sum(age_bucket(row.get('年龄')) == '无记录' for row in patients)
    if missing_ages:
        metrics['ageDistribution'].append({'label': '无记录', 'count': missing_ages})
    title = patients[0].get('_sourceTitle', '')
    match = re.search(r'(\d{4})\s*[年/-]\s*(\d{1,2})', title)
    source_month = f'{int(match[1]):04d}-{int(match[2]):02d}' if match else None
    month_matches = (source_month == start.strftime('%Y-%m') and start.day == 1
                     and end.year == start.year and end.month == start.month
                     and end.day == calendar.monthrange(start.year, start.month)[1])
    raw_counts = [clean(row.get('AI用药提醒次数')) for row in patients]
    valid_counts = all(re.fullmatch(r'\d+(?:\.0+)?', value) for value in raw_counts)
    total = sum(int(float(value)) for value in raw_counts) if valid_counts else None
    reminder_total = total if month_matches else None
    metrics['monthlySummary'] = {'sourceMonth': source_month, 'matchesPeriod': month_matches,
                                 'sourceReminderTotal': total,
                                 'basis': '月度患者主表AI用药提醒次数；仅与报告完整月份一致时纳入周期统计'}
    reminder_ids = {normalize_patient_id(row) for row in patients
                    if valid_counts and float(row.get('AI用药提醒次数', 0)) > 0}
    plans = data['medicationReminders']
    plan_ids = {normalize_patient_id(row) for row in plans}
    metrics['healthPlanCoverage'] = None
    metrics['trackingCoverage'] = ratio(len(reminder_ids), n) if month_matches and valid_counts else None
    metrics['reminderPlanCoverage'] = ratio(len(plan_ids), n)
    metrics['serviceExecution'].update(healthPlans=None, trackingPatients=None,
        medicationReminders=reminder_total, totalPrompts=reminder_total,
        temperatureMonitoring=None, vitalMonitoring=None, estimatedResponses=None,
        estimatedResponseRate=None, responseRateBasis=None, reminderPlanRecords=len(plans))
    drugs_by_patient = defaultdict(set)
    plan_combinations = Counter()
    for row in plans:
        # Only explicit drug names; never infer specification/dose/frequency from narrative plans.
        drugs = {part.strip() for part in re.split(r'[、,，;；+\n]', clean(row.get('联合用药'))) if part.strip()}
        drugs_by_patient[normalize_patient_id(row)].update(drugs)
        if drugs:
            plan_combinations[' + '.join(sorted(drugs))] += 1
    drugs = Counter(drug for names in drugs_by_patient.values() for drug in sorted(names))
    combination_counts = Counter(len(names) for names in drugs_by_patient.values() if names)
    drug_entries = sum(drugs.values())
    metrics['medications'] = {
        'recordCount': drug_entries, 'uniqueDrugCount': len(drugs),
        'averageDrugsPerPatient': round(drug_entries/n, 2),
        'drugDistribution': [{'label': name, 'count': count} for name, count in drugs.most_common()],
        'combinationCountDistribution': [{'label': str(k), 'count': v} for k,v in sorted(combination_counts.items())],
        'combinationModeDistribution': [{'label': k, 'count': v} for k,v in plan_combinations.most_common()],
        'productSpecificationDistribution': [], 'productFrequencyDistribution': [], 'productCourseDistribution': [],
        'planCycleDistribution': [{'label': k, 'count': v} for k,v in Counter(clean(row.get('用药周期')) or '无记录' for row in plans).most_common()],
        'productPatientCount': drugs.get(product, 0),
        'basis': '联合用药字段的登记药名，药品分布按患者ID和药名去重；组合模式按方案记录计数，不代表实际服药或同时联用',
    }
    for key, field in [('moduleCoverageByDisease','疾病'),('moduleCoverageByAge','年龄')]:
        ids_by_group = defaultdict(set)
        for row in patients:
            label = age_bucket(row[field]) if field == '年龄' else clean(row[field]) or '无记录'
            ids_by_group[label].add(normalize_patient_id(row))
        for group in metrics[key]:
            group_ids = ids_by_group[group['label']]
            group['modules'].pop('健康管理方案', None)
            group['modules'].pop('用药提醒', None)
            group['modules']['用药方案登记'] = ratio(len(group_ids & plan_ids), len(group_ids))
    metrics['serviceGoals'] = [
        {'label': '用药方案登记覆盖', 'actual': metrics['reminderPlanCoverage'], 'goal': '描述性统计'},
        {'label': '智能随访覆盖', 'actual': metrics['followupCoverage'], 'goal': '描述性统计'},
        {'label': '症状自评覆盖', 'actual': metrics['symptomCoverage'], 'goal': '描述性统计'},
    ]
    return metrics
