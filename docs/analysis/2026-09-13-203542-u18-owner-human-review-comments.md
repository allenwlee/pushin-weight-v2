here are all my comments, you will need to combine with my prior comments in this session and organize: ---
created_at: 2026-09-13T20:35:42.325709+09:00
timezone: Asia/Tokyo
source: sublime
---

general ask: to be super vertically oriented towards our audience, we need idiosyncratic tags including the following: local LLM; distillation claims. also, we need a tag for cost/performance. this was what 'discourse' taxonomy was supposed to be. do we need to revive discourse in order to do this? brainstorm and pov some ideas. these tags will change over time as we adjust to the most relevant topics of our audience.



H0040D161174
china nationalism: mild anti

H0DEC6F537E0
{"outcome": "classified", "post_types": ["questions_requests", "events"], "product_labels": ["ideas_requests"], "sentiment": "neutral", "china_nationalism": "none", "us_nationalism": "none"} <<< thef act that post type picked up question request, but product label did not, is concerning. should check on that. "i have some issues" is ambiguous enough for sentiment to be neutral or null

H1A3B3731E1C


this is actually a very standard 'journalism' post, reporting on something. post type should include research_explanation. sentiment should be neutral, since its stance is more info gathering.

H1E48CCEEB2F

see my thgouhts on a 'use-case' product label. this would be one of those posts.

H2B36BE298C6

this is a tough one. this is reporting on a clearly chinese nationalism stance. but the post itself is just reporting neutrally. so actually v26 is wrong in several ways. nationalism should be neutral; 

i'm wondering why this was detected as misinformation; give me details on how that occurred; my sense is that we need to rename misinformation. Grok's point is that it is more a flag for requiring further review. 

irregardless of whether thse claims were brought by a 3rd party or by the author of the post, in that event, allegations of misdoing, distillation, etc. should be given such a product label. let's brainstorm on better labels; some ideas: 'allegation'; but if allegation is what we are trying to find, then do we need a whole new product label? see if we can surface these particular posts by filtering for opinions/reactions with negative sentiments. if we do indeed relabel it allegation, or 'unproven claim', and reconfigure the prompt as such, roughly how many would we uncover on a % basis going forward?

this begs the question: releases/updates is currently geared towards product or brand specific ones (which it should be). however for general but very significant new releases such as this, how do we classify this? we have 13 posttypes already, to add another one would be really hard. if we do widen the definition of releases/updates to include news items such as this, how would user filter these for just product-specific release/updates?

H3569508600E

this should have a testimonial product label, and sentiment should be positive. 
"MiniMax H3 can generate video locally even with 8GB VRAM + 64GB RAM" <<< the use of 'even' is very telling: this is a positive endorsement of how, even with scant resources, minimax performs. the context is that local LLM is all about pulling intelligence from ever smaller hardware

H42DCD9324F4

