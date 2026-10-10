"""Nationalities picked from a list (the driver's app and the control panel; nothing is typed). Sovereign states and
Palestine, named after CLDR (ar, en); the employee record keeps the Arabic name, as the office writes it."""

import unicodedata

COUNTRIES: tuple[tuple[str, str, str], ...] = (  # ISO 3166-1 code, Arabic, English
    ("AD", "أندورا", "Andorra"),
    ("AE", "الإمارات العربية المتحدة", "United Arab Emirates"),
    ("AF", "أفغانستان", "Afghanistan"),
    ("AG", "أنتيغوا وبربودا", "Antigua and Barbuda"),
    ("AL", "ألبانيا", "Albania"),
    ("AM", "أرمينيا", "Armenia"),
    ("AO", "أنغولا", "Angola"),
    ("AR", "الأرجنتين", "Argentina"),
    ("AT", "النمسا", "Austria"),
    ("AU", "أستراليا", "Australia"),
    ("AZ", "أذربيجان", "Azerbaijan"),
    ("BA", "البوسنة والهرسك", "Bosnia and Herzegovina"),
    ("BB", "بربادوس", "Barbados"),
    ("BD", "بنغلاديش", "Bangladesh"),
    ("BE", "بلجيكا", "Belgium"),
    ("BF", "بوركينا فاسو", "Burkina Faso"),
    ("BG", "بلغاريا", "Bulgaria"),
    ("BH", "البحرين", "Bahrain"),
    ("BI", "بوروندي", "Burundi"),
    ("BJ", "بنين", "Benin"),
    ("BN", "بروناي", "Brunei"),
    ("BO", "بوليفيا", "Bolivia"),
    ("BR", "البرازيل", "Brazil"),
    ("BS", "جزر البهاما", "Bahamas"),
    ("BT", "بوتان", "Bhutan"),
    ("BW", "بوتسوانا", "Botswana"),
    ("BY", "بيلاروس", "Belarus"),
    ("BZ", "بليز", "Belize"),
    ("CA", "كندا", "Canada"),
    ("CD", "الكونغو الديمقراطية", "DR Congo"),
    ("CF", "جمهورية أفريقيا الوسطى", "Central African Republic"),
    ("CG", "الكونغو", "Congo"),
    ("CH", "سويسرا", "Switzerland"),
    ("CI", "ساحل العاج", "Côte d’Ivoire"),
    ("CL", "تشيلي", "Chile"),
    ("CM", "الكاميرون", "Cameroon"),
    ("CN", "الصين", "China"),
    ("CO", "كولومبيا", "Colombia"),
    ("CR", "كوستاريكا", "Costa Rica"),
    ("CU", "كوبا", "Cuba"),
    ("CV", "الرأس الأخضر", "Cape Verde"),
    ("CY", "قبرص", "Cyprus"),
    ("CZ", "التشيك", "Czechia"),
    ("DE", "ألمانيا", "Germany"),
    ("DJ", "جيبوتي", "Djibouti"),
    ("DK", "الدنمارك", "Denmark"),
    ("DM", "دومينيكا", "Dominica"),
    ("DO", "جمهورية الدومينيكان", "Dominican Republic"),
    ("DZ", "الجزائر", "Algeria"),
    ("EC", "الإكوادور", "Ecuador"),
    ("EE", "إستونيا", "Estonia"),
    ("EG", "مصر", "Egypt"),
    ("ER", "إريتريا", "Eritrea"),
    ("ES", "إسبانيا", "Spain"),
    ("ET", "إثيوبيا", "Ethiopia"),
    ("FI", "فنلندا", "Finland"),
    ("FJ", "فيجي", "Fiji"),
    ("FM", "ميكرونيزيا", "Micronesia"),
    ("FR", "فرنسا", "France"),
    ("GA", "الغابون", "Gabon"),
    ("GB", "المملكة المتحدة", "United Kingdom"),
    ("GD", "غرينادا", "Grenada"),
    ("GE", "جورجيا", "Georgia"),
    ("GH", "غانا", "Ghana"),
    ("GM", "غامبيا", "Gambia"),
    ("GN", "غينيا", "Guinea"),
    ("GQ", "غينيا الاستوائية", "Equatorial Guinea"),
    ("GR", "اليونان", "Greece"),
    ("GT", "غواتيمالا", "Guatemala"),
    ("GW", "غينيا بيساو", "Guinea-Bissau"),
    ("GY", "غيانا", "Guyana"),
    ("HK", "هونغ كونغ", "Hong Kong"),
    ("HN", "هندوراس", "Honduras"),
    ("HR", "كرواتيا", "Croatia"),
    ("HT", "هايتي", "Haiti"),
    ("HU", "هنغاريا", "Hungary"),
    ("ID", "إندونيسيا", "Indonesia"),
    ("IE", "أيرلندا", "Ireland"),
    ("IN", "الهند", "India"),
    ("IQ", "العراق", "Iraq"),
    ("IR", "إيران", "Iran"),
    ("IS", "آيسلندا", "Iceland"),
    ("IT", "إيطاليا", "Italy"),
    ("JM", "جامايكا", "Jamaica"),
    ("JO", "الأردن", "Jordan"),
    ("JP", "اليابان", "Japan"),
    ("KE", "كينيا", "Kenya"),
    ("KG", "قيرغيزستان", "Kyrgyzstan"),
    ("KH", "كمبوديا", "Cambodia"),
    ("KI", "كيريباتي", "Kiribati"),
    ("KM", "جزر القمر", "Comoros"),
    ("KN", "سانت كيتس ونيفيس", "Saint Kitts and Nevis"),
    ("KP", "كوريا الشمالية", "North Korea"),
    ("KR", "كوريا الجنوبية", "South Korea"),
    ("KW", "الكويت", "Kuwait"),
    ("KZ", "كازاخستان", "Kazakhstan"),
    ("LA", "لاوس", "Laos"),
    ("LB", "لبنان", "Lebanon"),
    ("LC", "سانت لوسيا", "Saint Lucia"),
    ("LI", "ليختنشتاين", "Liechtenstein"),
    ("LK", "سريلانكا", "Sri Lanka"),
    ("LR", "ليبيريا", "Liberia"),
    ("LS", "ليسوتو", "Lesotho"),
    ("LT", "ليتوانيا", "Lithuania"),
    ("LU", "لوكسمبورغ", "Luxembourg"),
    ("LV", "لاتفيا", "Latvia"),
    ("LY", "ليبيا", "Libya"),
    ("MA", "المغرب", "Morocco"),
    ("MC", "موناكو", "Monaco"),
    ("MD", "مولدوفا", "Moldova"),
    ("ME", "الجبل الأسود", "Montenegro"),
    ("MG", "مدغشقر", "Madagascar"),
    ("MH", "جزر مارشال", "Marshall Islands"),
    ("MK", "مقدونيا الشمالية", "North Macedonia"),
    ("ML", "مالي", "Mali"),
    ("MM", "ميانمار", "Myanmar"),
    ("MN", "منغوليا", "Mongolia"),
    ("MO", "ماكاو", "Macao"),
    ("MR", "موريتانيا", "Mauritania"),
    ("MT", "مالطا", "Malta"),
    ("MU", "موريشيوس", "Mauritius"),
    ("MV", "جزر المالديف", "Maldives"),
    ("MW", "ملاوي", "Malawi"),
    ("MX", "المكسيك", "Mexico"),
    ("MY", "ماليزيا", "Malaysia"),
    ("MZ", "موزمبيق", "Mozambique"),
    ("NA", "ناميبيا", "Namibia"),
    ("NE", "النيجر", "Niger"),
    ("NG", "نيجيريا", "Nigeria"),
    ("NI", "نيكاراغوا", "Nicaragua"),
    ("NL", "هولندا", "Netherlands"),
    ("NO", "النرويج", "Norway"),
    ("NP", "نيبال", "Nepal"),
    ("NR", "ناورو", "Nauru"),
    ("NZ", "نيوزيلندا", "New Zealand"),
    ("OM", "عُمان", "Oman"),
    ("PA", "بنما", "Panama"),
    ("PE", "بيرو", "Peru"),
    ("PG", "بابوا غينيا الجديدة", "Papua New Guinea"),
    ("PH", "الفلبين", "Philippines"),
    ("PK", "باكستان", "Pakistan"),
    ("PL", "بولندا", "Poland"),
    ("PS", "فلسطين", "Palestine"),
    ("PT", "البرتغال", "Portugal"),
    ("PW", "بالاو", "Palau"),
    ("PY", "باراغواي", "Paraguay"),
    ("QA", "قطر", "Qatar"),
    ("RO", "رومانيا", "Romania"),
    ("RS", "صربيا", "Serbia"),
    ("RU", "روسيا", "Russia"),
    ("RW", "رواندا", "Rwanda"),
    ("SA", "المملكة العربية السعودية", "Saudi Arabia"),
    ("SB", "جزر سليمان", "Solomon Islands"),
    ("SC", "سيشل", "Seychelles"),
    ("SD", "السودان", "Sudan"),
    ("SE", "السويد", "Sweden"),
    ("SG", "سنغافورة", "Singapore"),
    ("SI", "سلوفينيا", "Slovenia"),
    ("SK", "سلوفاكيا", "Slovakia"),
    ("SL", "سيراليون", "Sierra Leone"),
    ("SM", "سان مارينو", "San Marino"),
    ("SN", "السنغال", "Senegal"),
    ("SO", "الصومال", "Somalia"),
    ("SR", "سورينام", "Suriname"),
    ("SS", "جنوب السودان", "South Sudan"),
    ("ST", "ساو تومي وبرينسيبي", "São Tomé and Príncipe"),
    ("SV", "السلفادور", "El Salvador"),
    ("SY", "سوريا", "Syria"),
    ("SZ", "إسواتيني", "Eswatini"),
    ("TD", "تشاد", "Chad"),
    ("TG", "توغو", "Togo"),
    ("TH", "تايلاند", "Thailand"),
    ("TJ", "طاجيكستان", "Tajikistan"),
    ("TL", "تيمور الشرقية", "Timor-Leste"),
    ("TM", "تركمانستان", "Turkmenistan"),
    ("TN", "تونس", "Tunisia"),
    ("TO", "تونغا", "Tonga"),
    ("TR", "تركيا", "Türkiye"),
    ("TT", "ترينيداد وتوباغو", "Trinidad and Tobago"),
    ("TV", "توفالو", "Tuvalu"),
    ("TW", "تايوان", "Taiwan"),
    ("TZ", "تنزانيا", "Tanzania"),
    ("UA", "أوكرانيا", "Ukraine"),
    ("UG", "أوغندا", "Uganda"),
    ("US", "الولايات المتحدة", "United States"),
    ("UY", "أورغواي", "Uruguay"),
    ("UZ", "أوزبكستان", "Uzbekistan"),
    ("VA", "الفاتيكان", "Vatican City"),
    ("VC", "سانت فنسنت وجزر غرينادين", "Saint Vincent and Grenadines"),
    ("VE", "فنزويلا", "Venezuela"),
    ("VN", "فيتنام", "Vietnam"),
    ("VU", "فانواتو", "Vanuatu"),
    ("WS", "ساموا", "Samoa"),
    ("YE", "اليمن", "Yemen"),
    ("ZA", "جنوب أفريقيا", "South Africa"),
    ("ZM", "زامبيا", "Zambia"),
    ("ZW", "زيمبابوي", "Zimbabwe"),
)


