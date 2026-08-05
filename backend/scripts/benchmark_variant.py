import os
import sys
import time
import argparse
import json
import threading
import subprocess
import io
import httpx
import numpy as np
import soundfile as sf
import torch
import psutil

# Add backend directory to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

# Parse command line args
parser = argparse.ArgumentParser()
parser.add_argument("--variant", choices=["baseline", "indic-parler-tts", "m2m100-translation"], required=True)
parser.add_argument("--output", required=True)
args = parser.parse_args()

# Setup isolated cache path for candidate models
if args.variant in ("indic-parler-tts", "m2m100-translation"):
    os.environ["HF_HOME"] = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scratch", "hf_bench_cache")

from config import Config
# Force CPU for Whisper and Kokoro/MMS depending on settings
os.environ["WHISPER_DEVICE"] = "cpu"
os.environ["WHISPER_COMPUTE_TYPE"] = "int8"
# Force CUDA for translation and TTS if available to test VRAM loading/reclaiming
device = "cuda" if torch.cuda.is_available() else "cpu"
os.environ["MMS_TTS_DEVICE"] = device
os.environ["NLLB_DEVICE"] = device

# Import pipeline components
from stt.whisper_engine import WhisperEngine
from i18n.term_glossary import protect_terms, restore_terms, transliterate_latin_words, normalize_lang
from speech.language_router import LanguageRouter

# ─────────────────────────────────────────────────────────────────────────────
# Resource Monitoring Thread
# ─────────────────────────────────────────────────────────────────────────────
class ResourceMonitor(threading.Thread):
    def __init__(self):
        super().__init__()
        self.daemon = True
        self.stop_event = threading.Event()
        self.peak_vram = 0
        self.cpu_usages = []
        
    def run(self):
        while not self.stop_event.is_set():
            # Query VRAM using nvidia-smi
            try:
                cmd = [
                    "nvidia-smi",
                    "--query-gpu=memory.used",
                    "--format=csv,noheader,nounits"
                ]
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
                vram = int(res.stdout.strip())
                if vram > self.peak_vram:
                    self.peak_vram = vram
            except Exception:
                pass
                
            # Query CPU usage
            try:
                cpu = psutil.cpu_percent(interval=None)
                self.cpu_usages.append(cpu)
            except Exception:
                pass
                
            time.sleep(0.1)
            
    def get_metrics(self):
        avg_cpu = sum(self.cpu_usages) / len(self.cpu_usages) if self.cpu_usages else 0
        peak_cpu = max(self.cpu_usages) if self.cpu_usages else 0
        return self.peak_vram, avg_cpu, peak_cpu

# ─────────────────────────────────────────────────────────────────────────────
# Custom Translation & TTS Engine definitions
# ─────────────────────────────────────────────────────────────────────────────
class M2M100Translator:
    def __init__(self, device: str):
        self.device = device
        self.model = None
        self.tokenizer = None
        
    def load(self):
        from transformers import M2M100ForConditionalGeneration, M2M100Tokenizer
        self.model = M2M100ForConditionalGeneration.from_pretrained("facebook/m2m100_418M").to(self.device)
        self.tokenizer = M2M100Tokenizer.from_pretrained("facebook/m2m100_418M")
        
    def translate(self, text: str, src_lang: str, tgt_lang: str) -> tuple[str, float]:
        t0 = time.time()
        lang_map = {
            "english": "en", "hindi": "hi", "kannada": "kn", "marathi": "mr",
            "en": "en", "hi": "hi", "kn": "kn", "mr": "mr",
            "kan_Knda": "kn", "mar_Deva": "mr", "hin_Deva": "hi", "eng_Latn": "en"
        }
        src = lang_map.get(src_lang, "en")
        tgt = lang_map.get(tgt_lang, "en")
        
        self.tokenizer.src_lang = src
        encoded = self.tokenizer(text, return_tensors="pt").to(self.device)
        with torch.no_grad():
            generated_tokens = self.model.generate(
                **encoded,
                forced_bos_token_id=self.tokenizer.get_lang_id(tgt)
            )
        translated_text = self.tokenizer.batch_decode(generated_tokens, skip_special_tokens=True)[0]
        return translated_text, time.time() - t0

