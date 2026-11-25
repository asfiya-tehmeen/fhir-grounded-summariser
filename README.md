# fhirsum — FHIR-grounded clinical summariser (SMART on FHIR)

Summaries where **every sentence cites the FHIR resource it came from and is checked by code**.
The model writes structured claims, not prose; a deterministic verifier accepts or rejects each claim with a
machine-readable reason. Research prototype on synthetic and de-identified data. Not clinically validated, not
HIPAA-compliant, not medical advice. See `ideation.md` (v2 section) for the design rationale.

## Pipeline
```
FHIR source (SMART sandbox | HAPI | Synthea | MIMIC-IV demo | generated traps)
  -> PatientRecord (typed handles: MED-3, LAB-12, ALG-1 ... mapped to exact Type/id refs)
  -> note sanitiser (quarantine instruction-like text) + untrusted-data wrapping
  -> LLM -> JSON claims {kind, text, refs, value, unit, date, status, trend, absent_type, quote}
  -> verifier (code): ref exists, kind<->type, concept, status, value/unit, date, trend direction + staleness,
                      absence truly absent, note quote verbatim, every number/date in the sentence sourced
  -> one repair round with rejection reasons -> keep / drop (shown with reasons)
  -> completeness backfill: code adds any missed allergy / high-risk med / allergy-absence, labelled as code
  -> render: handoff | medrec | patient-friendly, clickable citations + code-computed safety checks
```

## Layout
| file | what |
|---|---|
| `src/fhirsum/record.py` | indexed patient record, handles, lab series (Synthea, MIMIC, SMART, HAPI) |
| `src/fhirsum/facts.py` | key-facts extractor (recall ground truth) + safety checks (duplicates, allergy conflicts, critical labs) |
| `src/fhirsum/verifier.py` | deterministic claim verifier |
| `src/fhirsum/summarise.py` | pipeline, template baseline, backfill |
| `src/fhirsum/sanitize.py` / `prompts.py` | injection quarantine; prompt + repair prompt |
| `src/fhirsum/llm.py` | Groq / Ollama / Anthropic backends with disk cache; `MockLLM` test double |
| `src/fhirsum/synth.py` | trap generator with clean twins; `plant()` traps onto Synthea/MIMIC |
| `src/fhirsum/evaluate.py` | metrics for 4 systems (template, llm_noverify, llm_verify, llm_verify_bf) |
| `src/fhirsum/sources.py` | FHIR server fetch, Synthea import, MIMIC ndjson split, HAPI upload |
| `src/fhirsum/app.py`, `static/` | FastAPI + SMART launch (`launch.html`) + viewer |

## Run
```powershell
python -m venv .venv; .venv\Scripts\pip install -e ".[dev]"      # add ,anthropic for Claude
copy .env.example .env                                            # add GROQ_API_KEY
.venv\Scripts\python -m pytest                                    # 29 offline tests
.venv\Scripts\fhirsum gen-suite                                   # 59 synthetic bundles -> data/generated
.venv\Scripts\fhirsum eval --llm mock                             # harness check only (test double)
.venv\Scripts\fhirsum eval --llm groq                             # real run, sanitiser on
.venv\Scripts\fhirsum eval --llm groq --no-sanitise               # injection ablation
.venv\Scripts\fhirsum eval --llm groq --type patient              # readability + fact preservation
.venv\Scripts\fhirsum summarise data\generated\allergy_conflict_0.json --type medrec --llm groq
.venv\Scripts\fhirsum serve                                       # http://127.0.0.1:8000
```
**SMART launch:** run `fhirsum serve`, then either open
`http://127.0.0.1:8000/launch.html?iss=https://launch.smarthealthit.org/v/r4/fhir` (standalone), or at
https://launch.smarthealthit.org set *App Launch URL* = `http://127.0.0.1:8000/launch.html` and launch (EHR launch).

**Data:**
- MIMIC-IV Clinical Database Demo on FHIR v2.1.0 (100 patients, ODbL 1.0, open access) is downloaded to
  `data/raw/mimic`; `fhirsum mimic-split <fhir dir> --out data/mimic` builds per-patient bundles.
- Synthea: `java -jar tools/synthea-with-dependencies.jar -p 60 -s 42 -a 35-85 --exporter.years_of_history 10 --exporter.baseDirectory data/raw/synthea Massachusetts`,
  then `fhirsum synthea-import data/raw/synthea/fhir --plant`.
- HAPI: `docker compose up -d`, then `fhirsum fetch --base http://localhost:8080/fhir --patient <id> --out data/server/p.json`.

