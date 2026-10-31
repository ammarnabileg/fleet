"""Comparing what people type in spreadsheet headers: case, spaces, the asterisk of required columns and Arabic
letter variants (hamza forms, taa marbuta, alif maqsura, tatweel) are ignored."""

_ARABIC = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ة": "ه", "ى": "ي", "ـ": ""})


def cell_text(value) -> str:
    """A spreadsheet cell as text: whole floats without ".0", spaces collapsed."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return " ".join(str(value).split())


def norm(value) -> str:
    return " ".join(cell_text(value).lower().translate(_ARABIC).replace("*", " ").split())
