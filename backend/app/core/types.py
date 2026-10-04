from typing import Annotated

from pydantic import Field, StringConstraints

LangCode = Annotated[str, StringConstraints(pattern=r"^[a-z]{2,3}(-[A-Z]{2})?$")]
Text200 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]

# A name in several languages, e.g. {"ar": "الشركة", "en": "The Company"}. The service layer checks that the
# languages are active and that the default language is present (i18n.service.validate_localized).
LocalizedText = Annotated[dict[LangCode, Text200], Field(min_length=1, max_length=20)]
