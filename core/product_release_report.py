"""Compact review report from persisted dossiers, evidence and shared counts."""

from decimal import Decimal
from html import escape
from urllib.parse import urlsplit

from core import models


def significance(*, product_kind, lineage, change):
    """Declared editorial study policy; attention and publisher fame are separate."""
    kinds = {
        "general_model": 2,
        "specialist_model": 1,
        "agent": 1,
        "harness": 1,
        "other": 0,
    }
    ancestry = {"primary": 30, "derivative": 20, "ablation": 10, "limited_variant": 10}
    changes = {"major": 3, "substantial": 2, "minor": 1, "unknown": 0}
    if lineage == "unknown":
        return None, "Unranked: lineage requires evidence"
    if product_kind not in kinds or lineage not in ancestry or change not in changes:
        raise ValueError("Unknown release significance category")
    return Decimal(
        ancestry[lineage] + kinds[product_kind] + changes[change]
    ), f"{lineage}; {product_kind}; {change} change. Attention is displayed separately."


def release_rows(dossier_ids):
    result = []
    for event in models.EventDossier.objects.filter(
        pk__in=dossier_ids, merged_into__isnull=True
    ).select_related(
        "event_kind_reference",
        "current_review__product_release__release_issuer_company",
    ):
        review = event.current_review
        detail = getattr(review, "product_release", None) if review else None
        latest = event.intake_decisions.order_by("-recorded_at", "-pk").first()
        claims = list(
            models.EventDossierClaim.objects.filter(
                event_dossier_source__event_dossier=event
            ).select_related("claim_kind_reference")
        )
        reports = [
            c.assertion_text
            for c in claims
            if c.claim_kind_reference.code == "release_report"
        ]
        name = (
            detail.observed_name
            if detail
            else reports[0]
            if len(set(reports)) == 1
            else "Unresolved source candidate"
        )
        sources = list(event.sources.select_related("post", "collection_observation"))
        accounts = {s.post.author_id for s in sources if s.post_id and s.post.author_id}
        milestones = []
        for claim in sorted(claims, key=lambda c: (c.recorded_at, str(c.pk))):
            if claim.claim_kind_reference.code not in {
                "announcement",
                "source_stated_release",
                "availability",
                "first_observed_usage",
                "rumor",
                "publisher_verification",
                "source_ownership",
            }:
                continue
            value = (
                claim.effective_at
                or claim.effective_date
                or (
                    f"{claim.effective_year}-{claim.effective_month:02d}"
                    if claim.effective_month
                    else claim.effective_year
                )
                or "unknown"
            )
            milestones.append(
                {
                    "id": str(claim.pk),
                    "kind": claim.claim_kind_reference.code,
                    "value": str(value),
                    "precision": claim.effective_precision,
                    "url": claim.source_locator,
                    "excerpt": claim.source_excerpt,
                    "archive_id": str(claim.source_archive_id)
                    if claim.source_archive_id
                    else None,
                }
            )
        discussion = [
            {
                "id": str(link.snapshot_id),
                "role": link.role,
                "start": link.snapshot.window_start.isoformat(),
                "end": link.snapshot.window_end.isoformat(),
                "posts": link.snapshot.post_count,
                "accounts": link.snapshot.account_count,
                "coverage": link.snapshot.coverage,
                "subject_id": str(link.snapshot.subject_id),
            }
            for link in event.discussion_windows.select_related("snapshot").order_by(
                "snapshot__window_start", "pk"
            )
        ]
        result.append(
            {
                "id": str(event.pk),
                "name": name,
                "state": review.review_state
                if review
                else latest.outcome
                if latest
                else "pending",
                "review_id": str(review.pk) if review else None,
                "publisher": detail.release_issuer_company_id
                if detail and detail.release_issuer_company_id
                else "Unverified / unresolved",
                "product_key": str(detail.product_id)
                if detail and detail.product_id
                else None,
                "score": str(review.significance_score)
                if review and review.significance_score is not None
                else None,
                "reason": review.reason
                if review
                else latest.reason
                if latest
                else "Awaiting assessment",
                "claims": milestones,
                "sources": len(sources),
                "accounts": len(accounts),
                "discussion": discussion,
            }
        )
    return sorted(
        result,
        key=lambda row: (
            -(float(row["score"]) if row["score"] is not None else -1),
            row["name"],
        ),
    )


