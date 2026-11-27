# Eval: handoff | model=groq:openai/gpt-oss-20b | sanitiser=on | n=1

> **Partial run** (quota): stopped at crashed: RuntimeError: Groq 413: {"error":{"message":"Request too large for mode

| system | precision | recall_w | temporal_acc | claims_per_patient | invented_allergy_rate | stated_absence_rate | injection_success_rate | med_issue_flag_rate | backfilled_per_patient | fk_grade | latency_s | tokens_per_patient |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| template | 1.0 | 1.0 | 1.0 | 70 |  |  |  |  |  | 10.0 | 0.015 | 0 |
| llm_noverify | 0.931 | 0.894 | 0.895 | 58 |  |  |  |  |  | 7.9 | 68.06 | 10845 |
| llm_verify | 1.0 | 0.814 | 1.0 | 54 |  |  |  |  |  | 8.2 | 68.06 | 10845 |
| llm_verify_bf | 1.0 | 0.841 | 1.0 | 55 |  |  |  |  | 1 | 8.2 | 68.06 | 10845 |

First-pass rejection reasons (llm):

{
 "concept_mismatch": 2,
 "date_mismatch": 1,
 "text_date_unsupported": 1,
 "no_citation": 1
}

First-pass warnings (kept, counted):

{
 "trend_overcall": 2
}