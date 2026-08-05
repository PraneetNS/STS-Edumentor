import os
import sys
import time
import subprocess
import shutil
import json
import urllib.parse
import urllib.request
import httpx

# Add backend directory to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

# ─────────────────────────────────────────────────────────────────────────────
# Path Configuration and Denylist
# ─────────────────────────────────────────────────────────────────────────────
SCRATCH_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scratch"))
BENCH_AUDIO_DIR = os.path.join(SCRATCH_DIR, "bench_audio")
HF_BENCH_CACHE = os.path.join(SCRATCH_DIR, "hf_bench_cache")

DENYLIST_PATHS = [
    r"C:\Users\savan\.cache\huggingface\hub\models--Systran--faster-whisper-small",
    r"C:\Users\savan\.cache\huggingface\hub\models--Systran--faster-whisper-small.en",
    r"C:\Users\savan\.cache\huggingface\hub\models--facebook--nllb-200-distilled-600M",
    r"C:\Users\savan\.cache\huggingface\hub\models--facebook--mms-tts-hin",
    r"C:\Users\savan\.cache\huggingface\hub\models--facebook--mms-tts-kan",
    r"C:\Users\savan\.cache\huggingface\hub\models--facebook--mms-tts-mar",
    r"C:\Users\savan\.cache\huggingface\hub\models--hexgrad--Kokoro-82M",
    r"c:\Users\savan\OneDrive\Desktop\LLM_Testing\EduMentor-Voice\backend\models\EduMentor-Qwen3-Q6_K.gguf",
]

# Standardize path list
DENYLIST = [os.path.normpath(p).lower() for p in DENYLIST_PATHS]

# Expected candidate download sizes in GB
MODEL_SIZES_GB = {
    "baseline": 0.0,
    "indic-parler-tts": 4.0,
    "m2m100-translation": 1.94,
}

def check_disk_space():
    total, used, free = shutil.disk_usage("C:\\")
    return free / (1024**3)

def print_banner():
    print("=" * 70)
    print("        EDUMENTOR VOICE MULTI-PIPELINE BENCHMARK HARNESS")
    print("=" * 70)
    print("\n[DENYLIST - These paths will never be touched by cleanup:")
    for path in DENYLIST_PATHS:
        print(f"  - {path}")
    print("]")
    
    free_space = check_disk_space()
    print(f"\n[Current C: Drive Free Space: {free_space:.2f} GB]")
    print("=" * 70)

