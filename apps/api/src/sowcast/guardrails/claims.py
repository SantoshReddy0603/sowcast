import re
import unicodedata
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, ConfigDict, Field

from sowcast.guardrails.prose import prose_error
from sowcast.i18n.render import Language


class Fact(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    id: str
    date: str
    latitude: float
    longitude: float
    value: float
    unit: str
    source_url: str
    fetched_at: str
    window_start: str | None = None
    window_end: str | None = None
    supporting_urls: tuple[str, ...] = ()
    label: str | None = None


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    text: str = Field(min_length=1, max_length=1200)
    evidence_id: str
    date: str
    latitude: float
    longitude: float


class Verification(BaseModel):
    passed: bool
    discrepancies: tuple[str, ...]


UNITS: dict[str, tuple[str, ...]] = {
    "mm": (
        "millimetres",
        "millimeters",
        "millimetre",
        "millimeter",
        "mm",
        "मिलीमीटर",
        "मिलिमीटर",
        "ಮಿಲಿಮೀಟರ್",
        "మిల్లీమీటర్లు",
        "మిల్లీమీటర్",
        "மில்லிமீட்டர்",
        "மி.மீ.",
    ),
    "degc": (
        "degrees celsius",
        "degree celsius",
        "°c",
        "degc",
        "सेल्सियस",
        "डिग्री सेल्सियस",
        "ಅಂಶ ಸೆಲ್ಸಿಯಸ್",
        "ಡಿಗ್ರಿ ಸೆಲ್ಸಿಯಸ್",
        "డిగ్రీల సెల్సియస్",
        "డిగ్రీ సెల్సియస్",
        "டிகிரி செல்சியஸ்",
        "அலகு செல்சியஸ்",
    ),
    "day": ("days", "day", "दिन", "दिवस", "ದಿನಗಳು", "ದಿನ", "రోజులు", "రోజు", "நாட்கள்", "நாள்"),
    "percent": ("percent", "%", "प्रतिशत", "टक्के", "ಶೇಕಡಾ", "శాతం", "சதவீதம்"),
    "dimensionless": ("dimensionless",),
    "m3/s": ("m³/s", "m3/s"),
    "km/h": ("km/h", "kilometres per hour", "किलोमीटर प्रति घंटा"),
}
NUMBER = re.compile(r"(?<![\w.])[+-]?\d+(?:\.\d+)?(?![\w.])")
QUANTITY = re.compile(r"(?<![\w.])([+-]?\d+(?:\.\d+)?)\s*([a-z%][a-z0-9/%]*)(?!\w)")


def normalize(text: str) -> str:
    translated: list[str] = []
    for character in unicodedata.normalize("NFKC", text).casefold():
        try:
            translated.append(str(unicodedata.decimal(character)))
        except ValueError:
            translated.append(character)
    value = "".join(translated).replace("−", "-")
    replacements = sorted(
        ((alias, unit) for unit, aliases in UNITS.items() for alias in aliases),
        key=lambda pair: len(pair[0]),
        reverse=True,
    )
    for alias, unit in replacements:
        value = re.sub(
            r"(?<!\w)" + re.escape(unicodedata.normalize("NFKC", alias).casefold()) + r"(?!\w)",
            unit,
            value,
        )
    return value


def verify_quantities(claims: tuple[Claim, ...], facts: dict[str, Fact]) -> Verification:
    discrepancies: list[str] = []
    for index, claim in enumerate(claims):
        fact = facts.get(claim.evidence_id)
        if fact is None:
            discrepancies.append(f"Claim {index}: unknown evidence reference")
            continue
        if (
            claim.date != fact.date
            or claim.latitude != fact.latitude
            or claim.longitude != fact.longitude
        ):
            discrepancies.append(f"Claim {index}: evidence date or location mismatch")
            continue
        text = normalize(claim.text)
        if re.search(
            r"\b(zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
            r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|"
            r"thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|million)\b"
            r"|एक|दो|तीन|पांच|पाँच|दस|शंभर|दोन|तीन|ಒಂದು|ಎರಡು|ಮೂರು|ಐದು"
            r"|ఒకటి|రెండు|మూడు|ఐదు|ஒன்று|இரண்டு|மூன்று|ஐந்து",
            text,
        ):
            discrepancies.append(f"Claim {index}: word quantities require code rendering")
        unit = normalize(fact.unit)
        if unit == "°c":
            unit = "degc"
        quantities = list(QUANTITY.finditer(text))
        for supported_unit in UNITS:
            for token in re.finditer(r"(?<!\w)" + re.escape(supported_unit) + r"(?!\w)", text):
                if not any(match.start() <= token.start() < match.end() for match in quantities):
                    discrepancies.append(f"Claim {index}: unit without parsed quantity")
        if any(
            character.isdecimal()
            and not any(match.start() <= position < match.end() for match in quantities)
            for position, character in enumerate(text)
        ):
            discrepancies.append(f"Claim {index}: unparsed numeric content")
        numeric_text = NUMBER.findall(text)
        if len(quantities) != len(numeric_text):
            discrepancies.append(f"Claim {index}: numeric claim lacks a supported unit")
            continue
        if re.search(r"\d\s*[,/–—]\s*\d|\d[eE][+-]?\d", text):
            discrepancies.append(f"Claim {index}: ambiguous numeric notation")
        for quantity in quantities:
            try:
                matches = Decimal(quantity[1]) == Decimal(str(fact.value))
            except InvalidOperation:
                matches = False
            if not matches or quantity[2] != unit:
                discrepancies.append(f"Claim {index}: unsupported numeric value or unit")
        if any(character.isnumeric() and not character.isdecimal() for character in text):
            discrepancies.append(f"Claim {index}: unsupported numeric notation")
    return Verification(passed=not discrepancies, discrepancies=tuple(discrepancies))


def verify(
    claims: tuple[Claim, ...], facts: dict[str, Fact], language: Language = "en"
) -> Verification:
    discrepancies = list(verify_quantities(claims, facts).discrepancies)
    for index, claim in enumerate(claims):
        error = prose_error(claim.text, language)
        if error:
            discrepancies.append(f"Claim {index}: {error}")
    return Verification(passed=not discrepancies, discrepancies=tuple(discrepancies))
