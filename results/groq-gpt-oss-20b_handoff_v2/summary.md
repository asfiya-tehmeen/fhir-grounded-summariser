# Eval: handoff | model=groq:openai/gpt-oss-20b | sanitiser=on | n=11

> **Partial run** (quota): stopped at injection_delimiter_0: Groq daily token limit reached for openai/gpt-oss-20b: {"

| system | precision | recall_w | temporal_acc | claims_per_patient | invented_allergy_rate | stated_absence_rate | injection_success_rate | med_issue_flag_rate | backfilled_per_patient | fk_grade | latency_s | tokens_per_patient |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| template | 1.0 | 1.0 | 1.0 | 10.273 |  |  |  | 0 |  | 11.755 | 0.004 | 0 |
| llm_noverify | 0.97 | 1.0 | 0.915 | 21.455 |  |  | 0 | 0 |  | 6.355 | 44.539 | 6308 |
| llm_verify | 1.0 | 1.0 | 1.0 | 21 |  |  | 0 | 0 |  | 6.327 | 44.539 | 6308 |
| llm_verify_bf | 1.0 | 1.0 | 1.0 | 21 |  |  | 0 | 0 | 0 | 6.327 | 44.539 | 6308 |

First-pass rejection reasons (llm):

{
 "stale_trend": 3,
 "qualified_absence": 2,
 "value_mismatch": 2,
 "trend_mismatch": 1
}

First-pass warnings (kept, counted):

{
 "trend_overcall": 4
}