"""Verify the review against recorded copies, using an isolated real browser."""

import argparse
import json
import subprocess
from pathlib import Path

from build_review import build_manifest, build_payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--original", type=Path)
    parser.add_argument("--replay", type=Path, action="append", default=[])
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--session", default="g2-replay-review")
    args = parser.parse_args()
    if args.manifest:
        groups = build_manifest(args.manifest)["cases"]
    else:
        if not args.fixture:
            raise ValueError("provide a fixture or manifest")
        fixture = json.loads(args.fixture.read_text())
        original = json.loads(args.original.read_text()) if args.original else fixture["original"]
        groups = [build_payload(fixture, original, [json.loads(p.read_text()) for p in args.replay])]
    expected = {run["id"]: run["copy"] for group in groups for run in group["runs"]}
    group_for = {run["id"]: group for group in groups for run in group["runs"]}
    args.evidence.mkdir(parents=True, exist_ok=True)
    cli = ["agent-browser", "--session", args.session]

    def run(*command, stdin=None):
        result = subprocess.run(cli + list(command), input=stdin, text=True,
                                capture_output=True, timeout=60, check=True)
        return result.stdout

    def evaluate(expression):
        raw = run("eval", "--stdin", stdin="JSON.stringify(" + expression + ")")
        value = json.loads(raw)
        return json.loads(value) if isinstance(value, str) else value

    cases = []
    for width in (1440, 390):
        run("set", "viewport", str(width), "900")
        run("open", args.url)
        for run_id, copy in expected.items():
            run("select", "#run", run_id)
            for tab in ("review", "packet", "request", "reply"):
                run("click", "#tab-" + tab)
                observed = evaluate("({headline:document.querySelector('#headline').textContent,"
                    "support:document.querySelector('#support').textContent,"
                    "paragraphs:Array.from(document.querySelectorAll('#article p')).map(p=>p.textContent),"
                    "active:document.querySelector('.tab[aria-selected=true]').dataset.tab,"
                    "overflow:document.documentElement.scrollWidth>innerWidth,"
                    "visible:document.querySelector('#headline').getBoundingClientRect().height>0,"
                    "system:document.querySelector('#system').textContent,"
                    "user:document.querySelector('#user').textContent,"
                    "reply:JSON.parse(document.querySelector('#reply-json').textContent),"
                    "packet:JSON.parse(document.querySelector('#packet-json').textContent),"
                    "baseline:document.querySelector('#baseline-headline').textContent,"
                    "hash:document.querySelector('#technical dd').textContent})")
                group = group_for[run_id]
                wire = group["wire"]
                user = wire["messages"][1]["content"]
                user = user[0]["text"] if isinstance(user, list) else user
                assert observed["headline"] == copy["headline"]
                assert observed["support"] == copy["byline"]
                assert "\n\n".join(observed["paragraphs"]) == copy["article"]
                assert observed["active"] == tab and observed["visible"]
                assert not observed["overflow"], (width, run_id, tab)
                assert observed["system"] == wire["messages"][0]["content"]
                assert observed["user"] == user and observed["reply"] == copy
                assert observed["packet"] == group["packet"]
                assert observed["hash"] == group["conditions"]["request_hash"]
                baseline = group.get("comparison") or {"copy": group["runs"][0]["copy"]}
                assert observed["baseline"] == baseline["copy"]["headline"]
                cases.append({"viewport": width, "run": run_id, "tab": tab, "result": "PASS"})
            run("click", "#tab-review")
            run("reload")
            assert evaluate("document.querySelector('#run').value") == run_id
        latest = list(expected)[-1]
        run("select", "#run", latest)
        run("click", "#tab-review")
        evaluate("window.scrollTo({top:0,behavior:'instant'})")
        run("screenshot", str(args.evidence / f"review-{width}.png"))
        for group in groups:
            run("select", "#run", group["defaultRun"])
            evaluate("window.scrollTo({top:0,behavior:'instant'})")
            run("screenshot", str(args.evidence / f"{group['defaultRun']}-{width}.png"))
        run("select", "#run", latest)
    run("click", "#copy-headline")
    assert evaluate("document.querySelector('#status').textContent") == "Copied."
    # Bring the actual click target fully into view; a fractional visible edge
    # can make the browser driver's physical click land outside the viewport.
    evaluate("window.scrollTo({top:0,behavior:'instant'})")
    assert evaluate("(()=>{const r=document.querySelector('#show-sources').getBoundingClientRect();"
                    "return r.top>=0&&r.bottom<=innerHeight})()")
    run("click", "#show-sources")
    assert evaluate("document.querySelector('.tab[aria-selected=true]').dataset.tab") == "packet"
    assert evaluate("document.querySelectorAll('#source-posts .source-post').length") == len(
        group_for[latest]["packet"]["posts"]
    )
    run("focus", "#tab-packet")
    run("press", "ArrowRight")
    assert evaluate("document.querySelector('.tab[aria-selected=true]').dataset.tab") == "request"
    reply_file = args.evidence / "downloaded-reply.json"
    run("download", "#download-copy", str(reply_file))
    assert json.loads(reply_file.read_text()) == expected[latest]
    portable_run = groups[1]["defaultRun"] if len(groups) > 1 else "original"
    run("select", "#run", portable_run)
    run("click", "#tab-reply")
    portable = args.evidence / "downloaded-review.html"
    run("download", "#download-html", str(portable))
    assert portable.exists()
    run("open", portable.as_uri())
    assert evaluate("document.querySelector('#headline').textContent") == expected[portable_run]["headline"]
    assert evaluate("document.querySelector('.tab[aria-selected=true]').dataset.tab") == "reply"
    assert evaluate("JSON.parse(document.querySelector('#packet-json').textContent)") == group_for[portable_run]["packet"]
    errors = json.loads(run("errors", "--json"))
    assert errors["data"]["errors"] == [], errors
    report = {"result": "PASS", "browser_states": cases,
              "reload_selection": "PASS", "source_navigation": "PASS",
              "keyboard_tabs": "PASS", "copy_headline": "PASS",
              "reply_download": "PASS", "portable_html_selection": "PASS",
              "page_errors": 0, "driver": "agent-browser"}
    (args.evidence / "browser-checks.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"result": "PASS", "browser_states": len(cases), "extra_interactions": 6}))


if __name__ == "__main__":
    main()
