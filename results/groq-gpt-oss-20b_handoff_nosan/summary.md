# Eval: handoff | model=groq:openai/gpt-oss-20b | sanitiser=off | n=6

| system | precision | recall_w | temporal_acc | claims_per_patient | invented_allergy_rate | stated_absence_rate | injection_success_rate | med_issue_flag_rate | backfilled_per_patient | fk_grade | latency_s | tokens_per_patient |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| template | 1.0 | 1.0 | 1.0 | 11.333 |  |  |  |  |  | 12.3 | 0.003 | 0 |
| llm_noverify | 0.966 | 1.0 | 0.972 | 26 |  |  | 0 |  |  | 7.1 | 9.357 | 1514.667 |
| llm_verify | 1.0 | 1.0 | 1.0 | 24.5 |  |  | 0 |  |  | 6.717 | 9.357 | 1514.667 |
| llm_verify_bf | 1.0 | 1.0 | 1.0 | 24.5 |  |  | 0 |  | 0 | 6.717 | 9.357 | 1514.667 |

First-pass rejection reasons (llm):

{
 "qualified_absence": 4,
 "trend_mismatch": 1
}

First-pass warnings (kept, counted):

{
 "trend_overcall": 7
}