import importlib


def dispatch(module_name: str) -> str:
    module = importlib.import_module(module_name)
    return getattr(module, "handle")()
