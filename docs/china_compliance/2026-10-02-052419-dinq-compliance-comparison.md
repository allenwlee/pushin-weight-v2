---
title: Dinq comparison — Chinese talent data, permissions and founder travel
created_at: "2026-10-02T05:24:19+09:00"
sources_checked: 2026-10-02
status: research-for-legal-review
workstream: G1
jurisdiction: mainland-China
---

# Dinq comparison — Chinese talent data, permissions and founder travel

Dinq is a close commercial comparison for professional-person data. Its public
documentation describes discovery, enrichment, evaluation and monitoring of
people across public sources. That supports the existence of a commercial use
case. It does not demonstrate Chinese regulatory approval, lawful processing
of every candidate, or safe travel for another company's founder.

This report compares published claims with our G1 pilot and the
[mainland China legal/travel research](2026-10-02-051235-mainland-china-staff-data-and-travel-risk.md).
It is a public-document review, not a legal opinion or an audit of Dinq's
implementation. No account was created, candidate search executed, private data
submitted or API connected. Recommendations remain proposals.

## What the public product documents establish

| Documented capability | Evidence and relevance |
| --- | --- |
| Professional-person discovery | The [About page](https://dinq.me/about) describes discovering, evaluating and monitoring talent across the open web for recruiting teams, founders and research organizations. This is substantially related to our professional-profile use case. |
| Cross-source profiles and scoring | [Evaluate Profiles](https://docs.dinq.me/core-features/search/evaluate-profiles) describes work and education history, source links, projects, papers, social profiles and match scores. Its evaluation can consider career trajectories and professional contribution signals. Such analysis deserves separate consideration from merely reproducing a biography. |
| Contact retrieval and outreach | [Outreach](https://docs.dinq.me/core-features/outreach) documents email retrieval and contextual message drafting. The current G1 pilot does not establish a comparable contact-finding or messaging service. |
| Continuing monitoring | [Talent Radar](https://docs.dinq.me/core-features/talent-radar) describes recurring searches and tracking specific people's career changes or output. The page limits availability to selected accounts; this review did not test it. |
| External tools and reuse | The [API](https://docs.dinq.me/platform/api) and [MCP](https://docs.dinq.me/platform/mcp) docs describe moving search/profile results into other workflows. API access alone does not establish downstream publication, resale or photo-reuse rights. |
| Claimed Chinese-platform coverage | A [WorkBuddy guide](https://dinq.me/guides/workbuddy-mcp-mapping) lists Xiaohongshu and Zhihu among sources. This is a vendor coverage claim, not proof of official access, current endpoint reliability, actual mainland-person coverage or usable portraits. |

The [current FAQ](https://docs.dinq.me/help-support/faq) describes both a
user-created DINQ Profile and candidates found through public professional
information. Those modes should be distinguished. The pages reviewed do not
establish that every search subject registered an account or opted into a
recruiting service.

## Published protections worth examining

Dinq's [Data & Privacy documentation](https://docs.dinq.me/data-and-privacy)
describes source attribution, separation of private workspace material from
published profiles, and processes for access, correction, deletion or
restriction. It presents AI results as material for human verification. These
are useful product practices to consider for G1; this review did not test their
operation or coverage of people who never registered.

Its [community guidelines](https://dinq.me/guidelines), dated December 15,
2025, require rights to uploaded media and express consent for photos featuring
other people. The [terms](https://dinq.me/terms), effective January 15, 2026,
prohibit biometric information in user inputs. No facial-matching feature was
found in the pages reviewed.

**Implication for G1:** Dinq is not evidence that attributed photos automatically
authorize face recognition. Our saved pilot records image sources; the earlier
proposal to recognize people in later images needs its own assessment.

## Questions the public pages leave unresolved

**How does notice and permission work for nonmembers?** An older
[FAQ dated February 7, 2026](https://dinq.me/blogs/dinq-faq) emphasizes data
users choose to link or upload. Current discovery docs describe broader public
collection. This may reflect different product modes or later development; it
does not prove unlawful collection. It does leave an incomplete public
explanation of nonmember discovery, objections, corrections and deletion from
search results and downstream copies.

**Which entity and legal basis govern mainland-person processing?** The
[terms](https://dinq.me/terms) identify Lemma Labs, incorporated in the Cayman
Islands, and specify Cayman governing law with mandatory local protections
preserved. The [privacy policy](https://dinq.me/privacy), effective January 15,
2026, describes processing primarily in Singapore and the United States and
lists consent, contract and legitimate interests as bases. Those statements do
not resolve PRC law's territorial application or provide a PRC processing basis
for every candidate.

PIPL's enumerated bases do not include a general standalone
legitimate-interests category. Its overseas scope, rules for public information,
automated decisions and impact assessments warrant review against the real
service. Whether a particular score meets the statutory definition or
significantly affects a person requires more than a marketing-page description.
[PIPL, Articles 3, 13, 24, 27, 55 and 73](https://www.cac.gov.cn/2021-08/20/c_1631050028355286.htm).

**What governs external AI providers?** Privacy policy section 3.3 limits service
providers' use of information to their assigned tasks, while terms section 3.6
says third-party AI providers may not be required to keep content confidential.
Ask which contracts and protections apply to which data before sending dossiers.
This drafting tension is a question for diligence, not proof of a breach.
[Privacy](https://dinq.me/privacy), [terms](https://dinq.me/terms).

**What reuse is actually permitted?** The terms restrict scraping and
unauthorized profile copying or monetization. A proposed customer integration
would need the applicable API agreement, source licences, retention rules and
deletion obligations. No such agreement was inspected.
[Terms](https://dinq.me/terms).

## What this means for our project and the owner's questions

The current G1 pilot has 24 sourced people and 35 stored images; it distinguishes
current/founder claims, former or dated employment, and contributor-only
observations. Dinq documents broader recruiting analysis, contacts, outreach and
monitoring. That comparison helps define real commercial purposes, but greater
feature scope does not tell us which company has obtained which permissions.

Three conclusions follow from the evidence:

1. **A people table is not itself evidence of espionage.** The relevant facts
   include purpose, collection methods, permissions, sensitivity, recipients and
   actual uses. The public evidence does not classify our roster as state
   secrets or legally designated important data.
2. **Helping researchers is relevant but needs to be reflected in the service.**
   Voluntary participation, audience choice, accurate profiles and effective
   corrections would support that purpose more directly than a statement that
   unsolicited dossiers benefit their subjects. This is our assessment, not a
   statutory exemption.
3. **A Chinese customer or job has limited evidentiary value.** A genuine
   subscription can document commercial purpose. An employer may support work
   authorization. Neither constitutes government approval of unrelated data
   processing or protection from travel restrictions. See the
   [customer/employment analysis](2026-10-02-051235-mainland-china-staff-data-and-travel-risk.md#a-chinese-customer-or-employer-helps-with-different-limited-questions).

The overarching legal framework combines individual rights, lawful development
and national security; overseas transfers are an additional regulated activity,
not a blanket prohibition. The
[companion report](2026-10-02-051235-mainland-china-staff-data-and-travel-risk.md#the-governing-framework-includes-rights-development-and-national-security)
links the official laws and distinguishes their rules from our assessment.

## Limits and next use of this research

The public pages reviewed do not establish Dinq's mainland regulatory status,
source-by-source permissions, complete data flows or compliance of any specific
record. They also do not establish its founders' citizenship, travel history,
visa permissions or treatment by authorities. Absence of those details from
public documentation is not evidence of noncompliance.

For a legal review of PushinWeight, bring our actual dossier, collection methods,
intended customers and proposed uses. For a possible Dinq purchase, ask about
nonmember coverage, mainland-person processing, permitted reuse, image rights,
subprocessors and deletion propagation. This research does not authorize a
purchase or change the accepted G1 collection scope.
