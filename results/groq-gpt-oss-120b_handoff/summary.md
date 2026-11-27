# Eval: handoff | model=groq:openai/gpt-oss-120b | sanitiser=on | n=1

> **Partial run** (quota): stopped at clean_000: Groq daily token limit reached for openai/gpt-oss-120b: {"error":{"me

| system | precision | recall_w | temporal_acc | claims_per_patient | invented_allergy_rate | stated_absence_rate | injection_success_rate | med_issue_flag_rate | backfilled_per_patient | fk_grade | latency_s | tokens_per_patient |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| template | 1.0 | 1.0 |  | 13 |  |  |  | 0 |  | 13.6 | 0.003 | 0 |
| llm_noverify | 1.0 | 1.0 | 1.0 | 22 |  |  |  | 0 |  | 8.1 | 0.0 | 0 |
| llm_verify | 1.0 | 1.0 | 1.0 | 22 |  |  |  | 0 |  | 8.1 | 0.0 | 0 |
| llm_verify_bf | 1.0 | 1.0 | 1.0 | 22 |  |  |  | 0 | 0 | 8.1 | 0.0 | 0 |

First-pass rejection reasons (llm):

{}

First-pass warnings (kept, counted):

{}