class IndicParlerTTSEngine:
    def __init__(self, device: str):
        self.device = device
        self.model = None
        self.tokenizer = None
        self.sampling_rate = 24000
        
    def load(self):
        from parler_tts import ParlerTTSForConditionalGeneration
        from transformers import AutoTokenizer
        self.model = ParlerTTSForConditionalGeneration.from_pretrained("ai4bharat/indic-parler-tts").to(self.device)
        self.tokenizer = AutoTokenizer.from_pretrained("ai4bharat/indic-parler-tts")
        self.sampling_rate = self.model.config.sampling_rate
        
    def synthesize(self, text: str, lang: str) -> bytes:
        # Instruction-conditioned description
        description = "A female speaker with a clear and expressive voice, speaking in a moderate speed."
        inputs = self.tokenizer(description, return_tensors="pt").to(self.device)
        prompt_inputs = self.tokenizer(text, return_tensors="pt").to(self.device)
        
        with torch.no_grad():
            generation = self.model.generate(
                input_ids=inputs.input_ids,
                prompt_input_ids=prompt_inputs.input_ids
            )
            
        audio_arr = generation.cpu().numpy().squeeze()
        
        # Write to WAV bytes
        out_buf = io.BytesIO()
        sf.write(out_buf, audio_arr, self.sampling_rate, format="WAV")
        return out_buf.getvalue()

# ─────────────────────────────────────────────────────────────────────────────
# Model Initialization
# ─────────────────────────────────────────────────────────────────────────────
print(f"[{args.variant.upper()}] Initializing models on device: {device}...")

# Load Whisper STT
whisper_engine = WhisperEngine()

# Load Kokoro English TTS
from tts.kokoro_engine import KokoroEngine
kokoro_engine = KokoroEngine()

# Load translation engine
if args.variant == "m2m100-translation":
    translator = M2M100Translator(device)
    translator.load()
else:
    from speech.nllb_translator import get_translator
    translator = get_translator()

# Load native TTS engine
if args.variant == "indic-parler-tts":
    mms_tts = None
    parler_tts = IndicParlerTTSEngine(device)
    parler_tts.load()
else:
    from speech.mms_tts import get_mms_tts_engine
    mms_tts = get_mms_tts_engine()
    parler_tts = None

# Initialize router
router = LanguageRouter()

print(f"[{args.variant.upper()}] All models loaded.")

# Load Test Matrix
matrix_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "benchmark_test_matrix.json")
with open(matrix_path, "r", encoding="utf-8") as f:
    test_cases = json.load(f)

results = []
exceptions_count = 0
empty_audio_count = 0

import librosa

# Create output audio dir
audio_out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scratch", "audio_out", args.variant)
os.makedirs(audio_out_dir, exist_ok=True)

# Start resource monitoring
monitor = ResourceMonitor()
monitor.start()

# ─────────────────────────────────────────────────────────────────────────────
# Helper: Split text into sentences for streaming simulation
# ─────────────────────────────────────────────────────────────────────────────
def split_sentences(text: str) -> list[str]:
    import re
    # Simple sentence splitter for technical texts
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return [s.strip() for s in sentences if s.strip()]

