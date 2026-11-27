# Works through the evaluation plan within each day's free Groq quota (200K tokens/day per model, rolling window).
# Safe to run every day: finished LLM calls replay from data/cache/llm for free, and each stage stops cleanly
# (saving partial results) when a model's daily quota is reached. Stages for a model whose quota is gone exit
# after one rejected request, which costs no tokens.
# Usage (PowerShell, from the project folder):  .\run_daily.ps1
$ErrorActionPreference = "Continue"
$env:PYTHONIOENCODING = "utf-8"
$fs = ".\.venv\Scripts\fhirsum.exe"
New-Item -ItemType Directory -Force results | Out-Null
$log = "results\daily_$(Get-Date -Format yyyyMMdd).log"

function Step($name, $argList) {
  "== $name  $(Get-Date -Format HH:mm:ss)" | Tee-Object -Append $log
  # Full output (including any traceback) goes to the log; the console shows only per-patient lines and stops.
  & $fs @argList 2>&1 | ForEach-Object { "$_" } | Tee-Object -Append $log |
    Select-String -Pattern '^  \S+: template|STOPPED|^\| llm|^\| template|Error|Traceback'
}

# Subsets (stratified): every trap type + clean twins of the injection cases + clean patients.
# Explicit lists: wildcards would silently pull later-added traps into earlier stages and change their n.
$INJ3   = "injection_omit_med_0*.json,injection_no_allergy_0*.json,injection_paraphrased_0*.json"
$S17    = "clean_00[0-3].json,missing_allergies_0.json,duplicate_med_0.json,allergy_conflict_0.json," +
          "worsening_trend_0.json,stale_trend_0.json,out_of_range_0.json,duplicate_obs_0.json,$INJ3"   # 17
$INJ    = $INJ3                                                   # 3 original injections + twins (6)
$RED    = "injection_clinical_voice_0*.json,injection_allergy_retraction_0*.json,injection_split_0*.json," +
          "injection_obfuscated_0*.json,injection_delimiter_0*.json"                                   # 5 harder + twins (10)
$EXPAND = "*[a-z]_[12].json,*_[12]_twin.json"                     # seeds 1-2 of each trap: grows n to 3 per trap
$S20 = "openai/gpt-oss-20b"; $S120 = "openai/gpt-oss-120b"

# 1. Main system, both models, handoff (sanitiser on)
Step "20b  handoff S17"          @("eval","--llm","groq","--model",$S20, "--pattern",$S17,"--out","results/groq-gpt-oss-20b_handoff")
Step "120b handoff S17"          @("eval","--llm","groq","--model",$S120,"--pattern",$S17,"--out","results/groq-gpt-oss-120b_handoff")
# 2. Injection ablation: sanitiser OFF on the same injection cases (paired with step 1)
Step "20b  handoff INJ nosan"    @("eval","--llm","groq","--model",$S20, "--pattern",$INJ,"--no-sanitise","--out","results/groq-gpt-oss-20b_handoff_nosan")
Step "120b handoff INJ nosan"    @("eval","--llm","groq","--model",$S120,"--pattern",$INJ,"--no-sanitise","--out","results/groq-gpt-oss-120b_handoff_nosan")
# 3. Patient-friendly summaries (readability + fact preservation)
Step "20b  patient S17"          @("eval","--llm","groq","--model",$S20, "--pattern",$S17,"--type","patient","--out","results/groq-gpt-oss-20b_patient")
Step "120b medrec S17"           @("eval","--llm","groq","--model",$S120,"--pattern",$S17,"--type","medrec","--out","results/groq-gpt-oss-120b_medrec")
# 2b. Harder injections (clinical voice, allergy retraction, split, obfuscated, delimiter), sanitiser on and off
Step "20b  handoff RED"          @("eval","--llm","groq","--model",$S20, "--pattern",$RED,"--out","results/groq-gpt-oss-20b_handoff_red")
Step "20b  handoff RED nosan"    @("eval","--llm","groq","--model",$S20, "--pattern",$RED,"--no-sanitise","--out","results/groq-gpt-oss-20b_handoff_red_nosan")
# 3b. REAL DATA: MIMIC-IV demo on FHIR, latest admission per patient (first 20, sorted). User approved sending this
#     de-identified ODbL data to Groq on 2026-11-27. Build inputs once with: fhirsum mimic-scope
if (Test-Path "data\mimic_adm") {
  Step "20b  MIMIC handoff 20"   @("eval","--dir","data/mimic_adm","--llm","groq","--model",$S20, "--limit","20","--out","results/groq-gpt-oss-20b_mimic_handoff")
  Step "120b MIMIC handoff 20"   @("eval","--dir","data/mimic_adm","--llm","groq","--model",$S120,"--limit","20","--out","results/groq-gpt-oss-120b_mimic_handoff")
}
# 4. Prompt v2 (trend + exact-number rules), paired with the v1 runs above on the same patients
Step "20b  handoff S17 prompt v2" @("eval","--llm","groq","--model",$S20, "--pattern",$S17,"--prompt","v2","--out","results/groq-gpt-oss-20b_handoff_v2")
Step "20b  patient S17 prompt v2" @("eval","--llm","groq","--model",$S20, "--pattern",$S17,"--type","patient","--prompt","v2","--out","results/groq-gpt-oss-20b_patient_v2")
# 5. Grow n: seeds 1-2 of every trap
Step "20b  handoff EXPAND"       @("eval","--llm","groq","--model",$S20, "--pattern",$EXPAND,"--out","results/groq-gpt-oss-20b_handoff_expand")
Step "120b handoff EXPAND"       @("eval","--llm","groq","--model",$S120,"--pattern",$EXPAND,"--out","results/groq-gpt-oss-120b_handoff_expand")

"" | Tee-Object -Append $log
& $fs progress 2>&1 | Tee-Object -Append $log
