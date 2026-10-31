from datetime import date
from decimal import Decimal
from typing import Literal

Language = Literal["en", "hi", "kn", "te", "ta", "mr"]
DIGITS = {
    "en": "0123456789",
    "hi": "०१२३४५६७८९",
    "mr": "०१२३४५६७८९",
    "kn": "೦೧೨೩೪೫೬೭೮೯",
    "te": "౦౧౨౩౪౫౬౭౮౯",
    "ta": "௦௧௨௩௪௫௬௭௮௯",
}


def number(value: float, language: Language) -> str:
    rendered = format(Decimal(str(value)), "f")
    return rendered.translate(str.maketrans(DIGITS["en"], DIGITS[language]))


def calendar_date(value: date, language: Language) -> str:
    return value.isoformat().translate(str.maketrans(DIGITS["en"], DIGITS[language]))


def measurement(value: float, unit: str, language: Language) -> str:
    return f"{number(value, language)} {unit}"
