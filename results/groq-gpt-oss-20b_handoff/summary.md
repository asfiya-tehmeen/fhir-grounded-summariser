# Eval: handoff | model=groq:openai/gpt-oss-20b | sanitiser=on | n=17

| system | precision | recall_w | temporal_acc | claims_per_patient | invented_allergy_rate | stated_absence_rate | injection_success_rate | med_issue_flag_rate | backfilled_per_patient | fk_grade | latency_s | tokens_per_patient |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| template | 1.0 | 1.0 | 1.0 | 11.059 | 0 | 1 |  | 0 |  | 11.535 | 0.004 | 0 |
| llm_noverify | 0.964 | 1.0 | 0.892 | 21.765 | 0 | 1 | 0 | 0 |  | 6.824 | 21.228 | 3058.529 |
| llm_verify | 1.0 | 1.0 | 1.0 | 21.059 | 0 | 1 | 0 | 0 |  | 6.659 | 21.228 | 3058.529 |
| llm_verify_bf | 1.0 | 1.0 | 1.0 | 21.059 | 0 | 1 | 0 | 0 | 0 | 6.659 | 21.228 | 3058.529 |

First-pass rejection reasons (llm):

{
 "trend_mismatch": 6,
 "qualified_absence": 4,
 "unsupported_number": 2,
 "value_mismatch": 1,
 "stale_trend": 1
}