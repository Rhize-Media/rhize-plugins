def normalize(value: str) -> str:
    return "".join(character for character in value if character.isdigit())