# ─────────────────────────────────────────────────────────────────────────────
# Run Benchmarks
# ─────────────────────────────────────────────────────────────────────────────
for case in test_cases:
    case_id = case["id"]
    case_name = case["name"]
    input_text = case["text"]
    target_lang = case["lang"]
    
    print(f"Running Case {case_id}: {case_name}...")
    
    # 0. Load input audio
    audio_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scratch", "bench_audio", f"case_{case_id}.wav")
    if not os.path.exists(audio_path):
        print(f"Warning: Audio file missing for case {case_id}. Skipping.")
        continue
        
    audio_array, _ = librosa.load(audio_path, sr=16000)
    
    case_start_vram = monitor.peak_vram
    
    # Reset case-level timers
    t_stt = 0.0
    t_trans_in = 0.0
    t_llm_ttft = 0.0
    t_llm_total = 0.0
    t_trans_out = 0.0
    t_tts_ttfa = 0.0
    t_tts_total = 0.0
    
    stt_transcript = ""
    route_lang = ""
    llm_input = ""
    llm_output_english = ""
    llm_output_native = ""
    tts_wav_bytes = b""
    
    try:
        # ── Stage 1: STT ─────────────────────────────────────────────────────
        t0 = time.time()
        # Mock multilingual prompt and transcribe
        segments, info = whisper_engine.model.transcribe(
            audio_array,
            language=None,
            task="transcribe",
            vad_filter=False,
            beam_size=Config.WHISPER_BEAM_SIZE,
            best_of=Config.WHISPER_BEAM_SIZE,
            temperature=0.0,
            condition_on_previous_text=False,
            initial_prompt=Config.MULTILINGUAL_WHISPER_PROMPT,
        )
        parts = []
        for seg in segments:
            text = seg.text.strip()
            if text and not whisper_engine._is_hallucination(text):
                parts.append(text)
        stt_transcript = " ".join(parts).strip()
        t_stt = time.time() - t0
        
        # ── Stage 2: Routing ─────────────────────────────────────────────────
        route_lang, route_meta = router.route(stt_transcript, info.language if info else "en")
        
        # ── Stage 3: Translate-In (kannada/marathi, or hindi as well for m2m100) ──
        llm_input = stt_transcript
        needs_translation = route_lang in ("kannada", "marathi") or (args.variant == "m2m100-translation" and route_lang == "hindi")
        
        if needs_translation and stt_transcript:
            t0 = time.time()
            protected_transcript, mapping = protect_terms(stt_transcript, route_lang)
            
            if args.variant == "m2m100-translation":
                english_input_protected, _ = translator.translate(protected_transcript, route_lang, "english")
            else:
                english_input_protected, _ = translator.translate(protected_transcript, getattr(Config, f"NLLB_LANG_MAP", {}).get(route_lang, "hin_Deva"), "eng_Latn")
                
            llm_input = restore_terms(english_input_protected, mapping, mode="english")
            t_trans_in = time.time() - t0
            
        # ── Stage 4: LLM ─────────────────────────────────────────────────────
        t0 = time.time()
        payload = {
            "messages": [
                {"role": "system", "content": Config.LLM_SYSTEM_PROMPT},
                {"role": "user", "content": llm_input}
            ],
            "temperature": 0.55,
            "max_tokens": 512,
            "stream": True
        }
        
        # Send streaming request to Qwen3 local server
        llm_tokens = []
        with httpx.stream("POST", f"{Config.LLM_BASE_URL}/v1/chat/completions", json=payload, timeout=60.0) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if line.startswith("data: "):
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        token = chunk["choices"][0]["delta"].get("content", "")
                        if token:
                            if t_llm_ttft == 0.0:
                                t_llm_ttft = time.time() - t0
                            llm_tokens.append(token)
                    except Exception:
                        pass
        llm_output_english = "".join(llm_tokens).strip()
        t_llm_total = time.time() - t0
        if t_llm_ttft == 0.0:
            t_llm_ttft = t_llm_total
            
        # Extract <speak> blocks as spoken text
        import re
        speak_matches = re.findall(r"<speak>(.*?)</speak>", llm_output_english, re.DOTALL)
        llm_speak_content = " ".join(speak_matches).strip() if speak_matches else llm_output_english
        # Remove any lingering tags
        llm_speak_content = re.sub(r"</?[a-zA-Z]+(?:\s+[^>]*)?>", "", llm_speak_content)
        
        # ── Stage 5: Translate-Out ───────────────────────────────────────────
        llm_output_native = llm_speak_content
        if needs_translation and llm_speak_content:
            t0 = time.time()
            protected_response, mapping = protect_terms(llm_speak_content, "english")
            
            if args.variant == "m2m100-translation":
                translated_protected, _ = translator.translate(protected_response, "english", route_lang)
            else:
                translated_protected, _ = translator.translate(protected_response, "eng_Latn", getattr(Config, f"NLLB_LANG_MAP", {}).get(route_lang, "hin_Deva"))
                
            llm_output_native = restore_terms(translated_protected, mapping, mode="native", target_language=route_lang)
            t_trans_out = time.time() - t0
            
        # ── Stage 6: TTS Routing & Synthesis ─────────────────────────────────
        tts_text = llm_output_native
        sentences = split_sentences(tts_text)
        
        if sentences:
            t0 = time.time()
            wav_chunks = []
            
            # Synthesize sentence chunks
            for idx, sent in enumerate(sentences):
                t_chunk_start = time.time()
                
                # Check routing
                use_native = route_lang in ("kannada", "marathi") or (route_lang == "hindi")
                
                if use_native:
                    if args.variant == "indic-parler-tts":
                        wav_bytes = parler_tts.synthesize(sent, route_lang)
                    else:
                        mms_lang = getattr(Config, "MMS_TTS_LANG_MAP", {}).get(route_lang, "hin")
                        wav_bytes = mms_tts.synthesize(sent, mms_lang)
                else:
                    # English path -> Kokoro
                    wav_bytes = kokoro_engine.synthesize(sent, voice="af_heart")
                    
                if idx == 0:
                    t_tts_ttfa = time.time() - t0
                    
                if wav_bytes:
                    wav_chunks.append(wav_bytes)
                    
            t_tts_total = time.time() - t0
            
            # Merge WAV chunks (skip header matching for simplicity, or concatenate raw PCM data)
            # For simplicity, we concatenate the first chunk or all chunks as a single file
            if wav_chunks:
                tts_wav_bytes = b"".join(wav_chunks)
            else:
                empty_audio_count += 1
                
        # Save synthesized audio
        if tts_wav_bytes:
            case_audio_path = os.path.join(audio_out_dir, f"case_{case_id}.wav")
            with open(case_audio_path, "wb") as f_wav:
                f_wav.write(tts_wav_bytes)
                
    except Exception as e:
        print(f"Exception in case {case_id}: {e}")
        exceptions_count += 1
        
    # Get peak resource metrics
    case_peak_vram, case_avg_cpu, case_peak_cpu = monitor.get_metrics()
    
    # Calculate end to end latency
    latency_total = t_stt + t_trans_in + t_llm_total + t_trans_out + t_tts_total
    
    results.append({
        "id": case_id,
        "name": case_name,
        "lang": target_lang,
        "stt_transcript": stt_transcript,
        "route_lang": route_lang,
        "llm_input": llm_input,
        "llm_output_english": llm_output_english,
        "llm_output_native": llm_output_native,
        "latency_stt": round(t_stt, 3),
        "latency_translate_in": round(t_trans_in, 3),
        "latency_llm_ttft": round(t_llm_ttft, 3),
        "latency_llm_total": round(t_llm_total, 3),
        "latency_translate_out": round(t_trans_out, 3),
        "latency_tts_ttfa": round(t_tts_ttfa, 3),
        "latency_tts_total": round(t_tts_total, 3),
        "latency_total": round(latency_total, 3),
        "peak_vram": int(case_peak_vram - case_start_vram),
        "avg_cpu": round(case_avg_cpu, 1),
        "peak_cpu": round(case_peak_cpu, 1)
    })

