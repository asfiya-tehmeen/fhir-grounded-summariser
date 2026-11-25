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
  & $fs @argList 2>&1 | Select-String -Pattern '^  \S+: template|STOPPED|^\| llm|^\| template' | Tee-Object -Append $log
}

# Subsets (stratified): every trap type + clean twins of the injection cases + clean patients.
$S17    = "clean_00[0-3].json,*[a-z]_0.json,*_0_twin.json"       # seed 0 of each trap, 3 twins, 4 clean
$INJ    = "injection_*_0.json,injection_*_0_twin.json"            # injection cases + twins only (ablation)
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
# 4. Grow n: seeds 1-2 of every trap
Step "20b  handoff EXPAND"       @("eval","--llm","groq","--model",$S20, "--pattern",$EXPAND,"--out","results/groq-gpt-oss-20b_handoff_expand")
Step "120b handoff EXPAND"       @("eval","--llm","groq","--model",$S120,"--pattern",$EXPAND,"--out","results/groq-gpt-oss-120b_handoff_expand")

"" | Tee-Object -Append $log
& $fs progress 2>&1 | Tee-Object -Append $log
