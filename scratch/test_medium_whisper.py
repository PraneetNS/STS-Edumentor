import os
import sys
import time
import urllib.parse
import urllib.request
import librosa
import numpy as np

sys.stdout.reconfigure(encoding='utf-8')

# Ensure scratch directory exists
os.makedirs("scratch", exist_ok=True)

test_clips = {
    "pure_kannada": {
        "text": "ಪುನರಾವರ್ತನೆಯು ಒಂದು ಪ್ರಕ್ರಿಯೆಯಾಗಿದ್ದು ಅದರಲ್ಲಿ ಫಂಕ್ಷನ್ ತನ್ನನ್ನು ತಾನೇ ಕರೆಯುತ್ತದೆ",
        "lang": "kn",
        "file": "scratch/test_kannada.mp3"
    },
    "kanglish": {
        "text": "Recursion calculation nalli function thanna thaanu call maaduvudu",
        "lang": "kn",
        "file": "scratch/test_kanglish.mp3"
    }
}

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# 1. Download TTS audio clips
for name, clip in test_clips.items():
    if not os.path.exists(clip["file"]):
        print(f"Downloading TTS audio for {name}...")
        try:
            q_enc = urllib.parse.quote(clip["text"])
            url = f"http://translate.google.com/translate_tts?ie=UTF-8&total=1&idx=0&textlen={len(clip['text'])}&client=tw-ob&q={q_enc}&tl={clip['lang']}"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req) as response:
                with open(clip["file"], "wb") as f:
                    f.write(response.read())
            print(f"  Saved {clip['file']}.")
        except Exception as e:
            print(f"  Error downloading {name}: {e}")
            sys.exit(1)
    else:
        print(f"Using existing audio file: {clip['file']}")

# Helper to load audio at 16kHz
def load_audio(path):
    y, sr = librosa.load(path, sr=16000)
    return y

# Load audio files into memory
audio_data = {}
for name, clip in test_clips.items():
    audio_data[name] = load_audio(clip["file"])
    print(f"Loaded {name} audio: {len(audio_data[name])} samples")

# 2. Test with Whisper Models
import faster_whisper

def run_whisper_benchmark(model_size):
    print(f"\n==================================================")
    print(f"Benchmarking faster-whisper model size: '{model_size}'")
    print(f"==================================================")
    
    t0 = time.time()
    try:
        model = faster_whisper.WhisperModel(model_size, device="cpu", compute_type="int8")
        print(f"Loaded model in {time.time() - t0:.2f}s")
    except Exception as e:
        print(f"Failed to load model {model_size}: {e}")
        return None

    results = {}
    for name, audio in audio_data.items():
        print(f"Transcribing {name}...")
        t_start = time.time()
        
        # We transcribe without forced language to see what script/language it naturally chooses
        segments, info = model.transcribe(
            audio,
            beam_size=5,
            best_of=5,
            temperature=0.0,
            condition_on_previous_text=False
        )
        
        parts = []
        for seg in segments:
            parts.append(seg.text.strip())
        transcript = " ".join(parts).strip()
        latency = time.time() - t_start
        
        print(f"  Result : {transcript!r}")
        print(f"  Detected language: {info.language} (prob={info.language_probability:.2f})")
        print(f"  Latency: {latency:.2f}s")
        
        results[name] = {
            "transcript": transcript,
            "detected_lang": info.language,
            "prob": info.language_probability,
            "latency": latency
        }
    return results

# Benchmark 'small' and 'medium'
small_results = run_whisper_benchmark("small")
medium_results = run_whisper_benchmark("medium")

# Save results JSON
with open("scratch/whisper_comparison_results.json", "w", encoding="utf-8") as f:
    import json
    json.dump({
        "small": small_results,
        "medium": medium_results
    }, f, ensure_ascii=False, indent=2)

print("\nFinished benchmarking. Saved results to scratch/whisper_comparison_results.json")