# ─────────────────────────────────────────────────────────────────────────────
# Step 1: Pre-download input audio files using Google Translate TTS API
# ─────────────────────────────────────────────────────────────────────────────
def generate_test_audio_matrix():
    print("\n[Generating input audio clips for test matrix...]")
    os.makedirs(BENCH_AUDIO_DIR, exist_ok=True)
    
    matrix_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "benchmark_test_matrix.json")
    with open(matrix_path, "r", encoding="utf-8") as f:
        test_cases = json.load(f)
        
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )
    }
    
    for case in test_cases:
        case_id = case["id"]
        text = case["text"]
        lang = case["gtts_lang"]
        
        cache_file = os.path.join(BENCH_AUDIO_DIR, f"case_{case_id}.wav")
        # Check if already exists
        if os.path.exists(cache_file):
            continue
            
        print(f"  Downloading speech audio for case {case_id} ({lang})...")
        
        try:
            q = urllib.parse.quote(text)
            url = f"http://translate.google.com/translate_tts?ie=UTF-8&total=1&idx=0&textlen={len(text)}&client=tw-ob&q={q}&tl={lang}"
            req = urllib.request.Request(url, headers=headers)
            temp_mp3 = cache_file.replace(".wav", ".mp3")
            
            with urllib.request.urlopen(req, timeout=15) as resp:
                with open(temp_mp3, "wb") as f_out:
                    f_out.write(resp.read())
                    
            # Convert MP3 to 16kHz WAV using ffmpeg or librosa (we can load and save in python)
            import librosa
            import soundfile as sf
            y, sr = librosa.load(temp_mp3, sr=16000)
            sf.write(cache_file, y, 16000, format="WAV")
            os.remove(temp_mp3)
            
        except Exception as e:
            print(f"  Error downloading audio for case {case_id}: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# Subprocess VRAM check
# ─────────────────────────────────────────────────────────────────────────────
def get_vram_usage():
    try:
        cmd = [
            "nvidia-smi",
            "--query-gpu=memory.used",
            "--format=csv,noheader,nounits"
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return int(res.stdout.strip())
    except Exception:
        return 0

# ─────────────────────────────────────────────────────────────────────────────
# Main Orchestrator Loop
# ─────────────────────────────────────────────────────────────────────────────
def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    print_banner()
    generate_test_audio_matrix()
    
    variants = ["baseline", "indic-parler-tts", "m2m100-translation"]
    
    python_exe = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".venv310", "Scripts", "python.exe")
    if not os.path.exists(python_exe):
        python_exe = sys.executable  # Fallback to current python
        
    for var in variants:
        print("\n" + "=" * 70)
        print(f"STARTING PIPELINE VARIANT: {var.upper()}")
        print("=" * 70)
        
        # Check Disk space constraints
        req_space = MODEL_SIZES_GB[var]
        safety_limit = req_space * 1.5
        free_space = check_disk_space()
        
        print(f"Checking disk safety for {var}: Free: {free_space:.2f} GB | Required: {req_space:.2f} GB | Safety Limit: {safety_limit:.2f} GB")
        
        if free_space < req_space:
            print(f"❌ ERROR: Insufficient disk space to load {var}. Model requires {req_space:.2f} GB, only {free_space:.2f} GB is free. Skipping.")
            # Write stub output JSON
            stub_out = {
                "variant": var,
                "skipped": True,
                "reason": "Insufficient disk space"
            }
            res_path = os.path.join(SCRATCH_DIR, f"res_{var}.json")
            with open(res_path, "w", encoding="utf-8") as f_stub:
                json.dump(stub_out, f_stub)
            continue
            
        elif free_space < safety_limit:
            print(f"⚠️  WARNING: Free space ({free_space:.2f} GB) is below the 1.5x safety threshold ({safety_limit:.2f} GB) for {var}. Proceeding due to mandatory override.")
            
        # Run in Subprocess
        res_path = os.path.join(SCRATCH_DIR, f"res_{var}.json")
        var_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "benchmark_variant.py")
        
        vram_before = get_vram_usage()
        disk_before = check_disk_space()
        
        print(f"GPU VRAM usage before process run: {vram_before} MiB")
        
        cmd = [python_exe, var_script, "--variant", var, "--output", res_path]
        
        t_start = time.time()
        process = subprocess.Popen(cmd)
        process.wait()
        t_duration = time.time() - t_start
        
        print(f"Subprocess completed with exit code: {process.returncode} in {t_duration:.2f}s")
        
        # Verify VRAM is fully released after process termination
        time.sleep(2.0) # Wait for OS memory reclaim
        vram_after = get_vram_usage()
        vram_diff = vram_after - vram_before
        print(f"GPU VRAM usage after process run: {vram_after} MiB (Delta: {vram_diff} MiB)")
        if vram_after <= vram_before + 50:
            print("✅ VRAM Successfully reclaimed and fully released by OS.")
        else:
            print("⚠️  VRAM was not completely released back to original idle state.")
            
        # Disk Space Cleanup
        if var in ("indic-parler-tts", "m2m100-translation"):
            print(f"\n[🧹 Cleaning up downloaded weights for variant {var}...]")
            
            # Verify HF_BENCH_CACHE is not on the denylist
            cache_norm = os.path.normpath(HF_BENCH_CACHE).lower()
            if cache_norm in DENYLIST:
                print(f"❌ CRITICAL ERROR: Benchmark cache path {HF_BENCH_CACHE} is in the protected Denylist! Skipping cleanup.")
            else:
                if os.path.exists(HF_BENCH_CACHE):
                    shutil.rmtree(HF_BENCH_CACHE)
                    print(f"✅ Deleted isolated cache directory: {HF_BENCH_CACHE}")
                    
            disk_after = check_disk_space()
            reclaimed_disk = disk_after - disk_before
            print(f"Disk free space change: Before: {disk_before:.2f} GB | After: {disk_after:.2f} GB (Reclaimed: {reclaimed_disk:.2f} GB)")
            
    # Trigger Report Generation
    print("\n" + "=" * 70)
    print("GENERATING BENCHMARK EVALUATION REPORT")
    print("=" * 70)
    
    report_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "generate_report.py")
    subprocess.run([python_exe, report_script])

if __name__ == "__main__":
    main()
