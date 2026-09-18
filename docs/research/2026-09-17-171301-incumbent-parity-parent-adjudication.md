# Incumbent parity: parent adjudication recommendations

`review-s3.json` completes the current 24-source incumbent translation baseline. It has seven confirmed erroneous sources, one source with an unresolved tokenizer-attachment ambiguity, and sixteen sources with all three outputs reviewed good. The 103-line source is now fully reviewed and no longer an unreviewed coverage gap.

Use the v2 parity rule on the exact 24-source cohort: compare each candidate independently to the source, then count source posts once when any required locale has a confirmed semantic, structural, transport, or pre-call defect. A candidate can equal or beat this incumbent only if its confirmed erroneous-source count is at most seven. The tokenizer source is neither a pass nor an incumbent error until parent adjudication resolves its attachment; it must not be used to prove parity.

For the eight-source commentary smoke set, T2 has one confirmed erroneous source: every locale describes the opaque t.co URL as an image. The `lol` interpretation is unresolved because playfulness does not prove that the hypothesis was unserious. Keep it unknown unless a source-only rationale changes that conclusion. The Korean Japanese commentary paraphrase does not warrant an automatic error.

Recommended comparison categories are candidate-only errors, incumbent-only errors, and shared errors, grouped by source ID, locale, and severity. Report coverage failures separately. This diagnostic can support regression and fresh qualification work but does not establish population parity.
