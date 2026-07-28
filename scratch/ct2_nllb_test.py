import os
import sys
import time
import json
import torch

sys.stdout.reconfigure(encoding='utf-8')

model_id = "facebook/nllb-200-distilled-600M"
output_dir = "scratch/nllb_ct2"

# 1. Convert model to CTranslate2 format if not already done
if not os.path.exists(output_dir):
    print("Converting NLLB-200 to CTranslate2 format (int8 quantization)...")
    t0 = time.time()
    try:
        import ctranslate2.converters
        converter = ctranslate2.converters.TransformersConverter(model_id)
        converter.convert(output_dir, quantization="int8")
        print(f"Conversion completed successfully in {time.time() - t0:.2f}s")
    except Exception as e:
        print(f"Error during conversion: {e}")
        sys.exit(1)
else:
    print(f"CTranslate2 model already exists at {output_dir}")

# 2. Load tokenizer and CTranslate2 translator
import ctranslate2
import transformers

print("Loading translator and tokenizer...")
try:
    # Use 4 threads for AMD Ryzen 7 6800HS to optimize CPU performance
    translator = ctranslate2.Translator(output_dir, device="cpu", inter_threads=4, intra_threads=4)
    tokenizer = transformers.AutoTokenizer.from_pretrained(model_id)
    print("Successfully loaded translator and tokenizer.")
except Exception as e:
    print(f"Error loading model: {e}")
    sys.exit(1)

# Check tokenizer behavior
sample_text = "Hello world!"
tokens = tokenizer.tokenize(sample_text)
print(f"Sample tokenization for {sample_text!r} using standard tokenize(): {tokens}")

# Define test cases
indic_prompts = {
    "Hindi": {
        "src_lang": "hin_Deva",
        "texts": [
            "recursion kya hota hai aur iska ek simple python example do", # Hinglish
            "programming mein database kya hota hai?", # Hinglish
            "binary search and linear search mein kya difference hai?", # Hinglish
            "object oriented programming ke pillars kya hain?", # Hinglish
            "linked list array se better kyun hai?" # Hinglish
        ]
    },
    "Kannada": {
        "src_lang": "kan_Knda",
        "texts": [
            "ಪುನರಾವರ್ತನೆ ಎಂದರೇನು ಮತ್ತು ಒಂದು ಸರಳ ಉದಾಹರಣೆ ಕೊಡಿ",
            "ಪ್ರೋಗ್ರಾಮಿಂಗ್‌ನಲ್ಲಿ ಡೇಟಾಬೇಸ್ ಎಂದರೇನು?",
            "ಬೈನರಿ ಸರ್ಚ್ ಮತ್ತು ಲೀನಿಯರ್ ಸರ್ಚ್ ನಡುವೆ ಏನು ವ್ಯತ್ಯಾಸ?",
            "ಆಬ್ಜೆಕ್ಟ್ ಓರಿಯೆಂಟೆಡ್ ಪ್ರೋಗ್ರಾಮಿಂಗ್‌ನ ಮುಖ್ಯ ಪಿಲ್ಲರ್‌ಗಳು ಯಾವುವು?",
            "ಲಿಂಕ್ಡ್ ಲಿಸ್ಟ್ ಅರೇಗಿಂತ ಹೇಗೆ ಉತ್ತಮ?"
        ]
    },
    "Marathi": {
        "src_lang": "mar_Deva",
        "texts": [
            "रिकर्शन म्हणजे काय आणि त्याचे एक सोपे उदाहरण द्या",
            "प्रोग्रामिंगमध्ये डेटाबेस म्हणजे काय?",
            "बायनरी सर्च आणि लिनियर सर्चमध्ये काय फरक आहे?",
            "ऑब्जेक्ट ओरिएंटेड प्रोग्रामिंगचे मुख्य पिलर्स कोणते आहेत?",
            "लिंक्ड लिस्ट अरेपेक्षा कशी चांगली आहे?"
        ]
    }
}

english_responses = [
    "Recursion is a method where a function calls itself to solve a smaller instance of the same problem.",
    "A database is an organized collection of structured data stored electronically in a computer system.",
    "Binary search works by repeatedly dividing the search interval in half, whereas linear search checks every element sequentially.",
    "The four pillars of Object-Oriented Programming are Encapsulation, Inheritance, Polymorphism, and Abstraction.",
    "A linked list is dynamic and allows fast insertions or deletions, while an array has a fixed size and is fast for random access."
]

def translate_ct2(text, src_lang_code, tgt_lang_code):
    t_start = time.time()
    try:
        # Tokenize with add_special_tokens=False
        source_tokens = tokenizer.tokenize(text)
        
        # NLLB requires the source language token prepended and EOS appended
        input_tokens = [src_lang_code] + source_tokens + ["</s>"]
        
        # Target prefix: [tgt_lang]
        target_prefix = [tgt_lang_code]
        
        # Translate batch
        results = translator.translate_batch(
            [input_tokens],
            target_prefix=[target_prefix],
            beam_size=4,
            max_decoding_length=128
        )
        
        # Get target tokens
        target_tokens = results[0].hypotheses[0]
        
        # Remove target language token if it's there
        if target_tokens and target_tokens[0] == tgt_lang_code:
            target_tokens = target_tokens[1:]
        
        # Convert tokens to ids and decode
        token_ids = tokenizer.convert_tokens_to_ids(target_tokens)
        translation = tokenizer.decode(token_ids, skip_special_tokens=True).strip()
        latency = time.time() - t_start
        return translation, latency
    except Exception as e:
        return f"ERROR: {str(e)}", time.time() - t_start

# Run translation tests
results_ct2 = {
    "Indic_to_English": {},
    "English_to_Indic": {}
}

# 1. Translate Indic Prompts to English
print("\n=== Translating Indic Prompts to English (CTranslate2) ===")
for lang, data in indic_prompts.items():
    print(f"\nTranslating {lang} -> English...")
    results_ct2["Indic_to_English"][lang] = []
    for idx, text in enumerate(data["texts"]):
        translation, latency = translate_ct2(text, data["src_lang"], "eng_Latn")
        print(f"  [{idx+1}/5] Source: {text!r}")
        print(f"        Trans : {translation!r} (in {latency:.2f}s)")
        results_ct2["Indic_to_English"][lang].append({
            "source": text,
            "translation": translation,
            "latency": latency
        })

# 2. Translate English Responses to Indic
print("\n=== Translating English Responses to Indic (CTranslate2) ===")
for lang, data in indic_prompts.items():
    tgt_lang = data["src_lang"]
    print(f"\nTranslating English -> {lang}...")
    results_ct2["English_to_Indic"][lang] = []
    for idx, text in enumerate(english_responses):
        translation, latency = translate_ct2(text, "eng_Latn", tgt_lang)
        print(f"  [{idx+1}/5] Source: {text!r}")
        print(f"        Trans : {translation!r} (in {latency:.2f}s)")
        results_ct2["English_to_Indic"][lang].append({
            "source": text,
            "translation": translation,
            "latency": latency
        })

# Save results JSON
with open("scratch/ct2_translation_results.json", "w", encoding="utf-8") as f:
    json.dump(results_ct2, f, ensure_ascii=False, indent=2)
print("\nSaved CTranslate2 translation results to scratch/ct2_translation_results.json")
