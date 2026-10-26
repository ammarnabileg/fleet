"""Kuwait plates are stored code/number whatever separator (or none) they were typed with."""

import pytest

from app.modules.fleet.service import normalize_plate


@pytest.mark.parametrize(
    ("typed", "stored"),
    [
        ("1016684", "10/16684"),
        ("616684", "6/16684"),
        ("60-76505", "60/76505"),
        ("60 76505", "60/76505"),
        ("60 / 76505", "60/76505"),
        ("٦٠-٧٦٥٠٥", "60/76505"),
        ("12/34567", "12/34567"),
        ("ABC 123", "ABC 123"),
        ("123456789", "123456789"),
    ],
)
def test_plate_is_written_code_slash_number(typed, stored):
    assert normalize_plate(typed) == stored
