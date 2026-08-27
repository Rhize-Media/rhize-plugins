from collections.abc import Callable


def receiver(event_name: str) -> Callable:
    def decorate(function: Callable) -> Callable:
        return function

    return decorate
