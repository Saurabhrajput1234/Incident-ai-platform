import re


def is_valid_email(email: str) -> bool:
    pattern = r"^[\w\.-]+@[\w\.-]+\.\w{2,}$"
    return bool(re.match(pattern, email))


def is_non_empty_string(value: str) -> bool:
    return isinstance(value, str) and len(value.strip()) > 0
