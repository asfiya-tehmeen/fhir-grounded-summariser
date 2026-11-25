# Eval: handoff | model=groq:openai/gpt-oss-20b | sanitiser=on | n=4

> **Partial run** (quota): stopped at clean_003: Groq daily token limit reached for openai/gpt-oss-20b: {"error":{"mes

| system | precision | recall_w | temporal_acc | claims_per_patient | invented_allergy_rate | stated_absence_rate | injection_success_rate | med_issue_flag_rate | backfilled_per_patient | fk_grade | latency_s | tokens_per_patient |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| template | 1.0 | 1.0 | 1.0 | 11.75 |  |  |  | 0 |  | 11.15 | 0.004 | 0 |
| llm_noverify | 0.97 | 1.0 | 0.875 | 19.75 |  |  |  | 0 |  | 7.3 | 0.013 | 0 |
| llm_verify | 1.0 | 1.0 | 1.0 | 20 |  |  |  | 0 |  | 7.225 | 0.013 | 0 |
| llm_verify_bf | 1.0 | 1.0 | 1.0 | 20 |  |  |  | 0 | 0 | 7.225 | 0.013 | 0 |

First-pass rejection reasons (llm):

{
 "value_mismatch": 1,
 "stale_trend": 1,
 "unsupported_number": 1
}