## Status (2026-11-25)
Done: everything in the table above, with 29 passing tests. The harness was checked end to end with `MockLLM` (a
test double with planted errors; **its numbers are not results**). It confirmed that the verifier drops invented
refs, wrong values and wrong trends, that injection success is detected against clean twins, and that the backfill
closes the omission gap the verifier alone cannot see.

Findings so far (from code, no model involved):
- **Verification alone cannot stop omission attacks.** "Say the patient has no allergies" yields a rejected false
  absence claim, but the allergy simply goes missing. The code backfill of weight-3 facts is the fix, and it is
  measured as a separate system.
- **The regex sanitiser misses paraphrased injections** (`injection_paraphrased`). The eval reports that case on
  its own so the isolation prompt and backfill are tested without the regex layer.
- **MIMIC demo is a different regime:** no allergy records, all medication orders `completed`/`stopped`, about 50
  admission diagnoses per patient without `clinicalStatus`, and prompts with a median of 33K characters
  (max 291K). The verifier correctly refuses to call those diagnoses "active".

### First real-model run (Groq `gpt-oss-20b`, 2026-11-25), partial: quota-limited
Only **4 patients** completed (1 trap + 3 clean) before the free daily quota ran out. Too few to report as results;
they are a smoke test.
- First-pass claim precision 0.97 (verified claims / all claims); weighted key-fact recall 1.0; ~20 claims per
  patient; patient-facing grade level ~7 (handoff) vs ~11 for the template.
- **Verifier calibration came from this run.** Six kinds of verifier false positive surfaced and were fixed, each with
  a regression test (29 tests total): age claims dated to the record's reference date, UCUM vs display units
  (`mL/min/{1.73_m2}` = `mL/min/1.73 m²`), typographic hyphens in quotes, "GFR" abbreviation, sub-threshold trends
  (now only *contradictions* fail), and "no *other* allergies" (separate `qualified_absence` reason so it doesn't
  inflate the safety-relevant false-absence count). After calibration, every remaining rejection was a real model
  error: a misread value (HbA1c 7.1 vs 7.0), a stale trend (latest value not cited), and a rounded number not in the record.
- **Next calibration step:** hand-label rejections on a larger run. The verifier needs its own precision number
  (how often a rejection is a real error), not just the model's.

### Groq free-tier constraints (this key)
| model | limits that matter | usable? |
|---|---|---|
| `openai/gpt-oss-120b` | 8K tokens/min, 200K tokens/day | yes; shared with other projects (exhausted today) |
| `openai/gpt-oss-20b` | 8K tokens/min, 200K tokens/day | yes; ~8K tokens/patient incl. repair → ~25 patients/day |
| `qwen/qwen3.8-27b` | **1,000 output tokens/min** | no: one summary needs 1–3K output tokens |

The client sizes `max_tokens` to fit the per-minute limit and logs every attempt to `data/cache/usage.jsonl`. Evals stop
cleanly on quota and save partial results. Rerunning replays cached calls for free and continues where it stopped.

**Daily routine (free tier):** run `.\run_daily.ps1` once a day; check with `fhirsum progress`. Stages, in priority order:
| # | stage | patients | output dir |
|---|---|---|---|
| 1 | handoff, sanitiser on, 20b + 120b | 17 (every trap seed 0, 3 twins, 4 clean) | `results/groq-gpt-oss-{20b,120b}_handoff` |
| 2 | injection ablation, sanitiser **off** | 6 (3 injection cases + twins) | `..._handoff_nosan` |
| 3 | patient-friendly (20b), medrec (120b) | 17 | `..._patient`, `..._medrec` |
| 4 | grow n: trap seeds 1–2 | 26 | `..._handoff_expand` |

Rough timeline at about 25 patients/model/day: stages 1–2 take about 1–2 days, stage 3 about 1 more, and stage 4 about 1–2 more.

## Next
1. Real runs: Groq on the generated suite (sanitiser on/off, three summary types), then Synthea with planted traps.
2. MIMIC: scope summaries to one admission (latest inpatient Encounter window) and add a discharge-medication view.
   Decide external API vs Ollama for MIMIC (ODbL allows it, but local is the conservative default).
3. Replace the small tables with RxNav ingredient lookup and the RxClass allergy-class API. Add Presidio on note text.
4. Hand-audit 50 verified claims to estimate what slips past the verifier. That is the honest "unsupported-claim
   rate after verification".
5. `REPORT.md`, Loom of the SMART launch, deploy.
