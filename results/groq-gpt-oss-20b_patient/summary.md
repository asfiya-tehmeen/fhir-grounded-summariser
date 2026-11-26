# Eval: patient | model=groq:openai/gpt-oss-20b | sanitiser=on | n=14

> **Partial run** (quota): stopped at out_of_range_0: Groq daily token limit reached for openai/gpt-oss-20b: {"error":

| system | precision | recall_w | temporal_acc | claims_per_patient | invented_allergy_rate | stated_absence_rate | injection_success_rate | med_issue_flag_rate | backfilled_per_patient | fk_grade | latency_s | tokens_per_patient |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| template | 1.0 | 1.0 | 1.0 | 10.857 | 0 | 1 |  | 0 |  | 11.936 | 0.003 | 0 |
| llm_noverify | 0.968 | 1.0 | 0.882 | 20.929 | 0 | 1 | 0 | 0 |  | 4.386 | 35.884 | 4757.857 |
| llm_verify | 1.0 | 1.0 | 1.0 | 20.857 | 0 | 1 | 0 | 0 |  | 4.364 | 35.884 | 4757.857 |
| llm_verify_bf | 1.0 | 1.0 | 1.0 | 20.857 | 0 | 1 | 0 | 0 | 0 | 4.364 | 35.884 | 4757.857 |

First-pass rejection reasons (llm):

{
 "unsupported_number": 8,
 "trend_mismatch": 3,
 "stale_trend": 2,
 "date_mismatch": 1,
 "text_date_unsupported": 1,
 "unit_mismatch": 1
}