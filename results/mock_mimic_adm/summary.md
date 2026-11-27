# Eval: handoff | model=mock:mock | sanitiser=on | n=20

> **MockLLM is a test double.** These numbers show the harness works; they are not model results.

| system | precision | recall_w | temporal_acc | claims_per_patient | invented_allergy_rate | stated_absence_rate | injection_success_rate | med_issue_flag_rate | backfilled_per_patient | fk_grade | latency_s | tokens_per_patient |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| template | 1.0 | 1.0 | 1.0 | 83.4 |  |  |  |  |  | 9.21 | 0.058 | 0 |
| llm_noverify | 0.667 | 0.03 |  | 3 |  |  |  |  |  | 8.4 | 0.0 | 0 |
| llm_verify | 1.0 | 0.03 |  | 2 |  |  |  |  |  | 4.3 | 0.0 | 0 |
| llm_verify_bf | 1.0 | 0.132 |  | 6.1 |  |  |  |  | 4.1 | 10.085 | 0.0 | 0 |

First-pass rejection reasons (llm):

{
 "unknown_ref": 20
}

First-pass warnings (kept, counted):

{}