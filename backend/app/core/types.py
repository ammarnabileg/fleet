from typing import Annotated

from pydantic import AfterValidator, Field, StringConstraints

LangCode = Annotated[str, StringConstraints(pattern=r"^[a-z]{2,3}(-[A-Z]{2})?$")]
Text200 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]

# A name in several languages, e.g. {"ar": "الشركة", "en": "The Company"}. The service layer checks that the
# languages are active and that the default language is present (i18n.service.validate_localized).
LocalizedText = Annotated[dict[LangCode, Text200], Field(min_length=1, max_length=20)]


def iban_ok(value: str) -> bool:
    """The ISO 13616 check digits (mod 97): catches a mistyped or swapped digit before salaries go to the bank."""
    value = value.replace(" ", "").upper()
    if not (15 <= len(value) <= 34 and value[:2].isalpha() and value[2:4].isdigit() and value.isalnum()):
        return False
    return int("".join(str(int(c, 36)) for c in value[4:] + value[:4])) % 97 == 1


def _iban(value: str) -> str:
    if not iban_ok(value):
        raise ValueError("invalid IBAN check digits")
    return value


Iban = Annotated[
    str,
    StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"^[A-Z]{2}[0-9]{2}[A-Z0-9]{10,30}$"),
    AfterValidator(_iban),
]
