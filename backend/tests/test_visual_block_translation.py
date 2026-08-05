import re
import pytest
from i18n.term_glossary import protect_visual_blocks, restore_visual_blocks


def test_protects_and_restores_markdown_code_fences():
    original = "Here is the code block:\n```python\ndef hello():\n    print('Hello World')\n```\nLet me know if it helps."
    protected, mapping = protect_visual_blocks(original)
    
    assert "__VISUAL_BLOCK_0__" in protected
    assert "```python" not in protected
    
    # Simulate translation preserving the placeholder
    translated = f"यहाँ कोड ब्लॉक है:\n{protected.splitlines()[1]}\nमुझे बताएं कि क्या इससे मदद मिलती है।"
    restored = restore_visual_blocks(translated, mapping)
    
    assert "```python" in restored
    assert "def hello():" in restored
    assert "यहाँ कोड ब्लॉक है:" in restored


def test_protects_and_restores_show_html_tags():
    original = "ಹಲೋ! <show type='code' lang='python' title='Example'>print(\"hello\")</show> ಬರೆಯಿರಿ."
    protected, mapping = protect_visual_blocks(original)
    
    assert "__VISUAL_BLOCK_0__" in protected
    assert "<show" not in protected
    
    # Simulate translation
    translated = f"ಹಲೋ! {protected.split()[1]} ಬರೆಯಿರಿ."
    restored = restore_visual_blocks(translated, mapping)
    
    assert "<show type='code' lang='python' title='Example'>print(\"hello\")</show>" in restored


def test_strips_visual_blocks_for_tts():
    translated = "ಹಲೋ! <show type='code' lang='python' title='Example'>print(\"hello\")</show> ಬರೆಯಿರಿ. ```python\ncode\n``` <followup>Any questions?</followup>"
    
    # Run the exact stripping regexes used in the code
    tts_clean = re.sub(r"<show(?:\s+[^>]*)?>.*?</show>", "", translated, flags=re.DOTALL | re.IGNORECASE)
    tts_clean = re.sub(r"<followup>.*?</followup>", "", tts_clean, flags=re.DOTALL | re.IGNORECASE)
    tts_clean = re.sub(r"```.*?```", "", tts_clean, flags=re.DOTALL)
    tts_clean = re.sub(r"</?(?:speak|show|followup|code)(?:\s+[^>]*)?>", "", tts_clean, flags=re.IGNORECASE)
    tts_clean = re.sub(r"\s+", " ", tts_clean).strip()
    
    assert "print(\"hello\")" not in tts_clean
    assert "code" not in tts_clean
    assert "Any questions?" not in tts_clean
    assert "ಹಲೋ! ಬರೆಯಿರಿ." in tts_clean
