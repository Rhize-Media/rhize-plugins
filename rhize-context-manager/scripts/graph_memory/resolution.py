"""Deterministic display-name normalization without identity acceptance."""

from __future__ import annotations

import math
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any, Mapping

from .contract import HASH_PATTERN, sha256_value


NORMALIZATION_VERSION = "1.0.0"
MAX_LABEL_LENGTH = 4096
MAX_ALIAS_LENGTH = 512
MAX_ALIASES = 32
MAX_CONTEXT_TOKENS = 64
MAX_VECTOR_DIMENSIONS = 64
TRUST_LEVELS = ("unverified", "low", "medium", "high")
PROTECTED_ENTITY_TYPES = frozenset(
    {
        "Repository", "Branch", "Commit", "Deployment", "Service", "Environment",
        "Approval", "Task", "Run", "Procedure",
    }
)
_SAFE_TYPE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")
_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/+#-]{0,127}$")
_POISON_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"ignore\s+(all\s+)?previous\s+instructions",
        r"system\s+prompt",
        r"execute\s+(this\s+)?(?:command|tool)",
        r"override\s+(?:policy|approval|permissions?|identity)",
        r"(?:accept|create)\s+same[_ -]?as",
        r"trusted[_ -]?id\s*[:=]",
    )
)


class HygieneError(ValueError):
    """Raised when graph-hygiene input is malformed or unsafe to process."""


def normalize_entity(entity: Mapping[str, Any]) -> dict[str, Any]:
    """Return a separate comparison projection; never mutate or merge the entity."""

    required = {
        "entityId", "tenantHash", "namespaceHash", "entityType", "acl", "trust",
        "confidenceClass", "quarantined", "sourceRevisionHash", "sourceRefHash", "label",
        "aliases", "deterministicIdentity", "comparisonTokens", "semanticVector",
        "recordedAt", "schemaVersion", "evidenceVersion",
    }
    if not isinstance(entity, dict) or set(entity) != required:
        raise HygieneError("identity entity has missing or unknown fields")
    for field in ("entityId", "tenantHash", "namespaceHash", "sourceRevisionHash", "sourceRefHash"):
        validate_hash(entity[field], field)
    validate_entity_type(entity["entityType"])
    acl = entity["acl"]
    if (
        not isinstance(acl, list)
        or not acl
        or len(acl) > 64
        or len(acl) != len(set(acl))
        or not all(isinstance(scope, str) and _SAFE_TOKEN.fullmatch(scope) for scope in acl)
    ):
        raise HygieneError("entity ACL must be a bounded unique scope list")
    if entity["trust"] not in TRUST_LEVELS:
        raise HygieneError("entity trust is invalid")
    if entity["confidenceClass"] not in {"EXTRACTED", "INFERRED", "AMBIGUOUS"}:
        raise HygieneError("entity confidenceClass is invalid")
    if not isinstance(entity["quarantined"], bool):
        raise HygieneError("entity quarantined must be boolean")
    recorded_at = parse_timestamp(entity["recordedAt"], "recordedAt")
    for field in ("schemaVersion", "evidenceVersion"):
        _validate_text(entity[field], field, 128)

    flags: set[str] = set()
    label = entity["label"]
    if not isinstance(label, str) or not label.strip() or len(label) > MAX_LABEL_LENGTH:
        flags.add("giant_or_invalid_label")
        label = ""
    aliases = entity["aliases"]
    if not isinstance(aliases, list):
        raise HygieneError("aliases must be an array")
    if len(aliases) > MAX_ALIASES:
        flags.add("alias_storm")
        bounded_aliases: list[str] = []
    else:
        bounded_aliases = []
        for alias in aliases:
            if not isinstance(alias, str) or not alias.strip() or len(alias) > MAX_ALIAS_LENGTH:
                flags.add("giant_or_invalid_alias")
                continue
            bounded_aliases.append(alias)

    surface_forms = [value for value in [label, *bounded_aliases] if value]
    for surface in surface_forms:
        if _contains_poison(surface):
            flags.add("prompt_injection")
        flags.update(_confusable_flags(surface))
    canonical_forms = sorted({_canonicalize(value) for value in surface_forms if value})
    canonical_name = _canonicalize(label) if label else ""
    canonical_aliases = [value for value in canonical_forms if value != canonical_name]

    comparison_tokens = entity["comparisonTokens"]
    if (
        not isinstance(comparison_tokens, list)
        or len(comparison_tokens) > MAX_CONTEXT_TOKENS
        or len(comparison_tokens) != len(set(comparison_tokens))
        or not all(isinstance(token, str) and _SAFE_TOKEN.fullmatch(token) for token in comparison_tokens)
    ):
        flags.add("invalid_comparison_tokens")
        comparison_tokens = []
    else:
        comparison_tokens = sorted(token.casefold() for token in comparison_tokens)

    vector = entity["semanticVector"]
    if vector is None:
        normalized_vector = None
    elif (
        not isinstance(vector, list)
        or not 1 <= len(vector) <= MAX_VECTOR_DIMENSIONS
        or any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not -1 <= value <= 1
            for value in vector
        )
    ):
        flags.add("poisoned_embedding")
        normalized_vector = None
    else:
        normalized_vector = [float(value) for value in vector]

    deterministic_identity = _validate_deterministic_identity(entity["deterministicIdentity"])
    deterministic_eligible = bool(
        deterministic_identity
        and entity["trust"] == "high"
        and entity["confidenceClass"] == "EXTRACTED"
        and not entity["quarantined"]
        and not flags
    )
    eligible = bool(
        canonical_name
        and entity["trust"] in {"medium", "high"}
        and entity["confidenceClass"] != "AMBIGUOUS"
        and not entity["quarantined"]
        and not flags
    )
    return {
        "normalizationVersion": NORMALIZATION_VERSION,
        "entityId": entity["entityId"],
        "tenantHash": entity["tenantHash"],
        "namespaceHash": entity["namespaceHash"],
        "entityType": entity["entityType"],
        "acl": sorted(acl),
        "trust": entity["trust"],
        "sourceRevisionHash": entity["sourceRevisionHash"],
        "sourceRefHash": entity["sourceRefHash"],
        "recordedAt": recorded_at.astimezone(timezone.utc).isoformat(),
        "schemaVersion": entity["schemaVersion"],
        "evidenceVersion": entity["evidenceVersion"],
        "surfaceForms": surface_forms,
        "surfaceFormHashes": [sha256_value(value) for value in surface_forms],
        "canonicalName": canonical_name,
        "canonicalAliases": canonical_aliases,
        "comparisonTokens": comparison_tokens,
        "semanticVector": normalized_vector,
        "deterministicIdentity": deterministic_identity,
        "deterministicEligible": deterministic_eligible,
        "eligibleForComparison": eligible,
        "protectedType": entity["entityType"] in PROTECTED_ENTITY_TYPES,
        "poisonFlags": sorted(flags),
    }


