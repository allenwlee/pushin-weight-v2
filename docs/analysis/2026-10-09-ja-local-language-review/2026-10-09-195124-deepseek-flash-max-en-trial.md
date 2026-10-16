# DeepSeek V4.1 Flash/max, mostly English inputs

Five first replies were generated with exact API alias `deepseek-flash`,
`reasoning_effort: max` and enabled thinking. The authenticated model catalog
returned that alias; [official model documentation](https://api-docs.deepseek.com/quick_start/pricing/)
maps it to DeepSeek-V4.1-Flash. The [request documentation](https://api-docs.deepseek.com/api/create-chat-completion/)
supports literal max effort and image input. Each request supplied both saved
Wang and Le Chonk stories, the existing English source packet and Wang's
original correction image. No style examples or output schema were added.

The English role sentences were:

- `Write in Japanese as if you were the editor of ToSpo (Tokyo Sports).`
- `Write in Japanese as if you were the editor of RocketNews24.`
- `Write in Simplified Chinese as if you were the editor of Southern Metropolis Daily.`
- `Write in Simplified Chinese as if you were the editor of a WeChat Official Account.`
- `Write as if you were the editor of the New York Post.`

All five requests returned the requested alias and completed with `stop`.
Japanese and Chinese replies each contain both stories. The English NYPost
reply contains only Wang, even though both stories were supplied. Its Chonk
selection explicitly displays the omission and retains the complete reply;
no second draft was invented, substituted or requested. Japanese Rocket and
both Chinese replies have shared introductions; Rocket and WeChat also have
shared endings. The reader page preserves those original sections alongside
the selected story. All five complete replies remain available unchanged.

The [combined review page](all-languages.html) now contains 35 saved replies,
six models and 70 story selection slots. Select Flash with EN/mixed inputs.
No Flash local-input call was made, so those combinations remain explicitly
untested. Earlier replies, source media and all eight saved editorial picks
are unchanged. The original DeepSeek Pro Rocket refusal is preserved.

| Output / voice | Input tokens | Output tokens including reasoning |
|---|---:|---:|
| JA / ToSpo | 2,980 | 26,757 |
| JA / RocketNews24 | 2,977 | 15,064 |
| zh-cn / Metro | 2,979 | 10,258 |
| zh-cn / WeChat | 2,980 | 9,857 |
| EN / NYPost | 2,976 | 7,724 |
| Total | 14,892 | 69,660 |

The maximum was 131,072 output tokens per call, with concurrency two, five
physical calls, zero retries/refinements and a USD1 ceiling. Conservative
peak reservation was USD0.816432. Usage at the published off-peak prices
estimates USD0.0440298; the peak-price comparison is USD0.0880596. Actual billed
charges were not returned by the API. Only the explicitly selected DeepSeek
credential was read; no secret value is saved in these records.

Real-browser verification passed 306 states across 1400×1000,1280×800 and
390×844: 210 saved-reply views, including six preserved refusal views and three
English omission views, plus 96 explicit untested views. All original raw texts
match their independently saved responses. Eight best-pick transitions and
reloads pass; images, source video and downloaded standalone HTML work.
Downloads preserve Flash selection in all three languages. No page errors,
failed asset requests or horizontal overflow occurred. Native explanations
fit the first screen; desktop/phone screenshots for all three languages were
inspected. The previous 30 complete records, media and picks match the saved
snapshot, and all 64 previously protected files retain their hashes. The
extended preservation manifest covers 79 files.

The owner's existing combined Chrome tab919891953 in window919891824 was
refreshed on allenwlee to Chinese Metro/Flash/Chonk/EN inputs, retaining the
story and voice the owner had open. The native title and exact model URL were
observed; six other tabs and their URLs were preserved. The preview remains
on fuchitalee at port58423. No application, production configuration, database,
Git publication, release or voice activation occurred. Native-reader assessment
and a new editorial ranking remain pending.

Private evidence: `.local/g2-deepseek-flash-max-en-20261009/` contains the
provider catalog/discovery, exact sanitized requests/roles, unchanged final
responses, private reasoning/stream events, receipts, token/budget summary,
previous combined HTML/build/data/proof snapshots and owner-browser observation.
Current additive renderer and browser proof are in
`.local/g2-combined-review-20261009/`.

English packet SHA-256: `9547378f7b71c72ae37f3202b6d617372f8268fc5b709486812de36a9f5c56d6`.
Combined page SHA-256: `6d1edea61f11f1432232fac41c53ef586b4413e7fe99798743d3b7bbbd9370ec`.
Worktree: `feat/g2-round2-voices`, base `1743234aa95e8b31d0613f313a88a4e9c60115b5`.
Completed: 2026-10-09T19:51:24+09:00.