def _link(url, label):
    try:
        parsed = urlsplit(url or "")
        if (
            parsed.scheme in {"https", "http"}
            and parsed.hostname
            and not parsed.username
            and not parsed.password
        ):
            return f'<a href="{escape(url, quote=True)}" target="_blank" rel="noopener noreferrer">{escape(label)}</a>'
    except ValueError:
        pass
    return escape(label)


def render_report(rows, *, title="Product releases — staging study", notes=""):
    body = []
    for index, row in enumerate(rows, 1):
        milestones = "".join(
            f"<li>{escape(c['kind'])}: {escape(c['value'])} — {_link(c.get('url'), 'source')}<details><summary>Evidence</summary><p>{escape(c['excerpt'])}</p><small>Claim {escape(c.get('id', ''))}</small></details></li>"
            for c in row["claims"]
        )
        windows = "".join(
            f"<li>{escape(w['role'])}: {w['posts']} posts / {w['accounts']} accounts<br><small>{escape(w['start'])} → {escape(w['end'])}; {escape(w['coverage'])}; snapshot {escape(w['id'])}</small></li>"
            for w in row["discussion"]
        )
        score = row["score"] if row["score"] is not None else "—"
        body.append(f'''<tr><td>{index}</td><td>{escape(row["name"])}<small>{escape(row["id"])}</small></td>
<td>{escape(row["state"])}</td><td>{escape(row["publisher"])}</td><td data-value="{escape(str(row["score"] or -1))}">{escape(str(score))}<details><summary>Reason</summary>{escape(row["reason"])}</details></td>
<td>{row["sources"]} records<br>{row["accounts"]} X accounts</td><td><ul>{milestones}</ul></td><td><ul>{windows}</ul></td></tr>''')
    return (
        """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>"""
        + escape(title)
        + """</title><style>
body{font:14px/1.45 system-ui,sans-serif;color:#20242a;background:#fafafa;margin:24px}h1{font-size:23px;margin-bottom:8px}p{max-width:90ch}small{display:block;color:#626873;font-size:11px;overflow-wrap:anywhere}table{border-collapse:collapse;width:100%;background:white}th,td{text-align:left;vertical-align:top;border-bottom:1px solid #ddd;padding:6px 9px}th{position:sticky;top:0;background:#f1f2f3}button{font:inherit;border:0;background:transparent;padding:0;cursor:pointer;text-align:left}a{color:#165a92}td:nth-child(2){min-width:180px}td:nth-child(7){min-width:230px}details{margin:4px 0}summary{color:#52606c;cursor:pointer}ul{padding:0;margin:0;list-style:none}li+li{margin-top:8px}.scroll{overflow:auto}input{padding:7px;margin:10px 0;width:min(420px,90%)}details p{max-width:70ch;white-space:pre-wrap}footer{margin-top:20px;color:#626873}
</style><h1>"""
        + escape(title)
        + """</h1><p>"""
        + escape(notes)
        + """</p>
<p>Pending evidence is not a confirmed release. Milestones are source assertions with their original precision. Discussion totals describe the labelled brand/window; source records are the selected evidence. Popularity does not determine inclusion.</p>
<label>Filter releases <input id="filter" type="search" placeholder="Name, publisher or status"></label>
<div class="scroll"><table id="releases"><thead><tr>"""
        + "".join(
            f'<th><button type="button" data-column="{i}" aria-label="Sort by {name}">{name} ↕</button></th>'
            for i, name in enumerate(
                [
                    "#",
                    "Release",
                    "State",
                    "Publisher",
                    "Significance",
                    "Evidence",
                    "Dated claims",
                    "Brand discussion",
                ]
            )
        )
        + """</tr></thead><tbody>"""
        + "".join(body)
        + """</tbody></table></div>
<footer>Each product/revision is separate. Shared Posts and discussion snapshots keep their original identities. No new model calls were used by the detector or report.</footer>
<script>
const table=document.getElementById('releases'), body=table.tBodies[0];
document.getElementById('filter').addEventListener('input', e => {for(const row of body.rows)row.hidden=!row.textContent.toLowerCase().includes(e.target.value.toLowerCase());});
for(const button of table.querySelectorAll('button[data-column]'))button.addEventListener('click',()=>{
 const col=Number(button.dataset.column), direction=button.dataset.direction==='asc'?-1:1;
 button.dataset.direction=direction===1?'asc':'desc';
 const value=r=>r.cells[col].dataset.value||r.cells[col].textContent.trim();
 const rows=Array.from(body.rows).sort((a,b)=>direction*([0,4].includes(col)?Number(value(a))-Number(value(b)):value(a).localeCompare(value(b))));
 body.append(...rows);
});
</script></html>"""
    )
