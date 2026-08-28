from .io import encode


def payload(value: str) -> bytes:
    return encode(value)
