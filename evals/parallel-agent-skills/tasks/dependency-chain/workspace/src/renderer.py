from src.schema import UserRecord


def render_user(user: UserRecord) -> str:
    return f"User: {user.display_name}"