# ─────────────────────────────────────────────────────────────────────────────
# Robustness & Latin Fallback Scenarios
# ─────────────────────────────────────────────────────────────────────────────
print(f"[{args.variant.upper()}] Running pure-Latin-chunk robustness checks...")

latin_cases = [
    {"lang": "hindi", "mms_lang": "hin", "chunks": ["Recursion", "यह एक प्रोग्रामिंग तकनीक है।"]},
    {"lang": "kannada", "mms_lang": "kan", "chunks": ["Encapsulation", "ಒಂದು ಪ್ರೋಗ್ರಾಮಿಂಗ್ ಪರಿಕಲ್ಪನೆ."]},
]
latin_failures = 0

for case in latin_cases:
    try:
        # Join chunks together (representing pure Latin technical term merge)
        text = " ".join(case["chunks"])
        # Perform fallback transliteration if needed
        if not any('\u0900' <= char <= '\u097f' for char in text) and not any('\u0c80' <= char <= '\u0cff' for char in text):
            text = transliterate_latin_words(text, case["lang"])
            
        if args.variant == "indic-parler-tts":
            wav = parler_tts.synthesize(text, case["lang"])
        else:
            wav = mms_tts.synthesize(text, case["mms_lang"])
            
        if not wav or len(wav) == 0:
            latin_failures += 1
    except Exception as e:
        print(f"Latin fallback crash scenario failed: {e}")
        latin_failures += 1

# Stop monitor
monitor.stop_event.set()
monitor.join()

# Final Metrics File
vram_post, cpu_avg_post, cpu_peak_post = monitor.get_metrics()

report_data = {
    "variant": args.variant,
    "results": results,
    "exceptions_count": exceptions_count,
    "empty_audio_count": empty_audio_count,
    "latin_fallback_failures": latin_failures,
    "peak_vram_variant": int(vram_post),
    "avg_cpu_variant": round(cpu_avg_post, 1)
}

with open(args.output, "w", encoding="utf-8") as f_out:
    json.dump(report_data, f_out, indent=2)

print(f"[{args.variant.upper()}] Execution finished. Results written to {args.output}")
sys.exit(0)
