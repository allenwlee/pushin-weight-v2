# Independent reviews S and T

Reviews S (translation) and T (commentary) cover the supplied 24-post,
72-locale packets using only each packet's source and stored context. They are
selected difficult diagnostics, not a prevalence estimate or human gold
standard; automated reviews are not owner labels.

Translation S found 4 erroneous source posts, 0 missing, and 0 additional
uncertain. Locale totals were EN 23 good/1 error, Simplified Chinese 24/0,
and Japanese 21/3. The smoke8 subset had 8 sources, 2 erroneous, 0 missing,
and 0 additional uncertain.

Commentary T found 3 erroneous source posts, including 2 sources unavailable
because of pre-call input-cap failures, and 0 additional uncertain. Locale
totals were EN 21 good/1 error/2 unavailable, Simplified Chinese 22/0/2,
and Japanese 21/1/2. The smoke8 subset had 8 sources, 2 erroneous, 1
missing/unavailable, and 0 additional uncertain. The 24-post commentary
packet is exploratory and uses a different execution configuration from the
current smoke8 candidate.

Exact source and output spans, corrections, and an explicit good/error/
uncertain/unavailable status for every locale are recorded in
`.context/model-task-20260917/review-s.json` and `review-t.json`.
