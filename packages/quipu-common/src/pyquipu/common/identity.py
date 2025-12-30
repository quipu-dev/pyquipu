import re


def get_user_id_from_email(email: str) -> str:
    if not email:
        return ""

    clean = email.lower().strip()
    # Replace common symbols with URL-safe and ref-safe separators.
    clean = clean.replace("@", "-at-").replace(".", "-dot-")
    # Remove any remaining non-compliant characters.
    return re.sub(r"[^a-z0-9-]", "", clean)
