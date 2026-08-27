from registry import subscribe


def handle_created() -> str:
    return "created"


subscribe("created", handle_created)
