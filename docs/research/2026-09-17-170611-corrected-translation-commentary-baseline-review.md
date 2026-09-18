# Corrected translation and commentary baseline review

This replaces no prior review artifact. It is a bounded source-only review of the current packets and does not use the rejected `review-s.json`, `review-t.json`, or the earlier summary.

`review-s2.json` records six confirmed erroneous translation sources in the 24-row diagnostic: the Japanese one-tenth discount, three outputs that literalize the French slang/introduce a Chinese denomination, two Japanese wrong-language outputs, the Hausa `Yara` subject error plus its English qualifier omission, and the Japanese DeepSeek-comparison parsing error. One code-switched Japanese output is uncertain rather than counted. The 103-line post's Chinese and Japanese translations are explicitly unreviewed.

`review-t2.json` reviews the primary smoke8 only. All eight rows delivered all three commentary locales. One source has a minor, three-locale unsupported image claim; a playful `lol` hypothesis is retained as uncertain rather than counted as a defect. Of the optional extra sixteen, fourteen completed and two were excluded before a model call by `synthesis_input_cap_exceeded`; those are operational coverage exclusions, not model-semantic errors.

Both review files retain exact source and output spans for every recorded translation finding. Their totals are derived from the locale-status maps with the embedded jq expressions.
