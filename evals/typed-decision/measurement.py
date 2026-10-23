"""Descriptive class/calibration diagnostics; no fitted thresholds or promotion authority."""
from collections import Counter, defaultdict
import json


def summarize(samples):
    groups = defaultdict(list)
    for sample in samples:
        groups[(sample['decision'], sample['question'], sample['cardinality'])].append(sample)
    reports = []
    for (decision, question, cardinality), rows in sorted(groups.items()):
        matrix = Counter((json.dumps(r['label']), json.dumps(r['prediction'])) for r in rows)
        classes = []
        for label in sorted({json.dumps(r['label']) for r in rows}):
            support = sum(n for (gold, _), n in matrix.items() if gold == label)
            true = matrix[label, label]
            predicted = sum(n for (_, choice), n in matrix.items() if choice == label)
            classes.append({'label': json.loads(label), 'support': support, 'recall': true / support,
                            'f1': 2 * true / (support + predicted)})
        scored = [r for r in rows if r['confidence'] is not None]
        bins = []
        for index in range(10):
            values = [r for r in scored if min(int(r['confidence'] * 10), 9) == index]
            if values:
                bins.append({'lower': index / 10, 'upper': (index + 1) / 10, 'n': len(values),
                             'mean_confidence': sum(r['confidence'] for r in values) / len(values),
                             'accuracy': sum(r['raw_prediction'] == r['label'] for r in values) / len(values)})
        risks = []
        for threshold in (0, .5, .7, .9, 1):
            answered = [r for r in scored if r['confidence'] >= threshold]
            risks.append({'threshold': threshold, 'answered': len(answered),
                          'coverage': len(answered) / len(rows),
                          'error_rate': sum(r['raw_prediction'] != r['label'] for r in answered) / len(answered)
                          if answered else None})
        reports.append({'decision': decision, 'question': question, 'candidate_count': cardinality,
                        'n': len(rows), 'independent_groups': len({r['group'] for r in rows}),
                        'label_bases': dict(Counter(r['label_basis'] for r in rows)),
                        'classes': classes,
                        'confusion': [{'label': json.loads(gold), 'prediction': json.loads(choice), 'count': n}
                                      for (gold, choice), n in sorted(matrix.items())],
                        'balanced_accuracy': sum(c['recall'] for c in classes) / len(classes),
                        'macro_f1': sum(c['f1'] for c in classes) / len(classes),
                        'reliability': bins,
                        'ece': sum(b['n'] * abs(b['accuracy'] - b['mean_confidence']) for b in bins) / len(scored)
                        if scored else None,
                        'risk_coverage': risks if scored else [], 'calibrated': False,
                        'claim_scope': 'descriptive only; repeated variants are not independent samples'})
    return reports
