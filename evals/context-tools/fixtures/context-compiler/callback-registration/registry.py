from collections.abc import Callable


def subscribe(event_name: str, callback: Callable) -> tuple[str, Callable]:
    return event_name, callback
