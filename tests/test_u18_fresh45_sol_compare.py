from scripts import u18_fresh45_sol_compare as subject


def test_blind_packet_shape_and_targets():
    packets = subject.packets()
    assert len(packets) == 45
    assert [row["case_id"] for row in packets] == [f"L45-{number:02d}" for number in range(1, 46)]
    assert sum(len(row["brand_ids"]) for row in packets) == 57
    forbidden_keys = {"owner", "benchmark", "comments", "answers"}
    assert all(not (set(row) & forbidden_keys) for row in packets)
    assert all(not (set(row["context"]) & forbidden_keys) for row in packets)


def test_owner_blank_is_unreviewed_but_explicit_sentinel_is_reviewed():
    assert subject.reviewed([]) is False
    assert subject.reviewed("") is False
    assert subject.reviewed(["none"]) is True
    assert subject.reviewed("unknown") is True


def test_rendered_sol_values_are_visibly_red():
    # The durable style contract is kept as literal CSS in the renderer.
    source = subject.Path(subject.__file__).read_text()
    assert "--red:#b42318" in source
    assert '<div class="sol"><small>SOL</small>' in source
