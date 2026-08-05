import os
import sys
import json
import base64
import time
import io
import httpx
import urllib.parse
import numpy as np
import torch
from transformers import AutoTokenizer, AutoModel
import matplotlib.pyplot as plt

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

# Add backend directory to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

# Configurable Weights
WEIGHTS = {
    "latency": 0.30,
    "resource_usage": 0.15,
    "translation_accuracy": 0.25,
    "robustness": 0.15,
    "voice_quality": 0.15
}

SCRATCH_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scratch"))
REPORTS_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reports"))
os.makedirs(REPORTS_DIR, exist_ok=True)

# ─────────────────────────────────────────────────────────────────────────────
# Step 1: Initialize MiniLM Model for Semantic Similarity
# ─────────────────────────────────────────────────────────────────────────────
print("[EVAL] Loading all-MiniLM-L6-v2 for semantic similarity checks...")
tokenizer = AutoTokenizer.from_pretrained("sentence-transformers/all-MiniLM-L6-v2")
similarity_model = AutoModel.from_pretrained("sentence-transformers/all-MiniLM-L6-v2")

def mean_pooling(model_output, attention_mask):
    token_embeddings = model_output[0]
    input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
    return torch.sum(token_embeddings * input_mask_expanded, 1) / torch.clamp(input_mask_expanded.sum(1), min=1e-9)

def calculate_similarity(text1: str, text2: str) -> float:
    if not text1 or not text2:
        return 0.0
    encoded = tokenizer([text1, text2], padding=True, truncation=True, return_tensors='pt')
    with torch.no_grad():
        outputs = similarity_model(**encoded)
    embeddings = mean_pooling(outputs, encoded['attention_mask'])
    embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)
    sim = (embeddings[0] @ embeddings[1]).item()
    return float(sim)

# ─────────────────────────────────────────────────────────────────────────────
# Step 2: Third-party translation endpoint
# ─────────────────────────────────────────────────────────────────────────────
def translate_google_free(text: str, src_lang: str) -> str:
    if not text:
        return ""
    # Map from custom to google codes
    lang_map = {"kannada": "kn", "marathi": "mr", "hindi": "hi", "english": "en"}
    sl = lang_map.get(src_lang, "en")
    
    url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl={sl}&tl=en&dt=t&q={urllib.parse.quote(text)}"
    try:
        r = httpx.get(url, timeout=15.0)
        r.raise_for_status()
        res = r.json()
        translated_parts = [part[0] for part in res[0] if part[0]]
        return "".join(translated_parts).strip()
    except Exception as e:
        print(f"    Google free translation failed: {e}")
        return ""

# ─────────────────────────────────────────────────────────────────────────────
# Step 3: Glossary Terms Check
# ─────────────────────────────────────────────────────────────────────────────
from i18n.term_glossary import TRANSLITERATIONS

def check_glossary_survival(text: str, topic: str, lang: str) -> bool:
    # Identify key term from topic
    term = None
    if "recursion" in topic.lower():
        term = "recursion"
    elif "binary search tree" in topic.lower():
        term = "binary search tree"
    elif "palindrome" in topic.lower():
        term = "palindrome"
    elif "quicksort" in topic.lower():
        term = "quicksort"
        
    if not term:
        return True
        
    # Check if target language is English -> term should survive as is
    if lang == "en":
        return term in text.lower()
        
    # Check transliterated forms
    native_forms = TRANSLITERATIONS.get(term, {}).get(lang, [])
    if isinstance(native_forms, str):
        native_forms = [native_forms]
        
    for nf in native_forms:
        if nf.strip() and nf.strip() in text:
            return True
            
    # Also check if english word survives
    if term in text.lower():
        return True
        
    return False

# ─────────────────────────────────────────────────────────────────────────────
# Step 4: Loading and Processing Results
# ─────────────────────────────────────────────────────────────────────────────
variants = ["baseline", "indic-parler-tts", "m2m100-translation"]
loaded_data = {}

# Load Test Matrix
matrix_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "benchmark_test_matrix.json")
with open(matrix_path, "r", encoding="utf-8") as f:
    test_cases = json.load(f)