this is advertising about a product called Runway. therefore sentiment and product label towards each brand should be neutral and none. it's the same point we had before: enforce sentiment and product label stance strictly towards the brand in question.
this should also get an unsanctioned flag, as this is advertising about a 3rd party product (we don't know for sure if they are affiliated with the brands, but we can add this flag as a caution--the user will know whether this was sanctioned or not)

H4E3B98376E5

this is also a news type, posting info from 3rd party with neutral stance like H1A3B3731E1C


H4E55D967F4E
why isn't this testimonial? give me a brief definition of how we are classifying a testimonial

H5024EDC82C6
should we relabel from crypto to blockchain? which is more accurate and more neutral (is crypto a bit negative)

H540717FEDF5
should be testimonial. this is not business/finance (see our prior discussion in session)

H638DEDC4101
another tough one that makes me rethink our taxonomy. posts like this are neither ostensibly pro/anti either cn or us. instead, they are making a broader geopolitical point. let's brainstorm on a better nationalism taxonomy that more accurately classifies this one. we definitely want to tag these kinds of posts with a 'geopolitical', or better yet, a 'state-level' classification, to show that user is mentioning a brand, but is making a point that widens the scope to include state actors. this is an insightful point that is not necessarily colored by bias either way--instead making a logical claim and putting forward an argument based on that.

H688781944AC
correctly classified as 'opportunities' by v25, however we need to make sure the time gating is properly ambiguous, as a 'closed beta' should not be surfaced as an impending event with a deadline. such closed betas asre not offered publicly, therefore it's debatable whether this is an opportunity or not. i think we can't capture every edge case such as this, so we can address this by having sufficiently vague time gates. note: whether we need a 'solicited' vs unsolicited type scale for requests (for the product people). i'd say no for now

H696CC3BCE4C
correct

H69C877BE195
this is NOT marketing spam, because it is written by an official account. for now, our official accounts (which are comprised of the ai labs) do NOT spam. however, in the future, when we widen the lens of the brands we track, we may in fact have brands (not ai labs, but intermediarly ai companies) that do spam. what is the easiest way we can clear current brands from any unsanctioned flags, but  allow for this rule to be differnetly applied in future?

H7046A8A0689
see my comments before; this is about meta model



H70A9986C432

it seems even the grok run didn't read the media, which is critical to interpreting this post. i used grok on the x post itself and here's the result:

The X post uses two anime-style chibi images of a blue-haired maid character celebrating Zhipu AI's GLM model price hikes ("GLM涨价") while dominating a defeated black-haired rival, with captions like "Finally got fooled" and "Price-hike big model, kneel before me!"
Text reads "依旧跑赢没奖励，跑输被斩杀" (Still, winning the race brings no reward; losing gets you beheaded), sarcastically critiquing the brutal Chinese LLM market where strong performance yields little gain but underperformance leads to elimination.
Hashtagged #DeepSeek, it references the intense 2026 AI pricing shifts—including DeepSeek's major August API hikes with peak/off-peak rates and prior price wars—amid broader industry moves by GLM and others toward value-based pricing.

The poster is complaining, in a jokey way, that competing in China’s AI-model market is a lose-lose game.They mean: even if your model “wins” (performs well or gains users), you still don’t get a real prize—prices stay squeezed or you have to raise them and look greedy. If you lose the race, you’re finished. The cute pictures mock GLM’s price hike and treat it like the winner stepping on a rival, while the #DeepSeek tag points at DeepSeek as part of the same messy price-war-then-price-hike cycle.


this post, without the media, is too short and cryptic to classify. how often do we see posts like these (where we can't interpret due to not accessing the media?) if it is rare, we can just pass on this for now and make this a to-do.

H74C810FB007
mostly correct. why not hands-on? presumably this author used it.


H7B628A24F88

this was correct not to apply hands-on, because technically, user did not have to actually use the product to pontificate on the underlying architecture


H7F29D6428BB

covered this last time



H87229E54527
covered this before



H8D074DCC4D3
context missing is correct; there is no parent to this post; either user misposted (rather than replying) or just posted this. 

H8FA9071508D
b.ai is spamming a lot via multiple accounts

H92A808A114E

sentiment should be positive. pointing out that 15 seconds of content can be generated in 9 seconds is a compliment. product label should be testimonial

H951CA2C2BF9


H9920CC08778


H9C7C731F3C3

sentiment should be positive; i do not see pro china nationalism here (at least in truncated message; this account has been suspended so i cannot see the entire message on x). give me the explicit pro china text that you have

HAF1D06FBEBA

HAF97A8DDDDE

HB4FB5810A09

this is from the official account, therefore it doesn't need a product label (should we add product labels to official account's posts, and then filter out later?)

HB94D1A5CA63
another canddiate for the news type post/tag

HC63FABBF5A3

HC9205DA00E5

should any post detected as advertising that is NOT for the brand itself, be tagged as unsanctioned?

HCA162EAEBE0
sentiment: positiv

HCC2BC2A1B6B
v26 correct

HCCC266D762E
covered by me before in session

HDA7D2AEEC6F
b.ai spam again - wondering if worth banning posts like this--but actually the post will already have been captured. probably not a ton of spam right now but this will increase once we add the frontier models to our list of brands being tracked. worth a small brainstorm--if there are enough posts like these


HE10CACEDD3F
how did this pass harvester? seems very rare and not worth worrying about

HE2CCD66B3DE

HE6730DF39A2
my interpretation is that sentiment is negative. user is expressing surprise that a model that lacks some fundamental capabilities got such a good score--therefore questioning credibility of those tests

HF3B55FD811B
covered before


HF4987074B1F

note this is from a staff account; note that without that context grok cannot properly classify, underlining the point that we probably should use our knowledge of official/staff accounts for our classifier


HF5D74262E64
i don't think this is clearly a complaint, product category should be none; grok's analysis is right

HF7C5DFD8079
correct



























. <<< save this entire prompt verbatim as an artifact and attach as exhibit to our plan ultimately. for now, evaluate all the questions and my comments, and organize into a summary to file. note that my personal eval of all 45 questions will be the only human review that we do, and so once these comments are addressed, show that the tests are closed and we can proceed.
