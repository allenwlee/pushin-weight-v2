"""Offline HTML and CSV views of the exact prepared job-history proposal."""

import base64
import csv
import io
import json
from collections import Counter
from datetime import datetime
from html import escape
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo


def text(value):
    return (
        escape(str(value))
        if value not in (None, "")
        else '<span class="muted">Unknown</span>'
    )


def jst(value):
    if not value:
        return "Unknown"
    return (
        datetime.fromisoformat(value)
        .astimezone(ZoneInfo("Asia/Tokyo"))
        .strftime("%Y-%m-%d %H:%M JST")
    )


def source_link(url, label):
    """Saved evidence URLs are untrusted data, including their schemes."""
    url = str(url or "")
    try:
        parsed = urlsplit(url)
        allowed = parsed.scheme.lower() in {"http", "https"} and bool(parsed.netloc)
    except ValueError:
        allowed = False
    if not allowed:
        return escape(label + (" · " + url if url else ""))
    return f'<a href="{escape(url, quote=True)}" target="_blank" rel="noreferrer">{escape(label)}</a>'


def _evidence(entry):
    kind = "Saved account bio" if entry["source_kind"] == "saved_bio" else "Post"
    identifier = (
        " · tweet " + str(entry["native_post_id"])
        if entry.get("native_post_id")
        else ""
    )
    published = (
        " · posted " + jst(entry["published_at"]) if entry.get("published_at") else ""
    )
    return (
        f'<div class="evidence">{source_link(entry["source_url"], kind + identifier)}'
        f" · collected {text(jst(entry['observed_at']))}{escape(published)}"
        f"<pre>{escape(entry['evidence_text'])}</pre>"
        "<small>Stored source link + text; staging Post/profile foreign key not bound.</small></div>"
    )


def _picture(profile):
    image = profile.get("image", {})
    if image.get("status") == "saved" and image.get("file"):
        path = Path(image["file"])
        if path.is_file():
            data = base64.b64encode(path.read_bytes()).decode()
            mime = image.get("mime", "image/jpeg")
            if mime in {"image/jpeg", "image/png", "image/webp", "image/gif"}:
                return f'<img alt="Saved X profile picture" src="data:{mime};base64,{data}" width="56" height="56">'
    return '<div class="no-image">No saved<br>picture</div>'


def _existing_history(person):
    rows = []
    for role in person.get("existing_affiliations", []):
        evidence = "".join(
            '<div class="evidence">'
            + source_link(e.get("source_url"), "Stored source")
            + " · observed "
            + text(jst(e.get("observed_at")))
            + "<pre>"
            + escape(e.get("evidence_text", ""))
            + "</pre></div>"
            for e in role["evidence"]
        )
        rows.append(
            "<tr><td>Existing affiliation "
            + text(role["id"])
            + "<br>"
            + text(role.get("observed_organization_name"))
            + " / Brand "
            + text(role.get("brand_id"))
            + "</td><td>"
            + text(role.get("status"))
            + "<br>"
            + text(role.get("start_date"))
            + " → "
            + text(role.get("end_date"))
            + "</td><td>"
            + text(role.get("title_raw"))
            + "<br>Function: "
            + text(role.get("job_function"))
            + "<br>Team: "
            + text(role.get("team"))
            + "<br>Description: "
            + text(role.get("description"))
            + "</td><td>"
            + evidence
            + "</td></tr>"
        )
    if not rows:
        return ""
    return (
        '<div class="existing-history"><h3>Already stored in staging — retained for comparison</h3><div class="table-scroll"><table><thead><tr><th>Existing record</th><th>Status / stored dates</th><th>Role fields</th><th>Existing evidence</th></tr></thead><tbody>'
        + "".join(rows)
        + "</tbody></table></div></div>"
    )


