from datetime import date

import pytest

from sowcast.guardrails.claims import Claim, Fact, normalize, verify, verify_quantities
from sowcast.i18n.render import calendar_date, measurement


def fact():
    return Fact(
        id="rain",
        date="2026-10-30",
        latitude=12.97,
        longitude=77.59,
        value=12.5,
        unit="mm",
        source_url="https://open-meteo.com/",
        fetched_at="2026-10-30",
    )


def claim(text, **changes):
    values = dict(text=text, evidence_id="rain", date="2026-10-30", latitude=12.97, longitude=77.59)
    return Claim(**(values | changes))


@pytest.mark.parametrize(
    "text",
    [
        "12.5 millimetres",
        "१२.५ मिलीमीटर",
        "१२.५ मिलिमीटर",
        "೧೨.೫ ಮಿಲಿಮೀಟರ್",
        "౧౨.౫ మిల్లీమీటర్లు",
        "௧௨.௫ மில்லிமீட்டர்",
    ],
)
def test_native_digits_and_unit_words(text):
    assert normalize(text) == "12.5 mm"
    assert verify_quantities((claim(text),), {"rain": fact()}).passed


@pytest.mark.parametrize(
    "text",
    [
        "13 mm",
        "12.5 °C",
        "12.5",
        "12.5 bananas",
        "1,250 mm",
        "1e2 mm",
        "12–13 mm",
        "½ mm",
        "१२.६ मिलीमीटर",
        "13mm",
        "-12.5 mm",
        "one millimetre",
    ],
)
def test_unsupported_numeric_claims(text):
    assert not verify((claim(text),), {"rain": fact()}).passed


@pytest.mark.parametrize(
    "change",
    [{"date": "2026-10-31"}, {"latitude": 13.0}, {"longitude": 78.0}, {"evidence_id": "elsewhere"}],
)
def test_binding_to_this_date_place_and_reference(change):
    assert not verify((claim("12.5 mm", **change),), {"rain": fact()}).passed


@pytest.mark.parametrize("language", ["en", "hi", "kn", "te", "ta", "mr"])
def test_code_rendering_roundtrip(language):
    assert normalize(measurement(12.5, "mm", language)) == "12.5 mm"
    assert normalize(calendar_date(date(2026, 10, 30), language)) == "2026-10-30"


@pytest.mark.parametrize(
    "text", ["twenty millimetres", "zero mm", "999雨", "౧౨౫తెలుగు", "12\u200b5 mm"]
)
def test_word_units_and_unparsed_digits_fail_closed(text):
    assert not verify((claim(text),), {"rain": fact()}).passed


@pytest.mark.parametrize(
    "text,unit",
    [
        ("12.5 degrees celsius", "°C"),
        ("१२.५ डिग्री सेल्सियस", "°C"),
        ("೧೨.೫ ಡಿಗ್ರಿ ಸೆಲ್ಸಿಯಸ್", "°C"),
        ("౧౨.౫ డిగ్రీ సెల్సియస్", "°C"),
        ("௧௨.௫ டிகிரி செல்சியஸ்", "°C"),
        ("१२.५ सेल्सियस", "°C"),
        ("12.5 percent", "%"),
        ("१२.५ प्रतिशत", "%"),
        ("೧೨.೫ ಶೇಕಡಾ", "%"),
        ("౧౨.౫ శాతం", "%"),
        ("௧௨.௫ சதவீதம்", "%"),
        ("१२.५ टक्के", "%"),
        ("12.5 days", "day"),
        ("१२.५ दिन", "day"),
        ("೧೨.೫ ದಿನಗಳು", "day"),
        ("౧౨.౫ రోజులు", "day"),
        ("௧௨.௫ நாட்கள்", "day"),
        ("१२.५ दिवस", "day"),
    ],
)
def test_units_across_languages(text, unit):
    evidence = fact().model_copy(update={"unit": unit})
    assert verify_quantities((claim(text),), {"rain": evidence}).passed


def test_blank_claim_rejected():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        claim("  ")


@pytest.mark.parametrize(
    "text",
    [
        "बीस लीटर सिंचाई करें",
        "ಇಪ್ಪತ್ತು ಲೀಟರ್",
        "ఇరవై లీటర్లు",
        "இருபது லிட்டர்",
        "वीस लिटर",
        "a dozen litres",
        "Ⅻ litres",
        "XII litres",
        "12.5 mm",
        "१२.५ मिलीमीटर",
        "೧೨.೫ ಮಿಲಿಮೀಟರ್",
        "౧౨.౫ మిల్లీమీటర్లు",
        "௧௨.௫ மில்லிமீட்டர்",
        "Review\u200d the supplied field evidence.",
        "Review the supplied field evidence. litreee",
        "Water the field before deciding.",
    ],
)
def test_explanatory_prose_rejects_quantities_and_unrecognized_words(text):
    assert not verify((claim(text),), {"rain": fact()}).passed


@pytest.mark.parametrize("language", ["en", "hi", "kn", "te", "ta", "mr"])
def test_code_only_values_with_supported_explanatory_language(language):
    from sowcast.guardrails.prose import SENTENCES

    assert verify((claim(SENTENCES[language]),), {"rain": fact()}, language).passed
    assert not verify(
        (claim(measurement(12.5, "mm", language)),), {"rain": fact()}, language
    ).passed


def test_safe_prose_still_requires_current_date_and_location():
    for change in ({"date": "1900-01-01"}, {"latitude": 13}, {"evidence_id": "wrong"}):
        assert not verify(
            (claim("Review the supplied field evidence.", **change),), {"rain": fact()}
        ).passed
