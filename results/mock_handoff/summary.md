# Eval: handoff | model=mock:mock | sanitiser=on | n=59

> **MockLLM is a test double.** These numbers show the harness works; they are not model results.

| system | precision | recall_w | temporal_acc | claims_per_patient | invented_allergy_rate | stated_absence_rate | injection_success_rate | med_issue_flag_rate | backfilled_per_patient | fk_grade | latency_s | tokens_per_patient |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| template | 1.0 | 1.0 | 1.0 | 10.695 | 0 | 1 |  | 0 |  | 11.568 | 0.002 | 0 |
| llm_noverify | 0.767 | 1.0 | 0.667 | 21.559 | 0 | 1 | 0 | 0 |  | 7.642 | 0.002 | 0 |
| llm_verify | 1.0 | 0.985 | 1.0 | 18.559 | 0 | 1 | 0 | 0 |  | 7.451 | 0.002 | 0 |
| llm_verify_bf | 1.0 | 0.985 | 1.0 | 18.559 | 0 | 1 | 0 | 0 | 0 | 7.451 | 0.002 | 0 |

First-pass rejection reasons (llm):

{
 "value_mismatch": 118,
 "trend_mismatch": 118,
 "unknown_ref": 59,
 "trend_text_mismatch": 31
}