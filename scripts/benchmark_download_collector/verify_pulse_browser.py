"""Verify the real opt-in page using an owned agent-browser session.

Usage: python -m scripts.benchmark_download_collector.verify_pulse_browser
  --url http://localhost:PORT/benchmarks/CONTRACT/deepseek/?end=2026-10-06
  --output .local/pulse-browser --session benchmark-review
Requires a retained real-data comparison and a later Arena baseline.
"""

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path


def verify_release_response(browser, check, screenshot, url):
    browser("set", "viewport", "1440", "1080")
    browser("open", url)
    browser("wait", "#legend button")
    browser("snapshot", "-i")
    check('document.querySelectorAll("#legend button").length === 3')
    check(
        '[...document.querySelectorAll("path.series")].length === 3 && [...document.querySelectorAll("path.series")].every(p=>p.getTotalLength()>20)'
    )
    check('document.querySelector(".reference-band").width.baseVal.value > 0')
    check(
        'document.querySelectorAll("#arena-chart .publication-point").length > 0 && document.querySelectorAll("#arena-chart .confidence-interval").length > 0'
    )
    browser("click", "#sources-open")
    check('document.querySelector("#sources").open')
    browser(
        "eval",
        '(async()=>{window.pulseEvidence=await fetch(document.querySelector("#download-data").href).then(r=>r.json());return {revision:pulseEvidence.reference.revision,lines:pulseEvidence.lines.length};})()',
    )
    check(
        'pulseEvidence.chart_kind === "release_response_v1" && pulseEvidence.reference.dates.length === 7'
    )
    check("pulseEvidence.lines.every(l=>l.points.some(p=>p.percent_change !== null))")
    check("pulseEvidence.arena_panel.source_identifiers.length === 1")
    revision = json.loads(browser("eval", "pulseEvidence.reference.revision"))
    check(
        'pulseEvidence.lines[1].transform === "adjacent_snapshot_difference" && pulseEvidence.lines[1].points.some(p=>p.evidence.length === 2)'
    )
    browser("press", "Escape")
    screenshot("response-desktop.png")
    browser(
        "eval",
        'window.smoothedPaths=[...document.querySelectorAll("path.series")].map(p=>p.getAttribute("d"));true',
    )
    browser("select", "#smoothing", "1")
    check(
        'document.querySelector("#scale-explanation").innerText.includes("daily values") && [...document.querySelectorAll("path.series")].some((p,i)=>p.getAttribute("d")!==smoothedPaths[i])'
    )
    browser("select", "#smoothing", "3")
    for key in ("posts", "downloads", "tokens"):
        selector = f'#legend button[data-line="{key}"]'
        browser("click", selector)
        check('document.querySelectorAll("path.series").length === 2')
        browser("click", selector)
        check('document.querySelectorAll("path.series").length === 3')
    browser("focus", "#day")
    browser("press", "Home")
    check(
        'document.querySelector("#day").value === "0" && document.querySelector("#arena-readout").innerText.includes(pulseEvidence.arena_panel.source_identifiers[0])'
    )
    browser("press", "ArrowRight")
    check('document.querySelector("#day").value === "1"')
    browser("select", "#date-axis", "relative")
    check(
        '[...document.querySelectorAll("#pulse-chart text")].some(n=>n.textContent.includes("Day "))'
    )
    browser("select", "#arena-measurement", "rank")
    check('document.querySelector("#arena-chart .arena-rank").getTotalLength() > 20')
    browser("select", "#arena-measurement", "score")
    browser("select", "#scale", "raw")
    browser("select", "#raw-series", "downloads")
    check(
        'document.querySelectorAll("path.series").length === 1 && document.querySelector("#readout").innerText.includes("Reported rolling 30-day counter")'
    )
    browser("select", "#scale", "linear")
    browser("select", "#date-axis", "calendar")
    browser("set", "viewport", "390", "844")
    check(
        'document.documentElement.scrollWidth <= innerWidth && document.querySelector("#pulse-chart").getBoundingClientRect().width > 300'
    )
    screenshot("response-mobile.png")
    browser("set", "viewport", "1440", "1080")
    browser("select", "#range", "available")
    browser("wait", "#legend button")
    browser("click", "#sources-open")
    check(
        f'await fetch(document.querySelector("#download-data").href).then(r=>r.json()).then(d=>d.reference.revision==={json.dumps(revision)})'
    )
    browser("press", "Escape")
    browser("snapshot", "-i")
    provider = browser(
        "get", "attr", "#usage-provider option:not([selected])", "value"
    ).strip()
    browser("select", "#usage-provider", provider)
    browser("wait", "#legend button")
    browser("click", "#sources-open")
    check(
        'await fetch(document.querySelector("#download-data").href).then(r=>r.json()).then(d=>d.lines[2].source==="opencode" && d.lines[2].points.some(p=>p.raw_value!==null))'
    )
    check(
        'document.querySelector("#source-details").innerText.includes("Go + free") && document.querySelector("#source-details").innerText.includes("approximate")'
    )
    browser("press", "Escape")
    screenshot("response-opencode.png")
    browser("open", url.replace("deepseek-response", "glm-response"))
    browser("wait", "#legend button")
    check(
        'document.querySelector("h1").innerText.includes("GLM") && [...document.querySelectorAll("path.series")].length===3'
    )
    screenshot("response-glm.png")
    errors = browser("errors").strip()
    if errors:
        raise RuntimeError(f"Browser errors: {errors}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--session", required=True)
    parser.add_argument("--expected-lines", type=int, default=5)
    parser.add_argument("--engagement", action="store_true")
    parser.add_argument("--release-response", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    receipt = []

    def browser(*command):
        completed = subprocess.run(
            ["agent-browser", "--session", args.session, *command],
            capture_output=True,
            text=True,
            timeout=45,
            check=True,
        )
        receipt.append({"command": list(command), "output": completed.stdout.strip()})
        return completed.stdout

    def check(expression):
        browser(
            "eval",
            f'(async () => {{ if (!({expression})) throw new Error("Pulse assertion failed"); return true; }})()',
        )

    def screenshot(name):
        result = browser("screenshot")
        match = re.search(r"Screenshot saved to (.+)", result)
        if not match:
            raise RuntimeError("Screenshot evidence missing")
        shutil.copyfile(match.group(1).strip(), args.output / name)

    try:
        if args.release_response:
            verify_release_response(browser, check, screenshot, args.url)
            (args.output / "result.json").write_text(
                json.dumps(
                    {"status": "passed", "url": args.url, "checks": receipt}, indent=2
                )
            )
            return
        browser("set", "viewport", "1440", "1080")
        browser("open", args.url)
        browser("wait", "#legend button")
        check(
            f'document.querySelectorAll("path.series").length === {args.expected_lines}'
        )
        check(
            f'document.querySelectorAll("#legend button").length === {args.expected_lines}'
        )
        check(
            'document.querySelector("#readout").innerText.includes("later than launch")'
        )
        check(
            'document.querySelector("#pulse-chart").getBoundingClientRect().height > 300'
        )
        check(
            f'new Set([...document.querySelectorAll("path.series")].map(p=>p.getAttribute("stroke"))).size === {args.expected_lines}'
        )
        screenshot("desktop.png")
        keys = ["posts", "downloads", "tokens", "score", "rank"]
        if args.engagement:
            keys += ["hf_likes", "hf_followers"]
        for key in keys:
            selector = f'#legend button[data-line="{key}"]'
            browser("click", selector)
            check(
                f'document.querySelector({json.dumps(selector)}).getAttribute("aria-pressed") === "false" && document.querySelectorAll("path.series").length === {args.expected_lines - 1}'
            )
            browser("click", selector)
            check(
                f'document.querySelectorAll("path.series").length === {args.expected_lines}'
            )
        browser("focus", "#day")
        browser("press", "Home")
        check('document.querySelector("#day").value === "0"')
        check('document.querySelector("#readout").innerText.includes("0%")')
        check('document.querySelector("#readout").innerText.includes("Not available")')
        browser("press", "End")
        browser("select", "#scale", "linear")
        check(
            'document.querySelector("#scale-explanation").innerText.startsWith("Linear scale")'
        )
        screenshot("linear.png")
        browser("select", "#scale", "raw")
        browser("select", "#raw-series", "rank")
        check('document.querySelectorAll("path.series").length === 1')
        check(
            'document.querySelector("#readout").innerText.includes("Lower rank is better")'
        )
        screenshot("raw-rank.png")
        browser("click", "#sources-open")
        check(
            'document.querySelector("#sources").open && document.querySelector("#download-data").href.startsWith("blob:")'
        )
        check(
            'document.querySelector("#source-details").innerText.includes("CC BY 4.0")'
        )
        if args.engagement:
            check(
                'document.querySelector("#source-details").innerText.includes("no style control")'
            )
            check(
                'document.querySelector("#source-details").innerText.includes("Apache-2.0")'
            )
            check(
                'await fetch(document.querySelector("#download-data").href).then(r=>r.json()).then(d=>d.attributions.some(a=>a.license_text && a.license_text.includes("TERMS AND CONDITIONS")))'
            )
        browser("press", "Escape")
        check('!document.querySelector("#sources").open')
        browser("select", "#scale", "compressed")
        browser("set", "viewport", "390", "844")
        check("document.documentElement.scrollWidth <= innerWidth")
        check(
            'document.querySelector("#pulse-chart").getBoundingClientRect().width > 300'
        )
        screenshot("mobile.png")
        browser("set", "viewport", "1440", "1080")
        browser("open", args.url.replace("/deepseek/", "/glm/"))
        browser("wait", "#legend button")
        check(
            f'document.querySelectorAll("path.series").length === {args.expected_lines}'
        )
        check('document.querySelector("h1").innerText === "GLM 5.3 Flash"')
        screenshot("glm.png")
        browser("errors")
        (args.output / "result.json").write_text(
            json.dumps(
                {"status": "passed", "url": args.url, "checks": receipt}, indent=2
            )
        )
    except Exception:
        (args.output / "result.json").write_text(
            json.dumps(
                {"status": "failed", "url": args.url, "checks": receipt}, indent=2
            )
        )
        raise


if __name__ == "__main__":
    main()
