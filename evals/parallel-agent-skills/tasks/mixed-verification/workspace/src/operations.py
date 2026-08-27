def add(left: int, right: int) -> int:
    return left + right


def headline(value: str) -> str:
    return value.strip().title()


def summary(name: str, count: int) -> str:
    return f"{headline(name)}: {add(count, 0)}"
