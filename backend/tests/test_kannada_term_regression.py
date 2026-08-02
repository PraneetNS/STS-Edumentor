import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from i18n.term_glossary import protect_terms, restore_terms

class TestKannadaTermRegression(unittest.TestCase):
    def test_kannada_recursion_protection(self):
        """
        Verifies that 'ರಿಕರ್ಷನ್' is properly identified and masked as 'recursion'
        and restored correctly in both English (mode='english') and native (mode='native') modes.
        """
        input_text = "ರಿಕರ್ಷನ್ ಎಂದರೇನು ಮತ್ತು ಅದರ ಒಂದು ಉದಾಹರಣೆ ಕೊಡಿ"
        
        # 1. Protection (passing 'kannada' as query language)
        protected, mapping = protect_terms(input_text, "kannada")
        print("Protected text:", repr(protected))
        print("Mapping:", mapping)
        
        # Verify that placeholder exists
        self.assertEqual(len(mapping), 1)
        placeholder = list(mapping.keys())[0]
        self.assertIn(placeholder, protected)
        
        # Verify that placeholder maps specifically to 'recursion' (English root)
        self.assertEqual(mapping[placeholder].lower(), "recursion")
        
        # 2. English restoration (used before sending query to LLM)
        restored_en = restore_terms(protected, mapping, mode="english", target_language="kannada")
        print("Restored English:", restored_en)
        # Should translate placeholder back to English root: 'recursion'
        self.assertIn("recursion", restored_en.lower())
        self.assertNotIn("ರಿಕರ್ಷನ್", restored_en)
        
        # 3. Native Kannada restoration (used in Stage 5 back-translation)
        restored_native = restore_terms(protected, mapping, mode="native", target_language="kannada")
        print("Restored Native:", restored_native)
        # Should translate placeholder back to Kannada transliteration: 'ರಿಕರ್ಷನ್'
        self.assertIn("ರಿಕರ್ಷನ್", restored_native)
        self.assertNotIn("recursion", restored_native.lower())

    def test_marathi_recursion_protection(self):
        """
        Verifies that 'रिकर्सन' is properly identified and masked as 'recursion'
        and restored correctly in both English (mode='english') and native (mode='native') modes for Marathi.
        """
        input_text = "रिकर्सन म्हणजे काय आणि त्याचे एक उदाहरण द्या"
        
        # 1. Protection (passing 'marathi' as query language)
        protected, mapping = protect_terms(input_text, "marathi")
        print("Protected Marathi text:", repr(protected))
        print("Mapping:", mapping)
        
        # Verify that placeholder exists
        self.assertEqual(len(mapping), 1)
        placeholder = list(mapping.keys())[0]
        self.assertIn(placeholder, protected)
        
        # Verify that placeholder maps specifically to 'recursion' (English root)
        self.assertEqual(mapping[placeholder].lower(), "recursion")
        
        # 2. English restoration
        restored_en = restore_terms(protected, mapping, mode="english", target_language="marathi")
        print("Restored English (Marathi):", restored_en)
        self.assertIn("recursion", restored_en.lower())
        self.assertNotIn("रिकर्सन", restored_en)
        
        # 3. Native Marathi restoration
        restored_native = restore_terms(protected, mapping, mode="native", target_language="marathi")
        print("Restored Native (Marathi):", restored_native)
        self.assertIn("रिकर्शन", restored_native)
        self.assertNotIn("recursion", restored_native.lower())

    def test_everyday_conversational_false_positives(self):
        """
        Stress-tests the glossary protection system against everyday conversational
        phrases to ensure zero false positives and no accidental technical term masking.
        """
        hindi_sentences = [
            "आज मौसम बहुत अच्छा है।",
            "अरे, तुम कहाँ जा रहे हो?",
            "कृपया मुझे एक ग्लास पानी दीजिए।",
            "कल मुझे जल्दी उठना है।",
            "क्या आप मेरी मदद कर सकते हैं?",
            "यह पुस्तक बहुत दिलचस्प है।",
            "मुझे आज बहुत काम है।",
            "आपसे मिलकर बहुत खुशी हुई।",
            "वह कल दिल्ली जाएगा।",
            "चलो, कहीं घूमने चलते हैं।",
            "खाना बहुत स्वादिष्ट बना है।"
        ]
        
        marathi_sentences = [
            "आज हवामान खूप छान आहे.",
            "अरे, तू कुठे चालला आहेस?",
            "कृपया मला एक ग्लास पाणी द्या.",
            "मला उद्या लवकर उठायचे आहे.",
            "तुम्ही मला मदत करू शकता का?",
            "हे पुस्तक खूप मनोरंजक आहे.",
            "मला आज खूप काम आहे.",
            "तुम्हाला भेटून खूप आनंद झाला।"
        ]
        
        kannada_sentences = [
            "ಇವತ್ತು ಹವಾಮಾನ ತುಂಬಾ ಚೆನ್ನಾಗಿದೆ.",
            "ಅರೇ, ನೀನು ಎಲ್ಲಿಗೆ ಹೋಗುತ್ತಿದ್ದೀಯಾ?",
            "ದಯವಿಟ್ಟು ನನಗೆ ಒಂದು ಲೋಟ ನೀರು ಕೊಡಿ.",
            "ನನಗೆ ನಾಳೆ ಬೇಗ ಏಳಬೇಕು.",
            "ನೀವು ನನಗೆ ಸಹಾಯ ಮಾಡಬಹುದೇ?",
            "ಈ ಪುಸ್ತಕ ತುಂಬಾ ಆಸಕ್ತಿದಾಯಕವಾಗಿದೆ.",
            "ನಿಮ್ಮನ್ನು ಭೇಟಿಯಾಗಿದ್ದು ತುಂಬಾ ಸಂತೋಷವಾಯಿತು."
        ]

        # Assert no mappings/masking occurs for Hindi everyday sentences
        for sentence in hindi_sentences:
            protected, mapping = protect_terms(sentence, "hindi")
            self.assertEqual(len(mapping), 0, f"False positive collision in Hindi: {sentence} -> {protected} (mapping: {mapping})")

        # Assert no mappings/masking occurs for Marathi everyday sentences
        for sentence in marathi_sentences:
            protected, mapping = protect_terms(sentence, "marathi")
            self.assertEqual(len(mapping), 0, f"False positive collision in Marathi: {sentence} -> {protected} (mapping: {mapping})")

        # Assert no mappings/masking occurs for Kannada everyday sentences
        for sentence in kannada_sentences:
            protected, mapping = protect_terms(sentence, "kannada")
            self.assertEqual(len(mapping), 0, f"False positive collision in Kannada: {sentence} -> {protected} (mapping: {mapping})")

if __name__ == "__main__":
    unittest.main()
