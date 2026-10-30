"""Update the G2 living cast audit after one candidate is resolved.

The original nine-person HTML remains an immutable snapshot. This script builds
the living review copy from the roster, nine historical receipts and optional
per-candidate audited records. It makes no provider or database calls.
"""

import argparse
import base64
import io
import json
import subprocess
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / ".local/g2-cast-api-audit-20261023"
ROSTER = ROOT / ".local/g2-cast-roster-21brands-20261023/roster.json"
STATE = PRIVATE / "living-records.json"
OUTPUT = ROOT / "docs/analysis/2026-10-23-180418-g2-cast-living-cost-audit.html"
SERP_ALLOCATED_COST = 25 / 1000
COMPANY_BY_BRAND = {
    "baichuan": "Baichuan", "deepseek": "DeepSeek", "dots": "Xiaohongshu",
    "doubao": "ByteDance", "ernie": "Baidu", "exaone": "LG AI Research",
    "glm": "Zhipu AI", "hunyuan": "Tencent", "inclusionai": "Ant Group",
    "kuaishou": "Kuaishou", "llama": "Meta", "mimo": "Xiaomi",
    "minimax": "MiniMax", "mistral": "Mistral AI", "moonshot_kimi": "Moonshot AI",
    "nemo_megatron": "NVIDIA", "qwen": "Alibaba", "sakana_ai": "Sakana AI",
    "sensechat": "SenseTime", "stepfun": "StepFun", "yi": "01.AI",
}
HISTORICAL = {
    "LUO Fuli": ("g2-chinese-cast-assets-20261022/luo", "20261022-184412", 10, 0.12026, "26 solo + 36 shared"),
    "YANG Zhilin": ("g2-chinese-cast-assets-20261022/yang", "20261022-193340", 10, 0.12026, "36 shared"),
    "TANG Jie": ("g2-chinese-cast-assets-20261022/tang", "20261022-193132", 10, 0.12026, "36 shared"),
    "YAN Junjie": ("g2-chinese-cast-assets-20261022/yan", "20261022-194001", 10, 0.12026, "36 shared"),
    "LIANG Wenfeng": ("g2-cast-next-five-20261022/liang", "20261022-203816", 4, 0.05010, "46 shared"),
    "LIN Junyang": ("g2-cast-next-five-20261022/lin", "20261022-202554", 4, 0.05010, "46 shared"),
    "ZHANG Peng": ("g2-cast-next-five-20261022/zhang", "20261022-202952", 4, 0.05010, "46 shared"),
    "JIANG Daxin": ("g2-cast-next-five-20261022/jiang", "20261022-203946", 4, 0.05010, "46 shared"),
    "WANG Xiaochuan": ("g2-cast-next-five-20261022/wang", "20261022-203645", 4, 0.05010, "46 shared"),
}


def safe_link(url, text):
    if not url or urlsplit(url).scheme not in {"http", "https"}:
        return escape(text)
    return f'<a href="{escape(url, quote=True)}" target="_blank" rel="noopener">{escape(text)}</a>'


def asset_summary(assets):
    photos = [a for a in assets if a.get("role") in {"identity-still", "existing-reference"}]
    clips = [a for a in assets if a.get("role") == "real-source-clip"]
    names = []
    for asset in photos[:3]:
        url = asset.get("source_url") or ""
        title = asset.get("credit") or asset.get("publisher") or urlsplit(url).hostname or "source"
        names.append(safe_link(url, title))
    if len(photos) > 3:
        names.append(f"+{len(photos) - 3} more")
    clip = "—"
    if clips:
        a = clips[0]
        url = a.get("source_url") or ""
        title = a.get("credit") or a.get("publisher") or urlsplit(url).hostname or "source"
        clip = safe_link(url, title)
    return ", ".join(names) or "—", clip


