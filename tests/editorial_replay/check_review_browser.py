"""Verify the review against recorded copies, using an isolated real browser."""

import argparse
import json
import subprocess
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--original", type=Path)
    parser.add_argument("--replay", type=Path, action="append", required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--session", default="g2-replay-review")
    args = parser.parse_args()
    fixture = json.loads(args.fixture.read_text())
    original = json.loads(args.original.read_text()) if args.original else fixture["original"]
    replays = [json.loads(path.read_text()) for path in args.replay]
    expected = {"original": original["copy"]}
    expected.update({"replay-" + str(r["assessment"]): r["copy"] for r in replays})
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
                    "reply:JSON.parse(document.querySelector('#reply-json').textContent)})")
                wire = fixture["snapshot"]["wire_request"]
                user = wire["messages"][1]["content"]
                user = user[0]["text"] if isinstance(user, list) else user
                assert observed["headline"] == copy["headline"]
                assert observed["support"] == copy["byline"]
                assert "\n\n".join(observed["paragraphs"]) == copy["article"]
                assert observed["active"] == tab and observed["visible"]
                assert not observed["overflow"], (width, run_id, tab)
                assert observed["system"] == wire["messages"][0]["content"]
                assert observed["user"] == user and observed["reply"] == copy
                cases.append({"viewport": width, "run": run_id, "tab": tab, "result": "PASS"})
            run("click", "#tab-review")
            run("reload")
            assert evaluate("document.querySelector('#run').value") == run_id
        latest = list(expected)[-1]
        run("select", "#run", latest)
        run("click", "#tab-review")
        run("screenshot", str(args.evidence / f"review-{width}.png"))
    run("click", "#copy-headline")
    assert evaluate("document.querySelector('#status').textContent") == "Copied."
    run("click", "#show-sources")
    assert evaluate("document.querySelector('.tab[aria-selected=true]').dataset.tab") == "packet"
    assert evaluate("document.querySelectorAll('#source-posts .source-post').length") == len(
        fixture["snapshot"]["source_packet"]["posts"]
    )
    run("focus", "#tab-packet")
    run("press", "ArrowRight")
    assert evaluate("document.querySelector('.tab[aria-selected=true]').dataset.tab") == "request"
    reply_file = args.evidence / "downloaded-reply.json"
    run("download", "#download-copy", str(reply_file))
    assert json.loads(reply_file.read_text()) == expected[latest]
    run("select", "#run", "original")
    run("click", "#tab-reply")
    portable = args.evidence / "downloaded-review.html"
    run("download", "#download-html", str(portable))
    assert portable.exists()
    run("open", portable.as_uri())
    assert evaluate("document.querySelector('#headline').textContent") == expected["original"]["headline"]
    assert evaluate("document.querySelector('.tab[aria-selected=true]').dataset.tab") == "reply"
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
