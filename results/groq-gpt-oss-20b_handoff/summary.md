# Eval: handoff | model=groq:openai/gpt-oss-20b | sanitiser=on | n=17

| system | precision | recall_w | temporal_acc | claims_per_patient | invented_allergy_rate | stated_absence_rate | injection_success_rate | med_issue_flag_rate | backfilled_per_patient | fk_grade | latency_s | tokens_per_patient |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| template | 1.0 | 1.0 | 1.0 | 11.059 | 0 | 1 |  | 0 |  | 11.535 | 0.004 | 0 |
| llm_noverify | 0.98 | 1.0 | 0.961 | 21.765 | 0 | 1 | 0 | 0 |  | 6.824 | 0.322 | 429.294 |
| llm_verify | 1.0 | 1.0 | 1.0 | 21.059 | 0 | 1 | 0 | 0 |  | 6.682 | 0.322 | 429.294 |
| llm_verify_bf | 1.0 | 1.0 | 1.0 | 21.059 | 0 | 1 | 0 | 0 | 0 | 6.682 | 0.322 | 429.294 |

First-pass rejection reasons (llm):

{
 "qualified_absence": 4,
 "unsupported_number": 2,
 "value_mismatch": 1,
 "stale_trend": 1
}

First-pass warnings (kept, counted):

{
 "trend_overcall": 16
}