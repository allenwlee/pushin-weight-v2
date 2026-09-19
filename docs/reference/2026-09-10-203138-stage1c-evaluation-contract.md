# Stage 1C evaluation contract

The tracked fixture
`tests/fixtures/stage1c_evaluation_contract_v1.json` freezes what later real
quality assessments must measure. Its validation is provider-free. A valid
fixture means the measurement plan is complete; it does not mean the new
classifier, discovery queries, or extractors have passed semantic-quality
gates.

Validate it with:

```bash
python - <<'PY'
from pathlib import Path
from core.stage1c_evaluation import validate_stage1c_evaluation_contract

print(validate_stage1c_evaluation_contract(
    Path("tests/fixtures/stage1c_evaluation_contract_v1.json")
))
PY
```

The classification assessment has three separate strata:

- `prevalence` estimates false positives at natural rates;
- `rare_positive` supplies enough job and personnel positives for per-type
  precision and recall;
- `event_opportunity_boundary` tests attendance against asynchronous,
  time-bounded action-for-benefit cases.

Required slices include EN, ZH-CN, JA and official, staff, named-person, and
third-party sources. Job and personnel discovery are scored in source-post
units. Job extraction is scored in listing/requisition units. Affiliation
extraction is scored in person-brand-claim units. Organization counts remain a
separate diagnostic.

Numeric floors must be preregistered before candidate scoring. Missing support
or any failed required floor blocks a production proposal. Provider-free
fixtures and staging tests can establish schema, routing, arithmetic, and
idempotency, but real-label candidate runs and blinded adjudication remain
required before production activation.
