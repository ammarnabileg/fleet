"""Nationalities: one list for the driver's app and the control panel, and what a client's sheet writes matched to it
(the country's name in Arabic or English, or its adjective), never guessed."""

import pytest

from app.modules.people import countries


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("الهند", "الهند"),
        ("هند", "الهند"),
        ("هندي", "الهند"),
        ("هندية", "الهند"),
        ("India", "الهند"),
        (" INDIAN ", "الهند"),
        ("مصري", "مصر"),
        ("أردني", "الأردن"),
        ("اردنى", "الأردن"),
        ("سوري", "سوريا"),
        ("سريلانكي", "سريلانكا"),
        ("Sri Lankan", "سريلانكا"),
        ("فلبيني", "الفلبين"),
        ("Filipino", "الفلبين"),
        ("بنغالي", "بنغلاديش"),
        ("بنجلاديشي", "بنغلاديش"),
        ("نيبالي", "نيبال"),
        ("عماني", "عُمان"),
        ("سعودي", "المملكة العربية السعودية"),
        ("Côte d’Ivoire", "ساحل العاج"),
        ("مريخي", None),
        ("", None),
    ],
)
def test_what_a_sheet_writes_is_matched_to_the_list(text, value):
    assert countries.match(text) == value


def test_every_value_is_a_listed_country_and_no_adjective_is_a_guess():
    values = {n["value"] for n in countries.nationalities()}
    assert len(values) == len(countries.COUNTRIES) == 197
    assert all(countries.is_nationality(v) for v in values) and not countries.is_nationality("هندي")
    assert set(countries._INDEX.values()) <= values
    # two countries with the same regular adjective give none: النيجر / نيجيريا differ, so both match
    assert (countries.match("نيجري"), countries.match("نيجيري")) == ("النيجر", "نيجيريا")
