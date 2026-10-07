# G2 final browser receipt

Invocation: `ce-test-browser mode:pipeline current --port 58022` under LFG.
Driver: installed `agent-browser`, headless named session `g2-editorial`.
Server: `http://127.0.0.1:58022`, isolated `g2_editorial_dev`, ordinary local staff session. Server restarted after the reader simplification and review fixes.

| Route or flow | Status | Evidence |
| --- | --- | --- |
| `/` | Pass | Existing General page renders with brand controls and filters. |
| `/stories/?track=chatter&lang=en` | Pass | Saved hero and exactly five distinct prior stories; 1440-pixel viewport has no horizontal overflow. |
| Chatter motion and pause | Pass | History scrollTop advanced 0 to 15 while hero y stayed unchanged; pause held the position. Earlier reduced-motion evidence remains valid because JavaScript did not change. |
| `/stories/<id>/?track=chatter&lang=en&edition=<id>` | Pass | Exact edition, full saved article, source link, General/archive links and X share intent; Open Graph URL matches the pinned URL. |
| Story mobile at 390 by 844 | Pass | No horizontal overflow; image decoded and loaded at stored 320-pixel width. |
| `/stories/?track=pulse&lang=ja` | Pass | Japanese archive chrome and empty state. |
| `/api/v2/editorial-stories/?track=chatter&lang=en` | Pass | Saved headline and five history items, no original source text in output. |
| `/stories/<id>/assets/<picture>/source/` | Pass | Stored fixture served while picture mode is select_only; after restoring off, API asset is null and direct asset request returns 404. |
| External OAuth flow | Skip | Used an ordinary local staff session; external identity-provider interaction is outside this test. |
| X/Instagram/Facebook card rendering | Skip | No external posting or platform crawler test authorized. |
| Generated image/video quality | Skip | Local picture is a green file-serving fixture; no paid generation ran. |

Unexpected browser errors: none observed. Fixture data and screenshots remain local; this is functional evidence, not a final layout or generated-art quality assessment. Checked-in `config/editorial.yaml` was restored byte for byte to all-off defaults.

Result: **PASS for the local routes and interactions above; external flows skipped as listed.**