def render_html(
    prepared,
    *,
    profiles=None,
    title="Staff employment — detailed preview",
    csv_name=None,
    json_name=None,
    coverage_comparison=None,
    coverage_name=None,
):
    profiles = profiles or {}
    sections, employers = [], set()
    for person in prepared["people"]:
        profile = profiles.get(person["handle"].casefold(), {})
        name = next(iter(person["names"]), "Name not saved")
        identity = person["identity"]
        body, companies = [], set()
        for number, role in enumerate(person["affiliations"], 1):
            fields, chain = role["fields"], role["chain"]
            organization = fields["observed_organization_name"]
            employers.add(organization)
            companies.add(organization)
            label = {
                "current": "Current, as observed",
                "former": "Prior",
                "unknown": "Status unknown",
            }[fields["status"]]
            assumed_current = fields["status"] == "current" and "certainty: low" in (
                fields.get("review_note") or ""
            )
            if assumed_current:
                label = "Assumed current · low certainty"
            company_actions = "<br>".join(
                f"{text(a['table'])}: <b>{text(a['action'])}</b> {text(a['key'])}"
                + (f"<br>{text(a['note'])}" if a.get("note") else "")
                for a in chain["actions"]
            )
            evidence = "".join(_evidence(e) for e in role["evidence"])
            notes = "<br>".join(
                text(n)
                for n in role["notes"]
                + chain["issues"]
                + ([fields["review_note"]] if fields.get("review_note") else [])
            )
            field_sources = "".join(
                "<li>"
                + text(field)
                + ": "
                + text(attribution["value"])
                + " · source keys "
                + text(", ".join(attribution["source_keys"]))
                + " · "
                + text(attribution["basis"])
                + "</li>"
                for field, entries in role.get("field_sources", {}).items()
                for attribution in entries
            )
            if field_sources:
                notes += (
                    "<details><summary>Field source keys</summary><ul>"
                    + field_sources
                    + "</ul></details>"
                )
            end_display = (
                (
                    "Present (low certainty)"
                    if assumed_current
                    else "Present (as observed)"
                )
                if fields["status"] == "current" and not fields["end_date"]
                else role["end_display"]
            )
            body.append(f"""<tr class="employment">
<td><b>{text(organization)}</b><br>{text(label)} · {text(fields["affiliation_type"])}
<p class="id">Affiliation: {text(role["existing_id"] or role["local_id"])}<br>Action: {text(role["action"])}</p>{notes}</td>
<td><b>Brand</b> {text(chain["brand_id"])}<br><b>Company</b> {text(", ".join(chain["company_ids"]))}<p class="id">{company_actions}</p></td>
<td><b>{text(role["start_display"])} → {text(end_display)}</b><p>start_date: {text(fields["start_date"])}<br>precision: {text(fields["start_date_precision"])}<br>end_date: {text(fields["end_date"])}<br>precision: {text(fields["end_date_precision"])}</p><small>Observation time is not an employment date.</small></td>
<td><b>Title</b><br>{text(fields["title_raw"])}<p><b>Function</b><br>{text(fields["job_function"])}</p><small>Technical involvement: inferred later.</small></td>
<td><b>Department</b> {text(fields["department"])}<br><b>Team / product</b> {text(fields["team"])}<p><b>Work description</b><br>{text(fields["description"])}</p><b>Employment type</b> {text(fields["employment_type"])}</td>
<td>{text(role["location_text"])}<p class="muted">Geolocation FK: {text(fields["geolocation_id"])}</p></td>
<td class="sources">{evidence}</td></tr>""")
        if not body:
            body.append(
                '<tr><td colspan="7">No structured employment entry in this scope. '
                + text(person["note"])
                + "</td></tr>"
            )
        issues = "<br>".join(text(i) for i in person["issues"])
        unused_html = "".join(
            "<div><b>Other saved evidence ("
            + text(e["source_key"])
            + ")</b>"
            + _evidence(e)
            + "</div>"
            for e in person.get("unused_evidence", [])
        )
        search = json.dumps(
            [
                person["handle"],
                name,
                person["native_id"],
                person["affiliations"],
                person.get("biography_summaries", []),
                person.get("reviewed_names", []),
                person["note"],
            ],
            ensure_ascii=False,
        ).casefold()
        companies_attr = json.dumps(sorted(companies), ensure_ascii=False)
        language_html = ""
        language = person.get("primary_language_assignment")
        if language:
            previous = (
                text(language["previous_value"] or "Unset")
                if language["previous_value_known"]
                else "Not captured in saved inventory"
            )
            language_html = (
                '<p class="primary-language"><b>people.primary_language: '
                + previous
                + " → "
                + text(language["value"])
                + "</b> · "
                + text(language["action"])
                + " · Owner override · "
                + text(language["decision_id"])
                + "</p>"
            )
        assessment = person.get("language_assessment")
        if assessment:
            language_html += (
                '<p class="primary-language"><b>Language signal: '
                + text(assessment["outcome"])
                + "</b> · heuristic proposal; not verified proficiency</p>"
            )
            evidence = "".join(
                "<li>"
                + text(e["rule"])
                + ": "
                + text(e["quote"])
                + " · "
                + source_link(e["source_url"], e["source_kind"])
                + "</li>"
                for e in assessment["evidence"]
            )
            if evidence:
                language_html += (
                    "<details><summary>Language evidence</summary><ul>"
                    + evidence
                    + "</ul></details>"
                )
        summaries = "".join(
            "<p><b>Biography summary</b> · "
            + text(summary["action"])
            + ": "
            + text(summary["text"])
            + " · "
            + source_link(summary["source_reference"], "Source")
            + " · observed "
            + text(jst(summary["observed_at"]))
            + "</p>"
            for summary in person.get("biography_summaries", [])
        )
        coverage = person.get("source_coverage")
        coverage_html = (
            (
                "<p>Saved sources: "
                + text(coverage["saved_bios"])
                + " bios · "
                + text(coverage["own_posts"])
                + " own posts · "
                + text(coverage["third_party_posts"])
                + " third-party posts. "
                + "Additional history search in this run: "
                + text(coverage["history_search"])
                + " · source completeness: "
                + text(coverage["source_completeness"])
                + ".</p>"
            )
            if coverage
            else ""
        )
        names_html = "".join(
            "<div><b>Reviewed name: "
            + text(name["full_name"])
            + "</b> · "
            + text(name["action"])
            + "".join(
                "<p>"
                + text(evidence["source_text"])
                + " · "
                + source_link(evidence["source_reference"], "Source")
                + " · observed "
                + text(jst(evidence["observed_at"]))
                + "</p>"
                for evidence in name["evidence"]
            )
            + "</div>"
            for name in person.get("reviewed_names", [])
        )
        held_html = "".join(
            "<div><b>Held for organization review: "
            + text(role["organization"])
            + "</b>"
            + "".join(_evidence(e) for e in role["evidence"])
            + "</div>"
            for role in person.get("held_roles", [])
        )
        sections.append(f'''<section class="person" data-search="{escape(search, quote=True)}" data-outcome="{escape(person["outcome"], quote=True)}" data-employers="{escape(companies_attr, quote=True)}">
<div class="person-heading">{_picture(profile)}<div><h2>{text(name)} <a href="https://x.com/{escape(person["handle"], quote=True)}" target="_blank" rel="noreferrer">@{text(person["handle"])}</a></h2>
<p>{text(person["outcome"])} · X ID: {text(person["native_id"])} · Person: <b>{text(identity["person_action"])}</b> {text(identity["person_id"])} · Account: <b>{text(identity["account_action"])}</b> {text(identity["account_key"])}</p>
{language_html}{coverage_html}{names_html}{summaries}{held_html}<p>{text(person["note"])}</p><p class="issue">{issues}</p></div></div>
<div class="table-scroll"><table><thead><tr><th>Employer / proposed record</th><th>Existing company chain</th><th>Affiliation dates</th><th>Title &amp; job function</th><th>Division, team &amp; description</th><th>Work location</th><th>Full saved evidence &amp; sources</th></tr></thead><tbody>{"".join(body)}</tbody></table></div>{unused_html}{_existing_history(person)}</section>''')
    counts = " · ".join(
        f"{value:,} {key}" for key, value in sorted(prepared["counts"].items())
    )
    action_counts = Counter(
        (r["table"], r["action"]) for r in prepared["record_actions"]
    )
    actions = "".join(
        f"<tr><td>{text(table)}</td><td>{text(action)}</td><td>{count:,}</td></tr>"
        for (table, action), count in sorted(action_counts.items())
    )
    options = "".join(
        f'<option value="{escape(e, quote=True)}">{escape(e)}</option>'
        for e in sorted(employers, key=str.casefold)
    )
    downloads = " · ".join(
        f'<a href="{escape(n, quote=True)}">{label}</a>'
        for n, label in [
            (csv_name, "CSV"),
            (json_name, "Prepared JSON"),
            (coverage_name, "Coverage JSON"),
        ]
        if n
    )
    language_summary = ""
    coverage_summary = ""
    if coverage_comparison is not None:
        before = coverage_comparison["before"]
        after = coverage_comparison["after"]
        coverage_summary = (
            f"<p><b>Coverage comparison:</b> {before['people']:,} → {after['people']:,} people; "
            f"{before['role_entries']:,} → {after['role_entries']:,} structured roles; "
            f"{before['fields']['start_date']['populated_entries']:,} → {after['fields']['start_date']['populated_entries']:,} with start dates; "
            f"{before['fields']['end_date']['populated_entries']:,} → {after['fields']['end_date']['populated_entries']:,} with end dates. "
            "Counts include held records.</p>"
            + (
                "<p>Inputs, target inventory or structured scope differ; these counts do not establish a change in extraction recall.</p>"
                if not coverage_comparison["same_input_digest"]
                or not coverage_comparison["same_target_inventory"]
                or before["scope"] != after["scope"]
                else ""
            )
        )
    if prepared.get("primary_language_assignment"):
        assignment = prepared["primary_language_assignment"]
        language_summary = (
            '<p class="language-summary"><b>'
            + text(prepared["primary_language_assignment_count"])
            + " owner-selected people.primary_language assignments: "
            + text(assignment["value"])
            + "</b>. Remaining candidates unchanged. "
            + text(assignment["authorized_by"])
            + " · "
            + text(jst(assignment["authorized_at"]))
            + " · "
            + text(assignment["decision_id"])
            + "</p><p>Owner instruction: "
            + text(assignment["instruction"])
            + "</p>"
        )
    role_counts = prepared.get("role_counts")
    if role_counts:
        scope_summary = (
            f"<p>{role_counts['input']:,} source role entries · "
            f"{role_counts['coalesced']:,} reconciled role observations · "
            f"{role_counts['outside_scope']:,} outside the structured scope · "
            f"{role_counts['held']:,} held for review (including held structured rows).</p>"
        )
        if prepared.get("profile_history_inventory") in {"not_captured", "unassessed"}:
            scope_summary += "<p><b>Profile-history comparison is incomplete.</b> The saved target inventory has not been checked for conflicting or compressed profile observations.</p>"
        elif prepared.get("profile_history_inventory") == "exact_matches_only":
            scope_summary += "<p><b>Profile-history comparison is partial.</b> Exact account, source, clock and profile-hash matches can be reused; observed account bios with an empty target history can be captured after a locked recheck. Other observations remain on hold.</p>"
        scope_summary += (
            f"<p>Held record actions: {action_counts[('people_brand_affiliations', 'hold')]:,} structured affiliations · "
            f"{action_counts[('people_texts', 'hold')]:,} person-text summaries · "
            f"{action_counts[('account_profile_snapshots', 'hold')]:,} profile snapshots. "
            "These are record counts and can overlap the people and role counts above.</p>"
        )
        scope_summary += "<p>Compact summaries cover saved reviewed role facts. Other biographical details remain in the original source text and have not all been extracted into summaries.</p>"
        affiliation_label = "structured affiliations"
    else:
        scope_summary = ""
        affiliation_label = "employment entries"
    return f"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#f5f3ed;color:#202323;font:14px/1.5 system-ui,-apple-system,sans-serif}}a{{color:#165a93}}header,main{{padding:22px 28px}}h1{{font-size:27px;margin:0 0 8px}}h2{{font-size:19px;margin:0}}p{{margin:7px 0}}.muted,small{{color:#697174}}.issue{{color:#933c19}}.controls{{position:sticky;top:0;background:#f5f3ed;z-index:2;display:flex;gap:12px;align-items:center;flex-wrap:wrap;padding:14px 28px;border-block:1px solid #d6d5ce}}input,select{{padding:8px;border:1px solid #a7b0b0;border-radius:4px;max-width:100%;font:inherit}}input{{width:360px}}.person{{margin-bottom:26px;border:1px solid #ced2cd;background:white;border-radius:7px;overflow:hidden}}.person-heading{{display:flex;gap:15px;padding:17px;background:#eaf0ed}}.person-heading>div{{min-width:0;overflow-wrap:anywhere}}.person-heading img{{border-radius:7px;flex-shrink:0}}.no-image{{width:56px;min-width:56px;font-size:10px;color:#64716b;background:#dce4de;text-align:center;padding-top:12px}}.table-scroll{{overflow-x:auto}}table{{border-collapse:collapse;width:100%;min-width:1550px;table-layout:fixed}}th,td{{border-top:1px solid #dce1dd;padding:11px;vertical-align:top;text-align:left;overflow-wrap:anywhere}}th{{font-size:12px;text-transform:uppercase;background:#f4f7f5}}th:nth-child(1){{width:15%}}th:nth-child(2){{width:14%}}th:nth-child(3){{width:11%}}th:nth-child(4){{width:11%}}th:nth-child(5){{width:14%}}th:nth-child(6){{width:8%}}th:nth-child(7){{width:27%}}.id{{overflow-wrap:anywhere;font:11px/1.6 ui-monospace,monospace;color:#516159}}.evidence{{padding:8px 0;border-bottom:1px solid #e1e6df}}pre{{font:13px/1.55 system-ui;white-space:pre-wrap;overflow-wrap:anywhere;margin:7px 0}}.counts{{font-size:17px;font-weight:600}}.summary table{{min-width:0;max-width:820px;table-layout:auto}}.summary{{padding:16px 28px}}.summary h2{{margin:10px 0}}[hidden]{{display:none!important}}@media(max-width:650px){{header,main{{padding:14px}}.controls{{padding:10px 14px}}h1{{font-size:22px}}.person-heading{{padding:12px}}h2 a{{display:block}}}}@media print{{.controls{{display:none}}.table-scroll{{overflow:visible}}table{{min-width:0;font-size:9px}}header,main{{padding:0}}.person{{break-inside:auto}}}}
