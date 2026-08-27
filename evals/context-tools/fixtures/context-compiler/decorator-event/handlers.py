from registry import receiver


@receiver("created")
def handle_created() -> str:
    return "created"
