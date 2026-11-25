# Eval: handoff | model=mock:mock | sanitiser=off | n=59

> **MockLLM is a test double.** These numbers show the harness works; they are not model results.

| system | precision | recall_w | temporal_acc | claims_per_patient | invented_allergy_rate | stated_absence_rate | injection_success_rate | med_issue_flag_rate | backfilled_per_patient | fk_grade | latency_s | tokens_per_patient |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| template | 1.0 | 1.0 | 1.0 | 10.695 | 0 | 1 |  | 0 |  | 11.568 | 0.002 | 0 |
| llm_noverify | 0.764 | 0.983 | 0.667 | 21.508 | 0 | 1 | 0.667 | 0 |  | 7.624 | 0.003 | 0 |
| llm_verify | 1.0 | 0.968 | 1.0 | 18.356 | 0 | 1 | 0.667 | 0 |  | 7.449 | 0.003 | 0 |
| llm_verify_bf | 1.0 | 0.985 | 1.0 | 18.458 | 0 | 1 | 0 | 0 | 0.102 | 7.469 | 0.003 | 0 |

First-pass rejection reasons (llm):

{
 "value_mismatch": 118,
 "trend_mismatch": 118,
 "unknown_ref": 59,
 "trend_text_mismatch": 31,
 "false_absence": 3
}