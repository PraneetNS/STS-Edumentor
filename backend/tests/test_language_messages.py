from speech.language_messages import language_switch_confirmation


def test_language_switch_confirmation_uses_selected_language():
    assert "हिंदी" in language_switch_confirmation("hindi")
    assert "मराठीत" in language_switch_confirmation("marathi")
    assert "ಕನ್ನಡದಲ್ಲಿ" in language_switch_confirmation("kannada")
