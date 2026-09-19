# Qwen3-235B translation v3 review amendment

This amends the retained v3 source review without rewriting it. The original review left 19 delivered locales unreviewed because their sources already had coverage failures. Those locales are now assessed in `.context/model-task-20260917/qwen235-translation-v3-diagnostic24-20260917-125905/source-grounded-review-v3-amendment.json` (SHA-256 `2024d8137c2e638d276ce1edbfbffacec08741bcc434da7fbc20f181a1a8be93`).

The diagnostic has 55 generated targets: 29 were delivered and reviewed, and 26 are coverage errors. Together with 17 native-copy fields, the 72 required fields resolve to 26 coverage errors, 40 passes, and six semantic errors. The five semantic-error sources are the two already reported complete-source errors plus three sources which also had a coverage failure: the one-tenth-price source is rendered as 10% off in English; French approving slang `c’est quoi ce poulet` becomes literal chicken in Japanese; and the Japanese Tetris post changes the stopped subject from the Qwen/Tetris effort to the speaker.

There are 15 coverage-failure sources and five semantic-error sources; three semantic sources overlap coverage failures. The source-level union remains 17, so the interval remains [17,17] against incumbent [7,8]. This confirms the previous no-advance decision and does not change its route- and price-cap-limited scope.
