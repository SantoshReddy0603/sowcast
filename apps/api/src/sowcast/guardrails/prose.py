import unicodedata

from sowcast.i18n.render import Language

SENTENCES: dict[Language, str] = {
    "en": (
        "Review the supplied field evidence before deciding. "
        "Review this forecast rainfall evidence with local extension advice. "
        "Check conditions before acting."
    ),
    "hi": "निर्णय से पहले उपलब्ध खेत और मौसम के साक्ष्य देखें। स्थानीय कृषि अधिकारी से सलाह लें।",
    "kn": "ನಿರ್ಧಾರ ಮಾಡುವ ಮೊದಲು ಲಭ್ಯವಿರುವ ಹೊಲ ಮತ್ತು ಹವಾಮಾನ ಮಾಹಿತಿಯನ್ನು ಪರಿಶೀಲಿಸಿ. ಸ್ಥಳೀಯ ಕೃಷಿ ಅಧಿಕಾರಿಗಳ ಸಲಹೆ ಪಡೆಯಿರಿ.",
    "te": (
        "నిర్ణయం తీసుకునే ముందు అందుబాటులో ఉన్న పొలం మరియు వాతావరణ సమాచారాన్ని పరిశీలించండి. "
        "స్థానిక వ్యవసాయ అధికారుల సలహా తీసుకోండి."
    ),
    "ta": (
        "முடிவு எடுக்கும் முன் கிடைக்கும் வயல் மற்றும் வானிலை தகவல்களை சரிபார்க்கவும். "
        "உள்ளூர் வேளாண் அலுவலரின் ஆலோசனையை பெறவும்."
    ),
    "mr": "निर्णय घेण्यापूर्वी उपलब्ध शेत आणि हवामान माहिती तपासा. स्थानिक कृषी अधिकाऱ्यांचा सल्ला घ्या.",
}


def words(text: str) -> tuple[str, ...]:
    tokens: list[str] = []
    current: list[str] = []
    for char in unicodedata.normalize("NFC", text).casefold():
        if unicodedata.category(char)[0] in {"L", "M"}:
            current.append(char)
        elif current:
            tokens.append("".join(current))
            current = []
    if current:
        tokens.append("".join(current))
    return tuple(tokens)


def vocabulary(language: Language) -> tuple[str, ...]:
    return tuple(sorted(set(words(SENTENCES[language]))))


def prose_error(text: str, language: Language) -> str | None:
    if any(char.isnumeric() for char in text):
        return "Quantities must be rendered from structured evidence by code"
    if any(
        unicodedata.category(char)[0] not in {"L", "M", "P", "Z"} and char not in "\n\r\t"
        for char in text
    ):
        return "Unsupported explanatory characters"
    tokens = words(text)
    if not tokens or not set(tokens).issubset(vocabulary(language)):
        return "Unsupported explanatory vocabulary; use the supplied words without quantities"
    return None
