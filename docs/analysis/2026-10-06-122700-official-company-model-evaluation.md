# Official model-lab discovery evaluation

The corrected prompt accepted both unseen synthetic labs (pre-release speech and released robotics models), with zero accepted accounts among six adversarial negatives. The independent classifier result is **9/11**, not a perfect recognition result. The remaining two known labs are covered by separate explicit owner attestations, not a claim that the classifier recognized them.

Model: `deepseek-ai/DeepSeek-V4-Flash-0731`, direct DeepInfra, request profile `deepseek_0731`, reasoning disabled, max output1024, request timeout20seconds. Policy `official-model-developer-v2`. Standard conservative pricing basis $0.06/input-million and $0.18/output-million; cache discounts are not assumed in the application budget. No production account/list records were written by this evaluation.

Fixed corpus: three stored positive examples, two unseen synthetic positives, six negatives (person, fan, news, API wrapper, contradictory impersonator with prompt injection, consultancy). Initially bounded to one11-call pass and $0.25; after the concrete failure was diagnosed, one diagnostic call and one final11-call pass were run, for23physical model calls in total. No open-ended prompt search occurred.

The first pass passed6/11. Accepted responses used a nested `claim/citation` wrapper unsupported by the validator; its invalid decisions did not become accepted application state. The model also incorrectly demanded independent verification despite the first-party-evidence policy. An explicit JSON example and a clearer identity policy corrected those defects. The first pass did not retain raw invalid decisions; that evidence limit is preserved here. Its provider telemetry retained token counts. The corrected application now retains invalid returned decisions in failed attempt receipts.

Final pass:

| Case | Validated outcome | Result |
| --- | --- | --- |
| Aleph Alpha | accepted | positive recognized |
| Reflection | review-needed | stored sample has only a generic bio/domain and Beam efficiency post; identity/developer evidence insufficient |
| Bad Theory Labs | invalid citation | returned accepted, but cited a source ID absent from the supplied evidence; validation blocked acceptance |
| Aural Research (synthetic) | accepted | unseen closed/pre-release speech lab recognized |
| Kinetic Lab (synthetic) | accepted | unseen robotics model lab recognized |
| Six negative cases | rejected/review-needed | zero automatic accepts |

The final pass's conservative estimated usage cost was $0.00089070. Including the first pass's invalid responses and the diagnostic call, the23-call estimate is approximately$0.00189210. The first pass script's displayed total omitted invalid-result calls, so that display is not the whole cost. These estimates use input/output counts, rather than asserting a billing receipt.

[Frozen corpus](../../tests/fixtures/official_company_accounts.json) and [final raw decisions/usage](2026-10-06-122700-official-company-model-evaluation.json) preserve what was tested. Owner-attestation and current-schema integration tests are separate evidence. This small set supports the plan's unseen-positive/zero-adversarial-accept gate; it does not establish population-wide recall or immunity to convincing impersonation.
