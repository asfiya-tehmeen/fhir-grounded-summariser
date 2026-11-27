# Eval: patient | model=groq:openai/gpt-oss-20b | sanitiser=on | n=17

| system | precision | recall_w | temporal_acc | claims_per_patient | invented_allergy_rate | stated_absence_rate | injection_success_rate | med_issue_flag_rate | backfilled_per_patient | fk_grade | latency_s | tokens_per_patient |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| template | 1.0 | 1.0 | 1.0 | 11.059 | 0 | 1 |  | 0 |  | 11.535 | 0.004 | 0 |
| llm_noverify | 0.968 | 1.0 | 0.893 | 21 | 0 | 1 | 0 | 0 |  | 4.529 | 12.221 | 1988.294 |
| llm_verify | 1.0 | 1.0 | 1.0 | 20.824 | 0 | 1 | 0 | 0 |  | 4.524 | 12.221 | 1988.294 |
| llm_verify_bf | 1.0 | 1.0 | 1.0 | 20.824 | 0 | 1 | 0 | 0 | 0 | 4.524 | 12.221 | 1988.294 |

First-pass rejection reasons (llm):

{
 "unsupported_number": 8,
 "trend_mismatch": 3,
 "stale_trend": 2,
 "text_date_unsupported": 2,
 "date_mismatch": 1,
 "unit_mismatch": 1,
 "qualified_absence": 1
}

First-pass warnings (kept, counted):

{
 "trend_overcall": 5
}