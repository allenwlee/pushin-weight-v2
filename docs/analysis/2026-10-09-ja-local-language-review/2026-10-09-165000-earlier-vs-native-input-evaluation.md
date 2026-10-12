---
title: G2 — editorial evaluation of earlier and fully local-language drafts
date: 2026-10-09
status: provisional-editorial-assessment
---

# Earlier versus fully local-language drafts

The fully local-language rerun did not consistently improve the writing.
The earlier high-model drafts often have stronger hooks and tighter pacing;
some new Japanese Wang passages are more specific and naturally conversational.
The new Chinese medium-model drafts avoid serious name/price mistakes in the
earlier set. Accuracy, publication resemblance and liveliness must be considered
together rather than collapsed into an automatic win for the latest version.

This is a reading of the actual saved draft artifacts. Criteria are naturalness,
headline appeal, intended outlet style, comprehension for outsiders, story
coherence, factual fidelity and unnecessary length. This does not score the
prompt/process or assert a language-only causal effect. Earlier Chinese role
sentences were already Chinese; their packets were mixed/English and their
transport was Codex CLI. The native rerun used translated Markdown and direct
Responses API. No additional generation call or prose rewrite was made.

| Language / voice / model | Editorial preference | Evidence |
| --- | --- | --- |
| Japanese / ToSpo / 6.1 high | Earlier, slightly | Earlier “AI界の大物” reads more naturally than new “AI大物”; both headlines deliver the same $5699→$30 contrast. Earlier Wang closes sharply on “ブランドの盛りすぎには赤ペン、肉体への褒め言葉には一転して寛大”. New adds repetition and an unsupported “頼まれてもいない”. New Japanese rendering of Wang's name helps outsiders, but the older copy has better pace. |
| Japanese / RocketNews24 / 6.1 high | Mixed: new Wang body, earlier Chonk | Earlier “【値札、盛りすぎィ！】…→『30ドルの古着です』” is the sharper hook. New “眼鏡より下着の情報が詳しい” and the accurate $240/$245 breakdown develop jokes from actual details, with fewer overt English-to-Japanese glosses. However, new Chonk repeatedly explains verification/availability and ends in generic future evaluation; the earlier Chonk headline “名前はぽっちゃり、規模は1兆” and tighter narrative are stronger. |
| Japanese / ToSpo / 6 Sol medium | Roughly tied; neither compelling as the house voice | Both coherently combine the stories, so combining is not itself a defect. New opening clearly describes “二つの盛り”; earlier has a lighter final “ツッコミどころも特大”. New “高級ブランド疑惑” risks making an outfit joke sound accusatory and adds an unverified present-time employment expression. Earlier “態度を軟化” also overinterprets a joking follow-up. Both remain mild news roundups more than a distinctive ToSpo treatment. |
| Japanese / RocketNews24 / 6 Sol medium | New for fidelity; earlier for hook | Earlier's approximate ¥850,000 makes the price easier for a Japanese reader to grasp, but no rate was supplied. New drops that unsupported conversion and preserves the event cleanly; its headline also loses the $30 payoff and its Wang article omits founder context. Earlier Chonk's short “名前は『ぽっちゃり猫』!?” hook is more inviting than the new long, cautious fan-reaction title. New is cleaner, not livelier. |
| Chinese / Metro / 6.1 high | Earlier | Earlier gives status, action and price payoff immediately: “被标成近万美元奢牌…T恤只花了30美元”. New “5699美元Gucci？…亲自给穿搭标签改价” omits the cheap-price payoff and relies more on a foreign name. Earlier is more economical human-interest news. Its weights-release headline compresses a plan into definite future wording. |
| Chinese / Metro / 6 Sol medium | New overall; earlier Chonk alone | Earlier Wang introduces unsupported “王兴兴” and miscalculates $9599 instead of $9569. New “上衣是30美元二手货” is concrete and grounded. Earlier Chonk is more inviting; new makes “猫梗来历仍是网友说法” the hook, foregrounding verification rather than the funny event. |
| Chinese / WeMedia / 6.1 high | Earlier for voice; neither clean unchanged | Earlier “名字负责卖萌，参数负责撑场面” is idiomatic and shareable. New “先别替CEO确认动机” sounds like instructions to an editor inside the article; intro, sections and ending repeat the same contrast. Earlier “被扒出一身奢侈品” can imply confirmed brands despite the correction, and “没人问” is unsupported. |
| Chinese / WeMedia / 6 Sol medium | New, narrowly | New “一件30美元的迷彩T恤，和一只‘胖猫’” gives a coherent two-story promise and avoids the earlier unsupported “王兴”. Earlier “亲自拿红笔改作业” is livelier. New is a safer concise review candidate, but depends on the separate background panel to explain Wang's founder status. |

The length increase in the Japanese high-model complete replies is about24%
for ToSpo and30% for RocketNews24, counting characters after removing URLs.
Chinese high replies grow by about1.6× in Chinese-character count. Length alone
is not a defect: new Wang's eye/underwear contrast and arithmetic add useful
material. Added source-check reminders and repeated explanations in several
Chonk/high-model drafts reduce momentum without adding comparable pleasure.

The most consequential recurring defect is source-audit language appearing
inside reader copy: “今回の素材には…” / “所提供材料中…” / “不能直接写成…”.
Readers need clear attribution and the relevant API-versus-weights distinction;
repeated commentary about what the supplied packet does not establish makes
the piece feel like a review memo. An explicit stage such as “10月末の公開を
予定” can preserve accuracy naturally without stopping the story.

For native feedback, strongest Japanese specimens are earlier ToSpo6.1,
earlier Rocket6.1, and the new Rocket6.1 Wang article as a meaningful alternative.
Chinese Metro's strongest candidate is earlier6.1. Earlier WeMedia6.1 best
demonstrates the desired voice, with factual concerns disclosed; new WeMedia6 Sol
is the safer short candidate. Neither combined output nor longer output is
automatically rejected. No draft is declared house-voice-qualified or cleared
for publication by this evaluation; native readers remain the final language
and style check.

Evidence: original Japanese texts under `.local/g2-ja-voices-20261009/bare/`
and `.local/g2-ja-local-language-20261009/bare/`; source/length observations in
`.local/g2-ja-local-language-20261009/comparison-evidence.json`; explicit Chinese
delegate's full comparison under
`.local/g2-zhcn-local-language-20261009/2026-10-09-165500-old-new-editorial-evaluation.md`.
The reviewer-page explanation/layout change is not treated as writer quality.

The owner's subsequent latest-Chinese Chonk image request was completed using
a visible standalone frame from Mistral's official video at4seconds, with
source caption and preserved video. It changes reader media presentation only;
all generated text, prompts and packets remain unchanged. See the
[scoped image receipt](../2026-10-09-zhcn-local-language-review/2026-10-09-170000-chonk-image-fix-addendum.md).
