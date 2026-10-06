"""Verify the real opt-in page using an owned agent-browser session.

Usage: python -m scripts.benchmark_download_collector.verify_pulse_browser
  --url http://localhost:PORT/benchmarks/CONTRACT/deepseek/?end=2026-10-06
  --output .local/pulse-browser --session benchmark-review
Requires the retained real-data comparison with five lines and a later Arena baseline.
"""

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--session", required=True)
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
            f'if (!({expression})) throw new Error("Pulse assertion failed"); true',
        )

    def screenshot(name):
        result = browser("screenshot")
        match = re.search(r"Screenshot saved to (.+)", result)
        if not match:
            raise RuntimeError("Screenshot evidence missing")
        shutil.copyfile(match.group(1).strip(), args.output / name)

    try:
        browser("set", "viewport", "1440", "1080")
        browser("open", args.url)
        browser("wait", "#legend button")
        check('document.querySelectorAll("path.series").length === 5')
        check('document.querySelectorAll("#legend button").length === 5')
        check(
            'document.querySelector("#readout").innerText.includes("later than launch")'
        )
        check(
            'document.querySelector("#pulse-chart").getBoundingClientRect().height > 300'
        )
        screenshot("desktop.png")
        for key in ["posts", "downloads", "tokens", "score", "rank"]:
            selector = f'#legend button[data-line="{key}"]'
            browser("click", selector)
            check(
                f'document.querySelector({json.dumps(selector)}).getAttribute("aria-pressed") === "false" && document.querySelectorAll("path.series").length === 4'
            )
            browser("click", selector)
            check('document.querySelectorAll("path.series").length === 5')
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
        check('document.querySelectorAll("path.series").length === 5')
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
