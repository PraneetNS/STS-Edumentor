import re

SSML_PATTERNS = [
    r'<speak[^>]*>',
    r'</speak>',
    r'<break[^>]*/?>',
    r'<prosody[^>]*>',
    r'</prosody>',
    r'<emphasis[^>]*>',
    r'</emphasis>',
    r'<phoneme[^>]*>',
    r'<say-as[^>]*>',
    r'<sub[^>]*>',
    r'<voice[^>]*>',
]

def strip_ssml(text: str) -> str:
    for pattern in SSML_PATTERNS:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    return text.strip()

def strip_template_leaks(text: str) -> str:
    text = re.sub(r'\{[a-zA-Z_][a-zA-Z0-9_]*\}', '', text)
    return text.strip()

def strip_markdown(text: str) -> str:
    text = re.sub(r'\*+', '', text)
    text = re.sub(r'_+', '', text)
    text = re.sub(r'`+', '', text)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'-\s+', '', text)
    return text.strip()

def cap_for_voice(text: str) -> str:
    return text

def sanitise(text: str) -> str:
    text = strip_ssml(text)          # NEW — step 0
    text = strip_template_leaks(text)
    text = strip_markdown(text)
    text = cap_for_voice(text)
    text = text.strip()
    if not text:
        text = "Can you tell me a bit more about what you are working on?"
    return text
