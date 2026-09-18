# Model trial evidence — corrected manifest

This preserves the 169 completed trial/review artifacts from the earlier export with an externally verified manifest. The earlier export accidentally listed its own manifest checksum; this replacement excludes that self-entry. Original source evidence is byte-identical. It predates the new 4.1 benchmark and rejected S/T reviewer drafts.

The archive contains contracts, final provider reports, reviews A–R and their rubric. These are development diagnostics, not qualification results. Extract into a new directory, then run `shasum -a 256 -c MANIFEST.sha256` from that directory. All 169 member checksums were verified against the archive bytes.
