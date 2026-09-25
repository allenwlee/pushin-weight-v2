# Docs taxonomy

This guide helps people and agents choose an existing home for a document in
`docs/`. Put a document where its main purpose fits. Prefer the most specific
existing folder, and link to related material instead of copying it into
several places.

Do not create another folder under `docs/` for a new task. Use an existing
folder. If none fits, put the draft in the closest existing folder and ask
before proposing a new one.

## Folder guide

| Folder | Put these documents here | Examples and boundaries |
| --- | --- | --- |
| `docs/reference/` | Detailed, maintained descriptions of how the current product, data, or operating interface works. Write for people and for people to refer agents to. | Keep a comprehensive current snapshot. Do not turn a reference into a change log or preserve obsolete behavior as history; Git keeps the history. Use plain explanations alongside precise technical details. |
| `docs/analysis/` | Results from tests, evaluations, measurements, data reviews, and structured comparisons. | Keep each result's population, method, evidence, limits, and conclusion together. Machine-readable evidence may live alongside a report when it is part of that analysis. |
| `docs/research/` | Findings gathered to learn about an external subject, vendor, market, technology, or source corpus. | Record sources and when changeable facts were checked. For conclusions about a PushinWeight failure, use `investigations/`. |
| `docs/investigations/` | A focused inquiry into a specific observed behavior, failure, or uncertain project question. | Include the question, evidence examined, reasoning, and findings. Move reusable fixes into `solutions/` once established. |
| `docs/iterations/` | Records and evidence for a particular product or interface iteration. | Use for dated UI comparisons, iteration reports, and approved visual or behavioral targets tied to a specific baseline. |
| `docs/ideation/` | Product and design exploration, proposals, mockups, and their supporting assets. | Use the existing `assets/` and `mockups/` folders where appropriate. Ideation is not an approved implementation plan. |
| `docs/brainstorms/` | Early requirements exploration and brainstorming records. | Keep the open questions and candidate directions distinct from settled decisions. |
| `docs/ideate/` | Existing ideation artifacts that predate or do not fit the current `ideation/` structure. | Do not add new material here when `ideation/` is the clearer existing home. |
| `docs/plans/` | Step-by-step implementation plans with scope, file paths, order, verification, and completion criteria. | Follow the repository's plan naming and Ollija requirements. A plan describes work to do; it is not a record of completed results. |
| `docs/operations/` | Instructions for running, inspecting, recovering, or maintaining the live or staging system. | Use for operator procedures and runbooks. Put release and deployment procedures in `deploy/` when they are specifically about shipping. |
| `docs/deploy/` | Deployment topology, release steps, verification, rollback, and hosting runbooks. | Keep operational release instructions together with the service they affect. |
| `docs/how-to/` | Reusable task instructions for people using the project or its tools. | Use for a repeatable task that is not specifically a live-system operation or deployment. |
| `docs/solutions/` | Reusable lessons from a problem that has been solved and verified. | Follow the existing category folders and metadata format. Do not use this as an incident timeline. |
| `docs/issues/` | A tracked description of an unresolved product or engineering issue. | Keep the problem and its current state clear; put the investigation or proposed fix in its appropriate document. |
| `docs/debug/` | Focused debugging evidence that is still being assembled. | Move the durable conclusion to `investigations/` or `solutions/` when the work is complete. |
| `docs/reviews/` | Review findings for code, plans, releases, or other named artifacts. | Identify exactly what was reviewed and distinguish findings from implementation decisions. |
| `docs/handoffs/` | Continuity notes that help another person or agent resume a specific session or task. | Include current state, completed work, remaining work, and important constraints. A handoff is not the canonical product reference. |
| `docs/notes/` | Short-lived working notes that do not yet have a more suitable home. | Move durable findings to the appropriate folder; avoid making this a permanent catch-all. |
| `docs/screenshots/` | Screenshots and other captured visual evidence. | Keep evidence with its named review or iteration where practical; do not treat a screenshot alone as a specification. |
| `docs/external_vendors/` | Vendor documentation, integrations, pricing evidence, and vendor-specific research. | Keep vendor material under its existing vendor folder when one exists. Separate PushinWeight's current integration behavior into `reference/`. |
| `docs/ollija/` | Ollija-specific project workflow records and generated guidance. | Use only for material about the Ollija workflow, not general implementation plans or product documentation. |

## Choose by purpose

When a document could fit in more than one folder, use this order:

1. Put current, reusable descriptions of how PushinWeight works in
   `reference/`.
2. Put measured results and test or evaluation evidence in `analysis/`.
3. Put external-source findings in `research/`; put a diagnosis of a PushinWeight
   behavior in `investigations/`.
4. Put instructions for operating or deploying the system in `operations/` or
   `deploy/`.
5. Put proposed future work in `plans/`, and early exploration in
   `brainstorms/` or `ideation/`.
6. Put solved, reusable lessons in `solutions/`.

Keep executable tests and machine fixtures in the repository's `tests/` tree,
not in a new `docs/test/` folder. A report that explains test results belongs
in `analysis/` and should link to its code or fixture.

## Reference-document rules

- Describe the codebase and product as they are at the time of writing.
- Keep each reference comprehensive, detailed, and at least as useful as the
  material it replaces. Do not summarize away implementation details, examples,
  caveats, or exact contracts.
- Use clear, direct language that a technically capable reader can follow
  without prior project context. Include the technical detail an agent needs
  to act correctly.
- Do not preserve obsolete behavior or explain how the system changed over
  time. Use Git history for that.
- Verify claims against the current code, configuration, tests, and schema.
  Link to primary project sources and to related references rather than
  duplicating their full contents.
- Keep literal prompts, schemas, and commands exact when the document says
  they are literal or machine-checked.
- Prefer stable descriptive filenames for maintained references. Use dates
  for dated evidence, evaluations, investigations, plans, and iteration
  records, not as a substitute for deciding whether a file is a reference.
- When moving or renaming a document, update its in-repository links and test
  references in the same change.

This taxonomy is a draft for review. Build a project-level docs-router skill
only after the folder rules and examples have been reviewed and settled.
