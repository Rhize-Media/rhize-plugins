def retry_delay(attempt: int) -> int:
    return min(2 ** (attempt - 1), 8)