def company_title(person):
    company = " / ".join(COMPANY_BY_BRAND.get(b, b) for b in person.get("brands", [])) or "—"
    role = person.get("role") or ""
    if role.startswith("Database-designated staff"):
        return company, "Title unverified"
    return company, role or "Title unverified"


def preview_data(asset):
    file = Path(asset.get("file") or "")
    if not file.is_file():
        return None
    try:
        if file.suffix.lower() in {".mp4", ".mov", ".webm"}:
            frame = subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", "1", "-i", str(file),
                 "-frames:v", "1", "-f", "image2pipe", "-vcodec", "mjpeg", "pipe:1"],
                capture_output=True, check=True, timeout=10,
            ).stdout
            opened_file = io.BytesIO(frame)
        else:
            opened_file = file
        with Image.open(opened_file) as opened:
            original = ImageOps.exif_transpose(opened).convert("RGB")
            resized = ImageOps.contain(original, (56, 42))
            thumb = Image.new("RGB", (56, 42), "#e5eaed")
            thumb.paste(resized, ((56 - resized.width) // 2, (42 - resized.height) // 2))
            out = io.BytesIO()
            thumb.save(out, "JPEG", quality=72, optimize=True)
        return "data:image/jpeg;base64," + base64.b64encode(out.getvalue()).decode("ascii")
    except (OSError, ValueError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None


def media_preview(asset, *, person_name, label, video=False, poster=None):
    if not asset:
        return '<span class="empty-preview">—</span>'
    data = preview_data(poster or asset)
    if not data:
        return '<span class="empty-preview">—</span>'
    source = asset.get("source_url") or ""
    title = f'{person_name} · {label} · {asset.get("credit") or "source"}'
    image = f'<img class="media-thumb" src="{data}" alt="{escape(title, quote=True)}" loading="lazy">'
    if video:
        image = '<span class="video-poster">' + image + '<span aria-hidden="true" class="play-mark">▶</span></span>'
    if urlsplit(source).scheme not in {"http", "https"}:
        return image
    return f'<a class="media-link" href="{escape(source, quote=True)}" target="_blank" rel="noopener" title="{escape(title, quote=True)}">{image}</a>'


def saved_local_pack_assets(pack_file):
    """Read older local cast pack formats for display without rewriting evidence."""
    data = json.loads(Path(pack_file).read_text())
    if "entries" in data:
        result = []
        for item in data["entries"]:
            role = "real-source-clip" if item.get("role") == "identity-and-natural-motion" else "existing-reference"
            result.append({"role": role, "file": item.get("file"),
                           "source_url": item.get("source_url"),
                           "credit": item.get("creator") or "Source publisher"})
        return result
    if "photos" in data and "video" in data:
        result = [{"role": "existing-reference", "file": item.get("file"),
                   "source_url": item.get("source_page") or item.get("url"),
                   "credit": urlsplit(item.get("source_page") or item.get("url") or "").hostname or "Source publisher"}
                  for item in data["photos"]]
        video = data["video"]
        result.append({"role": "real-source-clip", "file": video.get("file"),
                       "source_url": video.get("source"), "credit": video.get("publisher") or "Source publisher"})
        return result
    return data.get("assets", [])


def historical_record(name):
    pack_path, run_id, apify_runs, apify_cost, llm_calls = HISTORICAL[name]
    file = ROOT / ".local" / pack_path / "r2-save-receipt.json"
    pack = json.loads(file.read_text())
    return {
        "status": "complete",
        "finished_at": pack.get("saved_at"),
        "source": "2026-10-22 CLI research + saved R2 pack",
        "apify_runs": apify_runs,
        "apify_cost_usd": apify_cost,
        "serpapi_runs": 1,
        "llm_calls": llm_calls,
        "llm_model": "GPT-6.1 Sol/xhigh · Codex",
        "llm_cost_usd": None,
        "assets": pack["assets"],
        "evidence": str(file.relative_to(ROOT)),
        "note": "Historical shared CLI responses; per-person model cost unavailable.",
    }


def validate_record(record, roster):
    key = record.get("key")
    if key not in {p["key"] for p in roster}:
        raise ValueError("Candidate key must match the current cast roster")
    if record.get("status") not in {"complete", "incomplete", "in_progress"}:
        raise ValueError("Candidate status must be complete, incomplete or in_progress")
    metrics = record.get("metrics")
    if not isinstance(metrics, dict):
        raise ValueError("metrics object required")
    for k in ("apify_runs", "serpapi_runs", "llm_calls"):
        if metrics.get(k) is None and k == "apify_runs":
            continue  # Actor run count is unknown until reconciled with Apify receipts.
        if type(metrics.get(k)) is not int or metrics[k] < 0:
            raise ValueError(f"{k} must be a nonnegative integer")
    for k in ("apify_cost_usd", "llm_cost_usd"):
        if metrics.get(k) is not None and (type(metrics[k]) not in {int, float} or metrics[k] < 0):
            raise ValueError(f"{k} must be a nonnegative number or null")
    if metrics["llm_calls"] and (not metrics.get("llm_model") or metrics.get("llm_cost_usd") is None):
        raise ValueError("Direct LLM calls require named model and provider-receipt cost")
    if not isinstance(record.get("assets"), list):
        raise ValueError("assets array required")
    if record["status"] == "complete":
        roles = [a.get("role") for a in record["assets"]]
        if roles.count("identity-still") < 2 or roles.count("real-source-clip") < 1:
            raise ValueError("Complete requires two stills and one real clip")
    passes = record.get("passes")
    if not isinstance(passes, list) or not 1 <= len(passes) <= 3:
        raise ValueError("Record one to three bounded passes")
    for i, phase in enumerate(passes):
        if phase.get("number") != i + 1 or not phase.get("prompt_sha256") or not phase.get("outcome"):
            raise ValueError("Each pass needs sequential number, prompt hash and outcome")
        if i and (not phase.get("change_reason") or phase["prompt_sha256"] == passes[i - 1]["prompt_sha256"]):
            raise ValueError("Recovery pass must explain and change its prompt")
    if record["status"] == "incomplete" and len(passes) != 3 and not record.get("early_stop_reason"):
        raise ValueError("Incomplete before pass three needs an explicit stop reason")
    for asset in record["assets"]:
        if not asset.get("source_url") or not asset.get("credit"):
            raise ValueError("Every selected asset needs source URL and credit")
    if not record.get("evidence"):
        raise ValueError("Receipt or run evidence path required")


def money(value, *, precision=3):
    return "unreported" if value is None else f"${value:.{precision}f}"


def finish_sort_key(record):
    value = record.get("finished_at")
    if not value:
        return (1, datetime.max.replace(tzinfo=timezone.utc))
    return (0, datetime.fromisoformat(value).astimezone(timezone.utc))


def finish_cell(record):
    value = record.get("finished_at")
    if not value:
        return "—"
    when = datetime.fromisoformat(value).astimezone(ZoneInfo("Asia/Tokyo"))
    return f'<time datetime="{escape(value, quote=True)}">≈ {when:%Y-%m-%d %H:%M} JST</time>'


def row(person, record, *, outside=False):
    status = record["status"]
    metrics = record.get("metrics", record)
    assets = record.get("assets", [])
    photos, clip = asset_summary(assets)
    stills = [a for a in assets if a.get("role") in {"identity-still", "existing-reference"}]
    clip_asset = next((a for a in assets if a.get("role") == "real-source-clip"), None)
    frame = next((a for a in assets if a.get("role") == "source-frame" and clip_asset and
                  a.get("source_url") == clip_asset.get("source_url")), None)
    company, title = company_title(person)
    previews = [media_preview(stills[i] if i < len(stills) else None, person_name=person["name"], label=f"image {i+1}")
                for i in range(2)]
    previews.append(media_preview(clip_asset, person_name=person["name"], label="video source", video=True, poster=frame))
    apify = money(metrics.get("apify_cost_usd"), precision=5)
    serp = metrics.get("serpapi_runs")
    llm = metrics.get("llm_calls")
    model = metrics.get("llm_model") or "model unknown"
    note = record.get("note") or ""
    if outside:
        note = "Outside 21-brand roster. " + note
    attempts = record.get("passes", [])
    pass_note = "" if not attempts else f'{len(attempts)}/3 passes'
    return (f'<tr class="{escape(status)}"><td>{finish_cell(record)}</td>'
            f'<th>{escape(person["name"])}<small>{escape(person.get("name_original") or "")} · {escape(str(person.get("rank") or "archive"))}</small></th>'
            f'<td class="company-cell" title="{escape(company, quote=True)}">{escape(company)}</td>'
            f'<td class="title-cell" title="{escape(title, quote=True)}"><span>{escape(title)}</span></td>'
            f'<td><b>{escape(status)}</b><small>{escape(pass_note)}</small></td>'
            f'<td>{metrics.get("apify_runs") if metrics.get("apify_runs") is not None else "unreported"}</td><td>{apify}</td>'
            f'<td>{serp if serp is not None else "—"}</td><td>{money(serp * SERP_ALLOCATED_COST) if serp is not None else "unreported"}</td>'
            f'<td>{escape(str(llm if llm is not None else "unreported"))}<small>{escape(model)}</small></td>'
            f'<td>{money(metrics.get("llm_cost_usd"))}</td>'
            f'<td class="preview-cell">{previews[0]}</td><td class="preview-cell">{previews[1]}</td><td class="preview-cell">{previews[2]}</td>'
            f'<td>{photos}</td><td>{clip}</td><td>{escape(note)}</td></tr>')


def render(roster, updates):
    active, pending = [], []
    totals = {"complete": 0, "incomplete": 0, "in_progress": 0, "pending": 0, "apify_runs": 0, "apify_cost_usd": 0.0, "serpapi_runs": 0, "llm_cost_usd": 0.0}
    for person in roster:
        if person["key"] in updates:
            u = updates[person["key"]]
            record = {"status": u["status"], "metrics": u["metrics"], "assets": u["assets"], "passes": u["passes"],
                      "finished_at": u.get("finished_at"),
                      "evidence": u["evidence"], "note": u.get("note") or u.get("early_stop_reason") or ""}
        elif person["name"] in HISTORICAL:
            record = historical_record(person["name"])
        elif person.get("acquisition_status", "").startswith("saved"):
            local_pack = (person.get("pack") or {}).get("local_pack")
            when = datetime.fromtimestamp(Path(local_pack).stat().st_mtime, timezone.utc).isoformat() if local_pack else None
            record = {"status": "complete", "finished_at": when,
                      "note": "Saved first-wave pack; approximate time is its local file timestamp. API/cost audit pending.",
                      "assets": saved_local_pack_assets(local_pack) if local_pack else []}
        else:
            record = {"status": "pending", "assets": []}
        totals[record["status"]] += 1
        m = record.get("metrics", record)
        for k in ("apify_runs", "serpapi_runs"):
            totals[k] += m.get(k) or 0
        for k in ("apify_cost_usd", "llm_cost_usd"):
            totals[k] += m.get(k) or 0
        (pending if record["status"] == "pending" else active).append((finish_sort_key(record), person["rank"], row(person, record)))
    assert sum(totals[s] for s in ("complete", "incomplete", "in_progress", "pending")) == len(roster)
    outside = historical_record("WANG Xiaochuan")
    outside_row = row({"name": "WANG Xiaochuan", "name_original": "王小川",
                       "brands": ["baichuan"], "role": "Baichuan founder"}, outside, outside=True)
    active.sort(key=lambda item: (item[0], item[1]))
    pending.sort(key=lambda item: item[1])
    head = "<tr><th>Approx. finished (JST)</th><th>Person</th><th>Company</th><th>Title</th><th>Status / passes</th><th>Apify runs</th><th>Apify cost</th><th>SerpApi runs</th><th>SerpApi allocation</th><th>LLM calls · model</th><th>LLM cost</th><th>Image 1</th><th>Image 2</th><th>Video</th><th>Saved photos</th><th>Saved clip</th><th>Note</th></tr>"
    running_total = (
        f'<tr class="running-total"><th>—</th><th>Running total<small>{len(roster)}-person roster</small></th>'
        f'<td>—</td><td>—</td><td>—</td><td>{totals["apify_runs"]}</td><td>${totals["apify_cost_usd"]:.5f}</td>'
        f'<td>{totals["serpapi_runs"]}</td><td>${totals["serpapi_runs"] * SERP_ALLOCATED_COST:.3f}</td>'
        f'<td>—</td><td>${totals["llm_cost_usd"]:.3f}</td><td>—</td><td>—</td><td>—</td><td>—</td><td>—</td>'
        '<td>Unreported dollar values counted as $0 here.</td></tr>'
    )
    html = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>G2 {len(roster)}-person living cast audit</title>
<style>:root{{font:12px/1.3 system-ui,-apple-system,sans-serif;color:#172334;background:#f5f7f8}}body{{margin:0;padding:15px}}main{{max-width:1900px;margin:auto}}h1{{font-size:21px;margin:0 0 5px}}p{{margin:5px 0 10px}}.stats{{display:flex;gap:6px;flex-wrap:wrap;margin:10px 0}}.stats span{{background:white;border:1px solid #dce3e8;border-radius:6px;padding:5px 8px;font-weight:600}}.wrap{{overflow:auto;border:1px solid #dce3e8;border-radius:8px;background:white}}table{{width:100%;min-width:2050px;border-collapse:collapse}}.company-cell{{min-width:108px;max-width:108px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}.title-cell{{min-width:165px;max-width:165px}}.title-cell span{{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}.preview-cell{{width:66px;min-width:66px;padding:4px 5px;vertical-align:middle}}.media-link,.video-poster{{display:inline-block;position:relative;width:56px;height:42px}}.media-thumb{{display:block;width:56px;height:42px;object-fit:contain;background:#e5eaed;border-radius:3px}}.play-mark{{position:absolute;left:21px;top:11px;color:#fff;font-size:16px;text-shadow:0 1px 4px #000,0 0 3px #000;pointer-events:none}}.empty-preview{{color:#8b98a3}}th,td{{padding:6px 7px;border-bottom:1px solid #e6ebef;text-align:left;vertical-align:top}}thead th{{background:#eaf0f4;font-size:10px;text-transform:uppercase;position:sticky;top:0}}tbody th{{white-space:nowrap}}.running-total th,.running-total td{{background:#e4f1f5;font-weight:700;border-bottom:2px solid #9dc4d3}}small{{display:block;color:#677484}}a{{color:#075a8b;text-decoration:none}}a:hover{{text-decoration:underline}}details{{margin-top:10px}}summary{{cursor:pointer;font-weight:700}}.notes{{display:grid;grid-template-columns:repeat(2,1fr);gap:7px;margin-top:10px}}.notes p{{background:#fff;border:1px solid #dce3e8;padding:9px;border-radius:6px;font-size:12px}}@media(max-width:700px){{.notes{{grid-template-columns:1fr}}body{{padding:9px}}}}</style>
<main><h1>G2 cast · living cost and source audit</h1><p>{len(roster)}-person tracked-brand roster. Stefania Druga, Mert Ünsal, Arthur Mensch and Lucy Park were removed from this Chinese cast by owner direction; their database accounts are unchanged. The <a href="2026-10-23-175247-g2-nine-cast-source-api-audit.html">original nine-person report</a> stays frozen; this page is regenerated after each candidate. Mini previews open their credited source pages; the video column shows the saved clip’s source frame.</p>
<div class="stats"><span>{totals['complete']} complete</span><span>{totals['in_progress']} in progress</span><span>{totals['incomplete']} incomplete</span><span>{totals['pending']} pending</span><span>In-scope Apify: {totals['apify_runs']} runs · ${totals['apify_cost_usd']:.5f}</span><span>In-scope SerpApi: {totals['serpapi_runs']} searches · ${totals['serpapi_runs']*SERP_ALLOCATED_COST:.3f} allocated</span><span>Recorded direct LLM spend: ${totals['llm_cost_usd']:.3f} + historical CLI unreported</span></div>
<div class="wrap"><table><thead>{head}</thead><tbody>{running_total}{''.join(item[2] for item in active)}</tbody></table></div>
<details><summary>Show {len(pending)} pending people</summary><div class="wrap"><table><thead>{head}</thead><tbody>{''.join(item[2] for item in pending)}</tbody></table></div></details>
<details><summary>Show archived outside-roster pack</summary><div class="wrap"><table><thead>{head}</thead><tbody>{outside_row}</tbody></table></div></details>
<div class="notes"><p><b>Recovery rule, to wire before nonstop launch.</b> One normal pass plus two distinct recovery passes per person. Each recovery must change the model prompt and cite the failure: pass 2 targets the missing/weak asset; pass 3 changes source or selection strategy. Save all prompt hashes, changes, source receipts and costs. After three passes, mark incomplete and move on. An access or integrity stop can end a person early with a recorded reason. Current collector does not yet automate these new passes.</p><p><b>Request retry ceilings, to wire before launch.</b> Direct LLM: at most two retries for explicit transient 429/502/503/504, with bounded backoff and receipts. One separate revised-prompt repair for a complete but invalid model answer. SerpApi and ordinary downloads: at most one retry for explicit 502/503/504. XHS/Apify risk, CAPTCHA, 401/403/429: no automatic retry. A timeout with unknown billing needs reconciliation before any resend.</p><p><b>Run-wide stops.</b> Hard spend/search quota, missing or rejected credentials, provider-wide rate/access block, uncertain duplicate billing, corrupt source/hash, unavailable R2/disk, persistent code/schema error, or a host outage. Candidate-specific missing assets do not stop the queue. Disable XHS after its first risk warning; continue other source routes when possible.</p><p><b>Accounting.</b> Historical eight in-scope packs used shared GPT-6.1 Sol/xhigh Codex turns; their model dollar cost is unavailable and is not zero. Future direct API packs must carry model, physical call count, actual usage and estimated USD from provider receipts. SerpApi allocation is $25/1,000=$0.025/search; marginal charge within the prepaid plan is $0. The archived Baichuan pack is outside the tracked-brand roster totals. The prior direct-model experiment ledger is near its USD50 ceiling and cannot be silently reset.</p></div></main></html>'''
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temp = OUTPUT.with_suffix(".tmp")
    temp.write_text(html)
    temp.replace(OUTPUT)
    return totals


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record-file", type=Path, help="One audited candidate record; merge then regenerate")
    args = parser.parse_args()
    roster = json.loads(ROSTER.read_text())["people"]
    assert len(roster) == 65 and len({p["key"] for p in roster}) == 65
    updates = json.loads(STATE.read_text()) if STATE.exists() else {}
    if args.record_file:
        record = json.loads(args.record_file.read_text())
        validate_record(record, roster)
        updates[record["key"]] = record
        STATE.parent.mkdir(parents=True, exist_ok=True)
        temp = STATE.with_suffix(".tmp")
        temp.write_text(json.dumps(updates, indent=2, ensure_ascii=False) + "\n")
        temp.replace(STATE)
    totals = render(roster, updates)
    print(json.dumps({"output": str(OUTPUT), "totals": totals}, ensure_ascii=False))


if __name__ == "__main__":
    main()
