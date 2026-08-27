import re


def normalize_email(value: str) -> str:
    return value.strip()


def normalize_phone(value: str) -> str:
    return re.sub(r"[^0-9+]", "", value)
