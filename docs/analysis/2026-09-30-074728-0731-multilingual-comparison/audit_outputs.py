"""Explain delivered-output defects without repairing or rescoring any answer."""
from collections import Counter
import json

import run

run.verify()
requests = run.read("requests.json")
scores = run.read("scores.json")
questions = run.read("packet.json")["questions"]
field_rows = {(r["request_id"], r["field"]): r for r in scores["rows"]}
defects = []
for index, item in enumerate(requests):
    receipt = run.read(f"events/finished_{index}.json")["value"]
    provider = json.loads(receipt["raw_body"])
    text = provider["choices"][0]["message"]["content"]
    prefix = {"request_id": item["request_id"], "arm": item["arm"]}
    try:
        output = json.loads(text, object_pairs_hook=run.strict_object)
    except (ValueError, TypeError) as error:
        defects.append(prefix | {"reason": "invalid_json", "fields_affected": 38,
            "parser_error": str(error), "content_end": text[-100:]})
        continue
    assert isinstance(output, dict) and isinstance(output.get("answers"), dict)
    answers = output["answers"]
    if not answers:
        defects.append(prefix | {"reason": "empty_answer_map", "fields_affected": 38,
            "content": text})
        continue
    for field, question in questions.items():
        row = field_rows[(item["request_id"], field)]
        if row["valid"]:
            continue
        answer = answers.get(field)
        if isinstance(answer, dict) and question["type"] == "noul" and answer.get("label") in ("true", "false"):
            reason = "string_boolean_instead_of_json_boolean"
        elif row.get("label_valid"):
            reason = "probability_format_or_label_consistency"
        else:
            reason = "other_invalid_or_missing_field"
        defects.append(prefix | {"field": field, "reason": reason, "fields_affected": 1, "answer": answer})
assert sum(r["fields_affected"] for r in defects) == sum(not r["valid"] for r in scores["rows"])
summary = {}
for arm in ("raw", "translated"):
    part = [r for r in defects if r["arm"] == arm]
    error_rows = [r for r in scores["rows"] if r["arm"] == arm and not r["correct"]]
    certain = [r for r in scores["rows"] if r["arm"] == arm and r["valid"] and r["selected_probability"] == 1]
    summary[arm] = {"responses_with_invalid_fields": len({r["request_id"] for r in part}),
        "defect_fields": {reason: sum(r["fields_affected"] for r in part if r["reason"] == reason)
                          for reason in sorted({r["reason"] for r in part})},
        "total_errors": len(error_rows), "invalid_errors": sum(not r["valid"] for r in error_rows),
        "valid_but_disagrees": sum(r["valid"] for r in error_rows),
        "probability_exactly_one": len(certain), "probability_one_disagreements": sum(not r["correct"] for r in certain)}
result = {"scope": "Post-result error decomposition; no score/reference/payload repair or new model calls.",
    "summary": summary, "defects": defects}
run.save("output-audit.json", result)
print(json.dumps(summary, indent=2))
