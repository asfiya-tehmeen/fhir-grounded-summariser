# Eval: patient | model=groq:openai/gpt-oss-20b | sanitiser=on | n=14

> **Offline re-score:** repair round not available for 3 patient(s) (answer not cached); their llm_verify rows are first-pass verified claims only.

> **Partial run** (quota): stopped at out_of_range_0: offline: no cached answer for this openai/gpt-oss-20b prompt

| system | precision | recall_w | temporal_acc | claims_per_patient | invented_allergy_rate | stated_absence_rate | injection_success_rate | med_issue_flag_rate | backfilled_per_patient | fk_grade | latency_s | tokens_per_patient |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| template | 1.0 | 1.0 | 1.0 | 10.857 | 0 | 1 |  | 0 |  | 11.936 | 0.003 | 0 |
| llm_noverify | 0.968 | 1.0 | 0.882 | 20.929 | 0 | 1 | 0 | 0 |  | 4.386 | 0.0 | 0 |
| llm_verify | 1.0 | 1.0 | 1.0 | 20.5 | 0 | 1 | 0 | 0 |  | 4.471 | 0.0 | 0 |
| llm_verify_bf | 1.0 | 1.0 | 1.0 | 20.5 | 0 | 1 | 0 | 0 | 0 | 4.471 | 0.0 | 0 |

First-pass rejection reasons (llm):

{
 "unsupported_number": 8,
 "trend_mismatch": 3,
 "stale_trend": 2,
 "date_mismatch": 1,
 "text_date_unsupported": 1,
 "unit_mismatch": 1
}

First-pass warnings (kept, counted):

{
 "trend_overcall": 4
}