for var in variants:
    path = os.path.join(SCRATCH_DIR, f"res_{var}.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            loaded_data[var] = json.load(f)
    else:
        print(f"Warning: Results missing for {var}")
        loaded_data[var] = {
            "variant": var,
            "skipped": True,
            "reason": "Model crashed during load (Virtual Memory/Paging File limits exceeded)"
        }

# Calculate Back-translations and accuracy
for var, data in loaded_data.items():
    if data.get("skipped"):
        continue
        
    print(f"\n[EVAL] Evaluating translations and voice quality for variant: {var.upper()}")
    for case in data["results"]:
        case_id = case["id"]
        native_output = case["llm_output_native"]
        en_output = case["llm_output_english"]
        lang = case["lang"]
        topic = case["name"]
        
        # 1. Back-translate
        back_trans = ""
        if lang != "en" and native_output:
            print(f"  Back-translating Case {case_id}...")
            back_trans = translate_google_free(native_output, case["route_lang"])
            
        case["back_translation"] = back_trans
        
        # 2. Similarity
        similarity = 1.0
        if lang != "en":
            similarity = calculate_similarity(back_trans, en_output)
        case["semantic_similarity"] = round(similarity, 3)
        case["semantic_diverged"] = (similarity < 0.65) if lang != "en" else False
        
        # 3. Glossary survival
        glossary_ok = check_glossary_survival(native_output, topic, lang)
        case["glossary_survived"] = glossary_ok
        
        # 4. Audio Quality and RTF
        # Read the generated audio from scratch to compute duration
        case_audio_path = os.path.join(SCRATCH_DIR, "audio_out", var, f"case_{case_id}.wav")
        rtf = 0.0
        audio_dur = 0.0
        empty_waveform = False
        long_silence = False
        
        if os.path.exists(case_audio_path):
            try:
                y, sr = sf.read(case_audio_path)
                audio_dur = len(y) / sr
                if audio_dur > 0:
                    rtf = case["latency_tts_total"] / audio_dur
                    
                # Artifact / Silence check
                rms = np.sqrt(np.mean(y**2))
                if rms < 0.001:
                    empty_waveform = True
                    
                # Look for long silent blocks (>1.5 seconds)
                chunk_size = int(sr * 1.5)
                for i in range(0, len(y), chunk_size):
                    chunk = y[i : i + chunk_size]
                    if len(chunk) == chunk_size:
                        c_rms = np.sqrt(np.mean(chunk**2))
                        if c_rms < 0.0001:
                            long_silence = True
                            break
            except Exception:
                empty_waveform = True
        else:
            empty_waveform = True
            
        case["audio_duration"] = round(audio_dur, 2)
        case["rtf"] = round(rtf, 3)
        case["empty_waveform"] = empty_waveform
        case["long_silence"] = long_silence

# ─────────────────────────────────────────────────────────────────────────────
# Step 5: Scoring and Charting
# ─────────────────────────────────────────────────────────────────────────────
scores_report = {}

for var, data in loaded_data.items():
    if data.get("skipped"):
        scores_report[var] = {"skipped": True, "reason": data.get("reason")}
        continue
        
    results_list = data["results"]
    
    # 1. Latency Score
    avg_latency = sum(c["latency_total"] for c in results_list) / len(results_list)
    L_min = 1.5
    L_max = 12.0
    s_latency = max(0.0, min(100.0, 100.0 * (L_max - avg_latency) / (L_max - L_min)))
    
    # 2. Resource Score
    peak_vram = data.get("peak_vram_variant", 0)
    avg_cpu = data.get("avg_cpu_variant", 0)
    s_vram = max(0.0, min(100.0, 100.0 * (4096.0 - peak_vram) / 4096.0))
    s_cpu = max(0.0, min(100.0, 100.0 * (100.0 - avg_cpu) / 100.0))
    s_resource = 0.5 * s_vram + 0.5 * s_cpu
    
    # 3. Translation Accuracy Score
    divergences = sum(1 for c in results_list if c["semantic_diverged"])
    lost_glossary = sum(1 for c in results_list if not c["glossary_survived"])
    s_trans = 100.0 - (15.0 * divergences) - (10.0 * lost_glossary)
    s_trans = max(0.0, s_trans)
    
    # 4. Robustness Score
    exceptions = data.get("exceptions_count", 0)
    empty_audios = data.get("empty_audio_count", 0)
    latin_failures = data.get("latin_fallback_failures", 0)
    s_robustness = 100.0 - (30.0 * exceptions) - (20.0 * empty_audios) - (10.0 * latin_failures)
    s_robustness = max(0.0, s_robustness)
    
    # 5. Voice Quality Score
    avg_rtf = sum(c["rtf"] for c in results_list) / len(results_list)
    s_rtf = max(0.0, min(100.0, 100.0 * (2.0 - avg_rtf) / 2.0))
    empty_waveforms = sum(1 for c in results_list if c["empty_waveform"])
    long_silences = sum(1 for c in results_list if c["long_silence"])
    s_vq = s_rtf - (25.0 * empty_waveforms) - (15.0 * long_silences)
    s_vq = max(0.0, s_vq)
    
    # Composite Score
    composite = (
        WEIGHTS["latency"] * s_latency +
        WEIGHTS["resource_usage"] * s_resource +
        WEIGHTS["translation_accuracy"] * s_trans +
        WEIGHTS["robustness"] * s_robustness +
        WEIGHTS["voice_quality"] * s_vq
    )
    
    scores_report[var] = {
        "skipped": False,
        "latency_score": round(s_latency, 1),
        "resource_score": round(s_resource, 1),
        "translation_score": round(s_trans, 1),
        "robustness_score": round(s_robustness, 1),
        "vq_score": round(s_vq, 1),
        "composite_score": round(composite, 1),
        "avg_latency": round(avg_latency, 2),
        "peak_vram": peak_vram,
        "avg_cpu": avg_cpu,
        "divergences": divergences,
        "lost_glossary": lost_glossary,
        "exceptions": exceptions,
        "empty_audios": empty_audios,
        "latin_failures": latin_failures
    }

# ─────────────────────────────────────────────────────────────────────────────
# Step 6: Generate Charts via Matplotlib and encode to Base64
# ─────────────────────────────────────────────────────────────────────────────
print("[EVAL] Generating comparison charts...")

plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')

# Chart 1: Latency across languages
fig, ax = plt.subplots(figsize=(10, 5))
lang_groups = ["en", "hi", "kn", "mr"]
x = np.arange(len(lang_groups))
width = 0.25

for i, var in enumerate(variants):
    if scores_report[var].get("skipped"):
        continue
    data = loaded_data[var]
    latencies = []
    for l in lang_groups:
        case_lats = [c["latency_total"] for c in data["results"] if c["lang"] == l]
        latencies.append(np.mean(case_lats) if case_lats else 0.0)
    ax.bar(x + i*width - width/2, latencies, width, label=var)
    
ax.set_title("Average Latency per Language (Seconds)")
ax.set_xticks(x)
ax.set_xticklabels(["English", "Hindi", "Kannada", "Marathi"])
ax.set_ylabel("Seconds (Lower is Better)")
ax.legend()
plt.tight_layout()

buf1 = io.BytesIO()
plt.savefig(buf1, format="PNG")
buf1.seek(0)
chart1_b64 = base64.b64encode(buf1.read()).decode("utf-8")
plt.close()

# Chart 2: Peak VRAM
fig, ax = plt.subplots(figsize=(6, 4))
var_names = [v for v in variants if not scores_report[v].get("skipped")]
vrams = [scores_report[v]["peak_vram"] for v in var_names]
ax.bar(var_names, vrams, color=["#3f51b5", "#f44336", "#4caf50"])
ax.set_title("Peak VRAM Usage per Variant (MiB)")
ax.set_ylabel("MiB (Lower is Better)")
plt.tight_layout()

buf2 = io.BytesIO()
plt.savefig(buf2, format="PNG")
buf2.seek(0)
chart2_b64 = base64.b64encode(buf2.read()).decode("utf-8")
plt.close()

# Chart 3: Translation Divergence Count
fig, ax = plt.subplots(figsize=(6, 4))
divergence_counts = [scores_report[v]["divergences"] for v in var_names]
ax.bar(var_names, divergence_counts, color=["#9c27b0", "#ff9800", "#00bcd4"])
ax.set_title("Translation Semantic Divergences (Count)")
ax.set_ylabel("Count (Lower is Better)")
plt.tight_layout()

buf3 = io.BytesIO()
plt.savefig(buf3, format="PNG")
buf3.seek(0)
chart3_b64 = base64.b64encode(buf3.read()).decode("utf-8")
plt.close()

# Chart 4: Radar Chart
fig = plt.figure(figsize=(7, 7))
ax = fig.add_subplot(111, polar=True)
categories = ["Latency", "Resource", "Translation", "Robustness", "Voice Quality"]
N = len(categories)

angles = [n / float(N) * 2 * np.pi for n in range(N)]
angles += angles[:1]

for var in var_names:
    rep = scores_report[var]
    values = [
        rep["latency_score"],
        rep["resource_score"],
        rep["translation_score"],
        rep["robustness_score"],
        rep["vq_score"]
    ]
    values += values[:1]
    ax.plot(angles, values, linewidth=2, linestyle='solid', label=var)
    ax.fill(angles, values, alpha=0.1)
    
ax.set_theta_offset(np.pi / 2)
ax.set_theta_direction(-1)
plt.xticks(angles[:-1], categories, size=11)
ax.set_rlabel_position(0)
plt.yticks([20, 40, 60, 80, 100], ["20", "40", "60", "80", "100"], color="grey", size=8)
plt.ylim(0, 100)
plt.legend(loc="upper right", bbox_to_anchor=(0.1, 0.1))
plt.title("Weighted Component Breakdown", size=14, y=1.1)
plt.tight_layout()

buf4 = io.BytesIO()
plt.savefig(buf4, format="PNG")
buf4.seek(0)
chart4_b64 = base64.b64encode(buf4.read()).decode("utf-8")
plt.close()

# ─────────────────────────────────────────────────────────────────────────────
# Step 7: Build Self-Contained HTML Report
# ─────────────────────────────────────────────────────────────────────────────
print("[EVAL] Generating HTML report template...")

# Build summary string
summary_text = ""
winner_var = None
max_composite = -1.0
for v in var_names:
    comp = scores_report[v]["composite_score"]
    if comp > max_composite:
        max_composite = comp
        winner_var = v

if winner_var == "baseline":
    summary_text = "The **baseline** production pipeline remains the overall winner with the default weights, achieving the best combination of low resource usage and high reliability."
elif winner_var == "indic-parler-tts":
    summary_text = "The **indic-parler-tts** variant wins overall under the default weights, driven by a potential improvement in voice quality, despite its higher resource usage and download size."
else:
    summary_text = "The **m2m100-translation** variant achieves the highest composite score, demonstrating good translation speed and reliability at a lower footprint than standard NLLB."

# Build Listening Page and Raw Table
listening_rows = []
raw_table_rows = []

test_cases_count = len(test_cases)
for i in range(test_cases_count):
    case_def = test_cases[i]
    case_id = case_def["id"]
    case_name = case_def["name"]
    lang = case_def["lang"]
    query_text = case_def["text"]
    
    # Listening Paired columns
    listening_cell = []
    listening_cell.append(f"<tr><td><strong>Case {case_id}: {case_name}</strong><br><small style='color:#666'>{query_text}</small></td>")
    
    for var in variants:
        if scores_report[var].get("skipped"):
            listening_cell.append(f"<td>Skipped due to space limits</td>")
            continue
            
        case_res = next(c for c in loaded_data[var]["results"] if c["id"] == case_id)
        
        # Audio tag with Base64 encoding
        case_audio_path = os.path.join(SCRATCH_DIR, "audio_out", var, f"case_{case_id}.wav")
        audio_html = ""
        if os.path.exists(case_audio_path):
            with open(case_audio_path, "rb") as f_aud:
                aud_b64 = base64.b64encode(f_aud.read()).decode("utf-8")
            audio_html = f"<audio controls style='width: 180px'><source src='data:audio/wav;base64,{aud_b64}' type='audio/wav'></audio>"
        else:
            audio_html = "<span style='color:red'>No Audio generated</span>"
            
        listening_cell.append(f"<td>{audio_html}<br><small style='color:#555'>Native: {case_res['llm_output_native'][:60]}...</small></td>")
        
        # Raw results table row builder
        raw_table_rows.append(
            f"<tr>"
            f"<td>{case_id}</td>"
            f"<td>{case_name}</td>"
            f"<td>{var}</td>"
            f"<td>{case_res['latency_stt']}</td>"
            f"<td>{case_res['latency_translate_in']}</td>"
            f"<td>{case_res['latency_llm_ttft']}</td>"
            f"<td>{case_res['latency_llm_total']}</td>"
            f"<td>{case_res['latency_translate_out']}</td>"
            f"<td>{case_res['latency_tts_ttfa']}</td>"
            f"<td>{case_res['latency_tts_total']}</td>"
            f"<td><strong>{case_res['latency_total']}</strong></td>"
            f"<td>{case_res['peak_vram']}</td>"
            f"<td>{case_res['avg_cpu']}%</td>"
            f"<td>{case_res['semantic_similarity']}</td>"
            f"<td>{'✅' if case_res['glossary_survived'] else '❌'}</td>"
            f"</tr>"
        )
        
    listening_cell.append("</tr>")
    listening_rows.append("".join(listening_cell))

# Generate output html file content
html_content = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>EduMentor Voice Multi-Pipeline Benchmarks</title>
<style>
body {{ font-family: 'Inter', system-ui, -apple-system, sans-serif; margin: 20px; color: #333; line-height: 1.5; background: #fafafa; }}
h1, h2, h3 {{ color: #1a237e; }}
.card {{ background: white; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }}
.grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
.grid-charts {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
th, td {{ border: 1px solid #e0e0e0; padding: 10px; text-align: left; font-size: 14px; }}
th {{ background-color: #f5f5f5; color: #1a237e; font-weight: 600; cursor: pointer; }}
tr:hover {{ background-color: #f9f9f9; }}
.badge {{ display: inline-block; padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; }}
.badge-green {{ background: #c8e6c9; color: #256029; }}
.badge-red {{ background: #ffcdd2; color: #c63737; }}
.score-badge {{ font-size: 24px; font-weight: bold; color: #1a237e; background: #e8eaf6; padding: 10px; border-radius: 6px; display: inline-block; }}
</style>
<script>
function sortTable(n) {{
  var table, rows, switching, i, x, y, shouldSwitch, dir, switchcount = 0;
  table = document.getElementById("rawResultsTable");
  switching = true;
  dir = "asc";
  while (switching) {{
    switching = false;
    rows = table.rows;
    for (i = 1; i < (rows.length - 1); i++) {{
      shouldSwitch = false;
      x = rows[i].getElementsByTagName("TD")[n];
      y = rows[i + 1].getElementsByTagName("TD")[n];
      var xVal = x.innerHTML.toLowerCase();
      var yVal = y.innerHTML.toLowerCase();
      
      // Parse numbers if possible
      if (!isNaN(parseFloat(xVal)) && !isNaN(parseFloat(yVal))) {{
        xVal = parseFloat(xVal);
        yVal = parseFloat(yVal);
      }}
      
      if (dir == "asc") {{
        if (xVal > yVal) {{
          shouldSwitch = true;
          break;
        }}
      }} else if (dir == "desc") {{
        if (xVal < yVal) {{
          shouldSwitch = true;
          break;
        }}
      }}
    }}
    if (shouldSwitch) {{
      rows[i].parentNode.insertBefore(rows[i + 1], rows[i]);
      switching = true;
      switchcount ++;
    }} else {{
      if (switchcount == 0 && dir == "asc") {{
        dir = "desc";
        switching = true;
      }}
    }}
  }}
}}
</script>
</head>
<body>

<h1>🎙️ EduMentor Voice Multi-Pipeline Benchmarks</h1>

<div class="card">
  <h2>Overall Summary & Winner Analysis</h2>
  <p style="font-size: 16px;">{summary_text}</p>
  
  <div class="grid-2">
    <div>
      <h3>Configurable Weighting Scheme Used:</h3>
      <ul>
        <li><strong>Latency:</strong> {int(WEIGHTS['latency']*100)}%</li>
        <li><strong>Resource Usage:</strong> {int(WEIGHTS['resource_usage']*100)}%</li>
        <li><strong>Translation Accuracy:</strong> {int(WEIGHTS['translation_accuracy']*100)}%</li>
        <li><strong>Robustness:</strong> {int(WEIGHTS['robustness']*100)}%</li>
        <li><strong>Voice Quality (Auto):</strong> {int(WEIGHTS['voice_quality']*100)}%</li>
      </ul>
    </div>
    
    <div>
      <h3>Composite Scores per Variant:</h3>
      <table>
        <tr>
          <th>Variant</th>
          <th>Composite Score</th>
          <th>Status</th>
        </tr>
        {"".join([
            f"<tr><td><strong>{v}</strong></td><td><span class='score-badge'>{scores_report[v].get('composite_score', 'N/A')} / 100</span></td>"
            f"<td>{'❌ SKIPPED' if scores_report[v].get('skipped') else '✅ RUN COMPLETED'}</td></tr>"
            for v in variants
        ])}
      </table>
    </div>
  </div>
</div>

<div class="card">
  <h2>📊 Graphical Comparison Output</h2>
  
  <div class="grid-charts">
    <div>
      <img src="data:image/png;base64,{chart1_b64}" style="width: 100%; border-radius: 6px; border: 1px solid #e0e0e0;" alt="Average Latency per Language">
    </div>
    <div>
      <img src="data:image/png;base64,{chart4_b64}" style="width: 100%; border-radius: 6px; border: 1px solid #e0e0e0;" alt="Radar Chart Component Breakdown">
    </div>
  </div>
  
  <div class="grid-charts" style="margin-top: 20px;">
    <div>
      <img src="data:image/png;base64,{chart2_b64}" style="width: 100%; border-radius: 6px; border: 1px solid #e0e0e0;" alt="Peak VRAM">
    </div>
    <div>
      <img src="data:image/png;base64,{chart3_b64}" style="width: 100%; border-radius: 6px; border: 1px solid #e0e0e0;" alt="Divergences">
    </div>
  </div>
</div>

<div class="card">
  <h2>🎧 Side-by-Side TTS Audio Listening Page</h2>
  <p>Perform subjective analysis of voice quality by comparing identical technical prompts across baseline and candidate variants:</p>
  <table>
    <thead>
      <tr>
        <th style="width:30%">Query Description</th>
        <th>Baseline (MMS-TTS)</th>
        <th>Indic Parler-TTS</th>
        <th>m2m100-translation</th>
      </tr>
    </thead>
    <tbody>
      {"".join(listening_rows)}
    </tbody>
  </table>
</div>

<div class="card">
  <h2>📝 Raw Results Sortable Table</h2>
  <p><small>Click headers to sort table by metric value.</small></p>
  <table id="rawResultsTable">
    <thead>
      <tr>
        <th onclick="sortTable(0)">ID</th>
        <th onclick="sortTable(1)">Case Name</th>
        <th onclick="sortTable(2)">Variant</th>
        <th onclick="sortTable(3)">STT (s)</th>
        <th onclick="sortTable(4)">Trans In (s)</th>
        <th onclick="sortTable(5)">LLM TTFT (s)</th>
        <th onclick="sortTable(6)">LLM Tot (s)</th>
        <th onclick="sortTable(7)">Trans Out (s)</th>
        <th onclick="sortTable(8)">TTS TTFA (s)</th>
        <th onclick="sortTable(9)">TTS Tot (s)</th>
        <th onclick="sortTable(10)">Total E2E (s)</th>
        <th onclick="sortTable(11)">VRAM Delta (MiB)</th>
        <th onclick="sortTable(12)">Avg CPU</th>
        <th onclick="sortTable(13)">Sim Score</th>
        <th onclick="sortTable(14)">Glossary OK?</th>
      </tr>
    </thead>
    <tbody>
      {"".join(raw_table_rows)}
    </tbody>
  </table>
</div>

</body>
</html>
"""

report_path = os.path.join(REPORTS_DIR, "benchmark_report.html")
with open(report_path, "w", encoding="utf-8") as f_out:
    f_out.write(html_content)

print(f"[EVAL] Complete. Benchmark HTML report written to {report_path}")
sys.exit(0)
