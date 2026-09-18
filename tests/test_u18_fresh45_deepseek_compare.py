from scripts import u18_fresh45_deepseek_compare as subject


def test_logical_requests_keep_sol_evidence_and_semantics():
    packets = subject.shared.packets()
    body = subject.logical_request(packets[:15], "content")
    assert body["model"] == "deepseek-v4-flash"
    assert body["thinking"] == {"type": "disabled"}
    assert subject.shared.CONTENT_PROMPT in body["system"]
    assert "OUTPUT CONTRACT" in body["system"]
    assert "owner" not in body["messages"][0]["content"].lower()


def test_peak_reservation_is_bounded():
    packets = subject.shared.packets()
    batches = [packets[index:index + 15] for index in range(0, 45, 15)]
    requests = {role: [subject.logical_request(batch, role) for batch in batches] for role in ("content", "brand")}
    assert subject.token_reservation(requests) < subject.HARD_CAP