def nationalities() -> list[dict]:
    return [{"value": ar, "ar": ar, "en": en} for _, ar, en in COUNTRIES]


def is_nationality(value: str) -> bool:
    return value in _VALUES


# What HR sheets write instead of the country's name, where the regular Arabic form (below) does not give it
_ALIASES = {
    "بنغالي": "BD",
    "بنجالي": "BD",
    "بنجلاديشي": "BD",
    "بنجلاديش": "BD",
    "سيريلانكي": "LK",
    "سعودي": "SA",
    "اماراتي": "AE",
    "امريكي": "US",
    "بريطاني": "GB",
    "افغاني": "AF",
    "نمساوي": "AT",
    "indian": "IN",
    "egyptian": "EG",
    "pakistani": "PK",
    "bangladeshi": "BD",
    "bengali": "BD",
    "nepali": "NP",
    "nepalese": "NP",
    "sri lankan": "LK",
    "filipino": "PH",
    "syrian": "SY",
    "jordanian": "JO",
    "lebanese": "LB",
    "kuwaiti": "KW",
    "saudi": "SA",
    "emirati": "AE",
    "iraqi": "IQ",
    "iranian": "IR",
    "afghan": "AF",
    "sudanese": "SD",
    "yemeni": "YE",
    "palestinian": "PS",
    "ethiopian": "ET",
    "kenyan": "KE",
    "ugandan": "UG",
    "indonesian": "ID",
    "chinese": "CN",
    "american": "US",
    "british": "GB",
    "turkish": "TR",
    "moroccan": "MA",
    "tunisian": "TN",
    "algerian": "DZ",
    "omani": "OM",
    "qatari": "QA",
    "bahraini": "BH",
    "nigerian": "NG",
    "ghanaian": "GH",
}


