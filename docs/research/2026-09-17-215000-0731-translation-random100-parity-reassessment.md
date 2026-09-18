# 0731 translation random100 parity reassessment

This bounded reassessment verifies the archived 0731 candidate against the exact current random100 cohort. Its 100 candidate IDs equal the 100 IDs in `random100-live-input.json` and the 100 IDs in the corrected incumbent review. The input selection SHA is `23f75003f8a411720addec8a52e9364a5f45dbdf41fcbcce6b06700a282d1b6a`; its row SHA is `4b144e12056e682fb2061d44db79b6fde8c0c565189ac919e48e24ea5e54a412`.

The retained candidate output has 12 distinct source rows with a failed translation and 15 null required generated targets. That is already worse than the incumbent’s conservative **[9,10]** source interval: candidate coverage lower bound **12 > 10**. Parity therefore fails on coverage alone, before considering semantic quality. The 85 native copies are not generated-quality targets.

`translation-result.json` has the same normalized translation-row digest as the result wrapper, `53faa5e0a0c619ead14039d7dbe7fb3a3e4170ad128110b6c9835704167e39be`. The saved random100 candidate directory contains no later 0731 repeat. The prior adjudicated semantic record is retained in the new review JSON as historical evidence only: it was not freshly re-adjudicated in this bounded pass.

The archive reports 931,320 ms for the combined run and preflight price metadata of $0.06 input / $0.18 output per million tokens. Neither is a translation-only timing or billed-cost conclusion.
