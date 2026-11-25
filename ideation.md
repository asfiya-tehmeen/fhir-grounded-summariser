# I. FHIR-Grounded Clinical Summariser (SMART on FHIR) — Ideation

**Status:** Ideation | **Data:** REAL de-identified FHIR where licensing allows (MIMIC-IV demo on FHIR, to verify) + SYNTHETIC Synthea for scale and planted cases | **Target roles:** AI engineer (health-tech, hospitals, EHR vendors), forward-deployed AI engineer, healthcare integration engineer

**One-line pitch:** A SMART on FHIR app that writes clinician and patient summaries where every statement cites the FHIR resource it came from and is checked by code, with a red-team suite for prompt injection and missing data.

---

## 1. Why this matters

- Healthcare AI postings (for example Hippocratic AI's FDE and integration roles) ask for FHIR/HL7 integration, RAG grounded in clinical data, LLM-as-judge evaluation, HIPAA-safe pipelines and clinical safety guardrails.
- In the Gulf: M42 builds foundation models across EHR data; Fakeeh Care Group's AI Director role lists HL7, FHIR and clinical terminology standards.
- Grounded summarisation is well studied, so the differentiator here is **deterministic verification**: structured claims checked by code against FHIR data, not just another LLM judging an LLM.

## 2. How the idea was improved from v1

| v1 idea | Improved version | Why |
|---|---|---|
| Summarise a Synthea patient with citations | SMART on FHIR app that launches inside a public FHIR sandbox and reads real FHIR resources | Shows real integration skills, FDE-ready |
| LLM judges grounding | Model outputs structured claims `{text, resource_id, field, value}`; code verifies each one | Deterministic, auditable, not circular |
| One summary | Three summary types: clinician handoff, medication reconciliation, patient-friendly summary | Different risks; more interesting evaluation |
| Synthea only | Real de-identified FHIR (MIMIC-IV demo on FHIR, if licence allows) + Synthea for scale and planted traps | Real data first |
| Hallucination rate | Also omission rate (important facts missed), temporal errors, and red-team results | Omissions are as dangerous as hallucinations |

## 3. Research questions

1. **Precision:** What share of generated claims are verified by code against the record?
2. **Recall (omissions):** What share of key facts (computed from the record: active medications, abnormal recent labs, active problems, allergies) appear in the summary?
3. **Temporal reasoning:** How often does the model get trends and dates wrong (for example "improving" when values worsened)?
4. **Safety:** How often do injected instructions inside clinical text change the summary? How does the system behave when key data is missing?
5. **Audience:** Does the patient-friendly version keep the same facts while improving readability?

## 4. Data plan (real first)

| Need | Source | Real? | Notes / to verify |
|---|---|---|---|
| De-identified real patient records in FHIR | MIMIC-IV Clinical Database Demo on FHIR (PhysioNet) | ✅ Real | I believe the demo (about 100 patients) is open access; verify the licence and whether sending it to an external LLM API is allowed. If not, use a local model for this part. |
| Larger set + planted traps | Synthea FHIR R4 | ❌ Synthetic | Needed for scale and to plant specific traps (missing allergies, conflicting meds, injected text). |
| App launch environment | SMART Health IT public sandbox (launch.smarthealthit.org) | ✅ Real software | Free; patients there are synthetic. |
| FHIR server | HAPI FHIR (Docker) | ✅ Real software | Free. |
| Medication normalisation | NLM RxNav / RxNorm API | ✅ Real | Free. |
| Lab interpretation | LOINC codes and reference ranges in the records | ✅ Real | LOINC is free with registration. |
| De-identification check | Microsoft Presidio | ✅ Real software | Used as a safety layer on free text. |

## 5. System design

```
SMART on FHIR launch (sandbox or local HAPI)
          │ OAuth2 launch context (patient ID)
          ▼
FHIR fetcher (Patient, Condition, MedicationRequest, Observation, AllergyIntolerance, Encounter, DocumentReference)
          │
          ▼
Pre-processing: normalise meds (RxNorm), flag abnormal labs, build timeline, sanitise free text
          │
          ▼
Key-facts extractor (pure code) ──► "expected facts" list (for recall scoring)
          │
          ▼
LLM summariser → structured claims [{text, resource_id, field, value, date}]
          │
          ▼
Deterministic verifier: resource exists? field/value match? date consistent? trend direction correct?
          │                  │
     verified claims    rejected claims → regenerate or drop (with reason)
          ▼
Renderer: clinician handoff / med reconciliation / patient summary (citations clickable)
          │
          ▼
Evaluation harness + red-team suite
```

## 6. Evaluation plan

| Metric | How |
|---|---|
| Claim precision | Verified claims / all claims |
| Key-fact recall | Expected facts present / expected facts |
| Temporal accuracy | Trend and date claims checked against observation series |
| Unsupported-claim rate after verification | Should be near zero; report what slips through |
| Injection success rate | Red-team cases where summary changed due to injected text |
| Missing-data behaviour | Does it state "no allergy record found" vs inventing one |
| Readability (patient version) | Readability score + fact preservation vs clinician version |
| Cost/latency | Tokens and seconds per patient |

Baselines:
- Template-only summary generated by code (no LLM).
- LLM without verification.
- LLM with verification (main system).

Red-team set (planted in Synthea records): injected instructions in notes, conflicting medication lists, missing allergies, out-of-range values, duplicated records, very long histories.

## 7. Free stack and budget

- Python FastAPI backend or Next.js/TypeScript (you know both); `fhir.resources`; SMART on FHIR client library (fhirclient.js or Python); HAPI FHIR in Docker; Presidio; Pydantic/Zod; pytest/Vitest; Playwright for the UI.
- Free LLM tiers or local model; about 100–300 patients evaluated with caching.

## 8. Step-by-step plan

### Phase 0 — Verify and decide (½ day)
- [ ] Check MIMIC-IV demo on FHIR licence and LLM-use rules; record the decision.
- [ ] Decide the stack (TypeScript front end + Python verifier, or all Python).

### Phase 1 — Data and launch (2 days)
- [ ] HAPI FHIR locally; load Synthea + (if allowed) MIMIC demo FHIR.
- [ ] SMART launch working against the public sandbox and local server.
- [ ] FHIR fetcher + timeline builder + RxNorm normalisation.

### Phase 2 — Baselines (1 day)
- [ ] Key-facts extractor (code).
- [ ] Template-only summary.

### Phase 3 — LLM + verifier (3 days)
- [ ] Structured-claim prompt and schema.
- [ ] Deterministic verifier with reasons for rejection.
- [ ] Regenerate-or-drop loop.
- [ ] Three summary types; clickable citations in the UI.

### Phase 4 — Evaluation (2–3 days)
- [ ] Metrics in section 6 on real + synthetic sets (report separately).
- [ ] Red-team suite.

### Phase 5 — Ship (1–2 days)
- [ ] `REPORT.md`, Loom demo of the SMART launch, deploy UI.

## 9. Risks and mitigations

| Risk | Mitigation |
|---|---|
| MIMIC demo terms disallow external APIs | Use a local model for real-data runs; use APIs only on Synthea |
| Synthea records are simplistic | Planted traps; report real and synthetic results separately |
| SMART auth complexity | Start with the public sandbox's open launch; add auth later |
| Verifier too strict (drops useful text) | Report dropped-claim rate; allow "unverifiable narrative" section clearly labelled |

## 10. Do not claim

- Clinical safety or readiness for real patients.
- HIPAA compliance (you are not handling real PHI).
- That the patient summary is medical advice.

## 11. Stretch ideas

- Arabic patient summary (only if you can check Arabic quality).
- CDS Hooks card: show the summary inside a clinician workflow.
- Use project H's MCP tools to add label warnings for active medications.

## 12. Open questions to decide together

1. TypeScript front end or Python only?
2. Which summary type first?
3. Local model for real data, or wait for the licence check?

## 13. Resume/DM hook (fill in only after measuring)

> Built a SMART on FHIR summariser where every claim is verified by code against FHIR resources: [x]% claim precision, [y]% key-fact recall on [N] real de-identified and [N] synthetic patients, and injection success cut from [x]% to [y]%.

---

## 14. v2 improvements (2026-11-25, applied in the build)

| v1 plan | v2 change | Why |
|---|---|---|
| Model cites `resource_id` (UUIDs) | Model cites short **typed handles** (`MED-3`, `LAB-12`, `ALG-1`) that code maps back to exact `Type/id` | Copying UUIDs invites citation typos; handles make citation errors near-impossible to mistake for real refs |
| Claim `{text, resource_id, field, value}` | **Typed claims** (`condition`, `medication`, `allergy`, `lab_value`, `lab_trend`, `encounter`, `note`, `absence`, `medication_issue`, `demographic`) with a verifier per kind | Each kind has its own failure modes; one generic field check misses them |
| Check fields only | Also check the **sentence itself**: every number and date in `text` must come from the cited resources | Stops "correct fields, wrong prose", the most likely failure that passes field checks |
| Trend check = direction | Direction **+ staleness** (the latest value must be cited) **+ wording** ("fell" vs increasing) | Describing an old improving period while the patient is now worsening is the dangerous temporal error |
| Missing data = "does it say so" | First-class `absence` claims verified by code (truly zero active resources of that type) | Makes missing-data behaviour checkable, and false "no allergies" claims become hard rejections |
| Verifier catches hallucinations | **Completeness backfill:** code adds any missed safety-critical fact (allergies, high-risk meds, allergy absence), labelled as code-generated | The verifier can't see omissions. An injection that says "don't mention warfarin" passes verification by producing nothing |
| Red team = injected text | **Paired clean twins** for every injection case; success = target fact present in twin but missing in injected | Separates injection effects from ordinary model omissions |
| Sanitiser on/off | Regex quarantine + untrusted-data wrapping + backfill, each **ablated separately**; includes a *paraphrased* injection the regex cannot catch | Honest about what each layer buys |
| Safety warnings from LLM | **Code-computed safety checks** (duplicate therapy, allergy-class conflicts, critical labs, withheld note text) shown beside the summary | Deterministic alerts shouldn't depend on the model mentioning them |
| Recall = share of facts | **Weighted** recall (allergies and high-risk meds ×3, problems/meds/abnormal labs ×2, trends ×1) | Missing warfarin is worse than missing a stable LDL trend |
| 3 baselines | 4 systems: template, LLM-no-verify, LLM+verify, LLM+verify+backfill, all scored on the **same first LLM call** (paired) | Isolates each layer's contribution at no extra cost |
| Patient summary readability | Lay term + medical term in brackets ("high blood pressure (hypertension)") so patient claims stay verifiable | Plain language without losing the audit trail |
| All-cloud LLM | Pluggable Groq (free) / Claude / Ollama (local) with an on-disk cache | Reruns are free and reproducible; local option for MIMIC |

**Decisions taken (section 12):** (1) Python-only backend + vanilla JS SMART page (fhirclient.js); (2) clinician handoff first, with medrec and patient also wired; (3) MIMIC demo is ODbL open access, so external APIs are allowed by the licence, but Ollama is the conservative default for MIMIC runs.

**Phase 0 result:** MIMIC-IV Clinical Database Demo on FHIR v2.1.0 is ODbL 1.0, open access, 100 patients, and has no clinical notes. Its medication orders are all completed/stopped and diagnoses carry no `clinicalStatus`, so MIMIC needs admission-scoped summaries (next step).