</style><header><h1>{escape(title)}</h1><p class="counts">{len(prepared["people"]):,} people · {prepared["affiliation_count"]:,} {affiliation_label}</p>{scope_summary}{coverage_summary}<p>{escape(counts)}</p>
<p><b>Local preview — no database import or X-list change.</b> Zero new tables or columns. “Supported” describes saved employment evidence, not final import approval. Current status follows saved evidence and review notes; low-certainty continuation assumptions are labeled.</p>
{language_summary}
<p>Target inventory: {text(prepared["target"]["database"])}, captured {text(jst(prepared["target"]["captured_at"]))}. All proposed records remain local; unresolved identities and company links are shown.</p>
<p>Unknown dates and locations are left unknown. Row order groups current, former and uncertain roles; it does not invent chronology among undated jobs. The original 65-person roster is outside this intake.</p><p>{downloads}</p><p class="id">Prepared payload SHA-256: {text(prepared["payload_digest"])}</p></header>
<div class="controls"><input id="search" type="search" aria-label="Search people and evidence" placeholder="Search handle, name, job, source text…"><select id="employer" aria-label="Employer"><option value="">All employers</option>{options}</select><select id="outcome" aria-label="Outcome"><option value="">All outcomes</option><option>supported</option><option>unresolved</option><option>excluded</option></select><span id="visible-count">{len(prepared["people"]):,} people shown</span></div>
<main>{"".join(sections)}</main><div class="summary"><h2>Proposed record actions</h2><p>Shared company records count once. Actions on unresolved people are proposals, not an apply queue. Evidence comparison and target binding must be completed in the later staging-import phase.</p><table><thead><tr><th>Existing table</th><th>Proposed action</th><th>Records</th></tr></thead><tbody>{actions}</tbody></table></div>
<script>const people=[...document.querySelectorAll('.person')].map(element=>({{element,search:element.dataset.search,outcome:element.dataset.outcome,employers:JSON.parse(element.dataset.employers)}}));const search=document.getElementById('search');const employer=document.getElementById('employer');const outcome=document.getElementById('outcome');function filter(){{let n=0;const q=search.value.toLocaleLowerCase();for(const p of people){{const show=p.search.includes(q)&&(!outcome.value||p.outcome===outcome.value)&&(!employer.value||p.employers.includes(employer.value));if(p.element.hidden===show)p.element.hidden=!show;if(show)n++;}}document.getElementById('visible-count').textContent=n.toLocaleString()+' people shown';}}search.addEventListener('input',filter);employer.addEventListener('change',filter);outcome.addEventListener('change',filter);</script></html>"""


def render_csv(prepared):
    output = io.StringIO()
    writer = csv.writer(output)
    has_language_assignment = bool(prepared.get("primary_language_assignment"))
    has_fresh = any("language_assessment" in person for person in prepared["people"])
    has_summaries = any(
        "biography_summaries" in person for person in prepared["people"]
    )
    writer.writerow(
        [
            "handle",
            "name",
            "native_x_id",
            "outcome",
            "person_id",
            "account_key",
            "employer",
            "brand_id",
            "company_ids",
            "status",
            "start_date",
            "start_precision",
            "end_date",
            "end_precision",
            "title",
            "job_function",
            "department",
            "team",
            "description",
            "location",
            "affiliation_action",
            "source_urls",
            "saved_evidence",
            "notes",
        ]
        + (
            [
                "primary_language",
                "primary_language_origin",
                "primary_language_decision",
                "primary_language_previous",
                "primary_language_action",
            ]
            if has_language_assignment
            else []
        )
        + (["language_signal", "language_evidence"] if has_fresh else [])
        + (["biography_summaries"] if has_summaries else [])
    )
    for person in prepared["people"]:
        for role in person["affiliations"] or [None]:
            f = role["fields"] if role else {}
            values = [
                person["handle"],
                next(iter(person["names"]), ""),
                person["native_id"],
                person["outcome"],
                person["identity"]["person_id"],
                person["identity"]["account_key"],
                f.get("observed_organization_name"),
                f.get("brand_id"),
                "; ".join(role["chain"]["company_ids"]) if role else "",
                f.get("status"),
                f.get("start_date"),
                f.get("start_date_precision"),
                f.get("end_date"),
                f.get("end_date_precision"),
                f.get("title_raw"),
                f.get("job_function"),
                f.get("department"),
                f.get("team"),
                f.get("description"),
                role["location_text"] if role else "",
                role["action"] if role else "",
                "\n".join(e["source_url"] for e in role["evidence"]) if role else "",
                "\n\n".join(e["evidence_text"] for e in role["evidence"])
                if role
                else "",
                "\n".join(
                    [
                        person["note"],
                        *person["issues"],
                        *(role["notes"] if role else []),
                        f.get("review_note") or "",
                    ]
                ),
            ]
            if has_language_assignment:
                language = person.get("primary_language_assignment", {})
                values.extend(
                    language.get(k)
                    for k in (
                        "value",
                        "origin",
                        "decision_id",
                        "previous_value",
                        "action",
                    )
                )
            if has_fresh:
                assessment = person.get("language_assessment", {})
                values.extend(
                    [
                        assessment.get("outcome", ""),
                        json.dumps(assessment.get("evidence", []), ensure_ascii=False),
                    ]
                )
            if has_summaries:
                values.append(
                    json.dumps(
                        person.get("biography_summaries", []), ensure_ascii=False
                    )
                )
            # Prevent saved source strings from becoming spreadsheet formulae.
            writer.writerow(
                [
                    "'" + v
                    if isinstance(v, str) and v.startswith(("=", "+", "-", "@"))
                    else v
                    for v in values
                ]
            )
    return output.getvalue()
