import pytest
from i18n.term_protector import mask_protected_terms, restore_protected_terms

def test_term_protection_roundtrip():
    text = "Explain machine learning and recursion step-by-step."
    
    # Mask
    masked, mapping = mask_protected_terms(text)
    assert "__TERM_0__" in masked
    assert "__TERM_1__" in masked
    assert "machine learning" not in masked.lower()
    assert "recursion" not in masked.lower()
    
    # Restore
    restored = restore_protected_terms(masked, mapping)
    # Case might be preserved or returned to original depending on mapping behavior
    assert "machine learning" in restored.lower()
    assert "recursion" in restored.lower()
