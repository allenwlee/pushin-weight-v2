from core.product_release_report import render_report, significance


def test_substance_is_ranked_without_attention_or_publisher_fame():
    primary = significance(
        product_kind="general_model", lineage="primary", change="major"
    )
    derivative = significance(
        product_kind="general_model", lineage="derivative", change="major"
    )
    ablation = significance(
        product_kind="general_model", lineage="ablation", change="major"
    )
    assert primary[0] > derivative[0] > ablation[0]
    assert (
        significance(product_kind="agent", lineage="unknown", change="unknown")[0]
        is None
    )


def test_report_escapes_sources_and_never_makes_javascript_links():
    html = render_report(
        [
            {
                "id": "one",
                "name": "<script>bad()</script>",
                "state": "pending",
                "publisher": "Unverified",
                "score": None,
                "reason": "Awaiting evidence",
                "claims": [
                    {
                        "kind": "announcement",
                        "value": "unknown",
                        "url": "javascript:bad()",
                        "excerpt": '<img src=x onerror="bad()">',
                    }
                ],
                "sources": 1,
                "accounts": 1,
                "discussion": [],
            }
        ],
        title="Study",
        notes="Stored sources only",
    )
    assert "<script>bad()" not in html
    assert 'href="javascript:' not in html
    assert "&lt;script&gt;" in html
    assert "addEventListener" in html
