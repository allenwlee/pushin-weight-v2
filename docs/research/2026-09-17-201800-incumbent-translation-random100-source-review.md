# Incumbent translation random100 source review

Reviewed 2026-09-17 against all 100 records in `random100-live-input.json` and the retained incumbent `translation-result.json`. No requests were made. The retained result has no transport failures, contains 85 exact native-language controls, and supplies all 215 required generated targets.

The matching 24-row S3 baseline is preserved, including its seven confirmed source failures and one tokenizer-attachment unknown. The wider review finds two additional source failures outside that subset: the Japanese target for post `2100205285700747681` remains Turkish (`API'yi nereden alacağız hocam el birliğiyle yapalım`), and the Japanese target for `2100307770360913963` leaves the ordinary Chinese word `干货` untranslated.

The mechanically derived full-cohort result is 285 good, eight material-error, five minor-error, and two uncertain output fields. At source level that is nine confirmed erroneous sources, one uncertain source, and a conservative interval of **[9, 10]**. Six sources have material defects and three have minor defects. The detailed record preserves exact spans and every locale status in `review-incumbent4.1-translation-random100.json`.

The old45 incumbent reference issue remains separate: its ten Japanese-as-Chinese rows occur in both saved raw response and report, so they are output/canonicalization defects rather than report-field extraction artifacts. They do not establish a random100 error without matching random100 source/output evidence.