def _fold(text: str) -> str:
    """One spelling: no diacritics or tatweel, one alef (hamza forms), taa marbuta as haa, alef maqsura as yaa,
    lower case, single spaces."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c) and c != chr(0x0640))
    return " ".join(text.replace("ة", "ه").replace("ى", "ي").lower().split())


def _demonym(ar: str) -> str | None:
    """The regular Arabic adjective: الهند → هندي, سوريا → سوري, سريلانكا → سريلانكي."""
    name = _fold(ar)
    if " " in name:
        return None
    name = name.removeprefix("ال")
    for end in ("يا", "ا", "ه"):
        if name.endswith(end):
            name = name[: -len(end)]
            break
    return name + "ي"


def _index() -> dict[str, str]:
    by_code = {code: ar for code, ar, _ in COUNTRIES}
    index: dict[str, str] = {}
    demonyms: dict[str, set[str]] = {}
    for _, ar, en in COUNTRIES:
        for key in (_fold(ar), _fold(ar).removeprefix("ال"), _fold(en)):
            index[key] = ar
        if adjective := _demonym(ar):
            demonyms.setdefault(adjective, set()).add(ar)
    index |= {k: next(iter(v)) for k, v in demonyms.items() if len(v) == 1 and k not in index}  # never a guess
    index |= {_fold(alias): by_code[code] for alias, code in _ALIASES.items()}
    return index


_VALUES = {ar for _, ar, _ in COUNTRIES}
_INDEX = _index()


def match(text: str) -> str | None:
    """The list's value for what a sheet says: the country's name in Arabic or English, or its adjective ("هندي",
    "مصرية", "Indian"). None when it is not clear."""
    key = _fold(text)
    if key.endswith("يه"):  # the feminine adjective: هندية → هندي
        key = key[:-1]
    return _INDEX.get(key)