def canonical_pair(first_id: str, second_id: str) -> tuple[str, str]:
    validate_hash(first_id, "first candidate id")
    validate_hash(second_id, "second candidate id")
    if first_id == second_id:
        raise HygieneError("identity candidate pair must contain two distinct ids")
    return tuple(sorted((first_id, second_id)))


def validate_hash(value: Any, name: str) -> str:
    if not isinstance(value, str) or not HASH_PATTERN.fullmatch(value):
        raise HygieneError(f"{name} must be a sha256 hash")
    return value


def validate_entity_type(value: Any) -> str:
    if not isinstance(value, str) or not _SAFE_TYPE.fullmatch(value):
        raise HygieneError("entityType is invalid")
    return value


def parse_timestamp(value: Any, name: str) -> datetime:
    if not isinstance(value, str) or "T" not in value or len(value) > 64:
        raise HygieneError(f"{name} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HygieneError(f"{name} must be an ISO-8601 timestamp") from exc
    if parsed.utcoffset() is None:
        raise HygieneError(f"{name} must include a timezone")
    return parsed


def trust_rank(level: str) -> int:
    if level not in TRUST_LEVELS:
        raise HygieneError("trust level is invalid")
    return TRUST_LEVELS.index(level)


def _canonicalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold().strip()
    return " ".join(normalized.split())


def _confusable_flags(value: str) -> set[str]:
    flags: set[str] = set()
    scripts: set[str] = set()
    for character in value:
        if not character.isalpha():
            continue
        name = unicodedata.name(character, "")
        for script in ("LATIN", "CYRILLIC", "GREEK"):
            if script in name:
                scripts.add(script)
    if len(scripts) > 1:
        flags.add("mixed_script_confusable")
    if any(ord(character) > 127 and unicodedata.normalize("NFKC", character).isascii() for character in value):
        flags.add("compatibility_confusable")
    return flags


def _contains_poison(value: str) -> bool:
    return any(pattern.search(value) for pattern in _POISON_PATTERNS)


def _validate_deterministic_identity(value: Any) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {"kind", "valueHash", "authorityHash"}:
        raise HygieneError("deterministicIdentity has missing or unknown fields")
    if not isinstance(value["kind"], str) or not re.fullmatch(r"[a-z][a-z0-9_]{1,63}", value["kind"]):
        raise HygieneError("deterministic identity kind is invalid")
    validate_hash(value["valueHash"], "deterministic identity valueHash")
    validate_hash(value["authorityHash"], "deterministic identity authorityHash")
    return dict(value)


def _validate_text(value: Any, name: str, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise HygieneError(f"{name} must be bounded text")
    return value
