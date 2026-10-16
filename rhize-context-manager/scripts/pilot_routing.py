"""Single workflow-pilot routing decoder shared by collection and research."""
import math

CHOICES = ('content', 'general', 'none')
EXCLUSIONS = frozenset({'content_creation', 'publishing', 'deployment', 'external_messages'})


def _decode(scores, abstain_below, exclusions):
    if not isinstance(scores, dict) or set(scores) != set(CHOICES):
        raise ValueError('invalid routing scores')
    if any(type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 1
           for score in scores.values()):
        raise ValueError('invalid routing score')
    if (type(abstain_below) not in (int, float) or not math.isfinite(abstain_below)
            or not 0 <= abstain_below <= 1):
        raise ValueError('invalid abstention threshold')
    if (not isinstance(exclusions, (list, tuple)) or len(exclusions) > 4
            or any(not isinstance(x, str) or x not in EXCLUSIONS for x in exclusions)
            or len(set(exclusions)) != len(exclusions)):
        raise ValueError('invalid routing exclusions')
    ranking = sorted(({'candidateId': name, 'score': float(score)} for name, score in scores.items()
                      if not (name == 'content' and 'content_creation' in exclusions)),
                     key=lambda row: (-row['score'], row['candidateId']))
    abstained = ranking[0]['score'] < abstain_below
    return {'choice': None if abstained else ranking[0]['candidateId'], 'ranking': ranking,
            'reason': 'below_threshold' if abstained else None}


def decode_scores(scores, abstain_below=0.0, exclusions=()):
    """Historical v1/v2 replay decoder: observational argmax; never authority."""
    return _decode(scores, abstain_below, exclusions)


def decode_choice(probabilities, abstain_below=0.0, exclusions=()):
    """Typed `choice` decoder (workflow-input-v3): same shape and validation as decode_scores."""
    return _decode(probabilities, abstain_below, exclusions)
