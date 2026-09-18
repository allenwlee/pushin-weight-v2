# Translation diagnostic adjudication

These eight posts deliberately include earlier failures. Their error rates describe this difficult development packet, not normal production traffic. The original blinded reviewer files remain unchanged. The parent review below adds missed findings; automated reviewer agreement is not human-verified truth.

## Initial Qwen run

The independent review found four erroneous source posts out of eight. Parent inspection confirms the rejection and adds two material findings on already-failing posts: Korean `49억` became **49 billion** in English instead of **4.9 billion**; French `c'est quoi ce poulet` became a literal chicken/bird reference rather than an impressed colloquial reaction. The Japanese Korean-headline translation also uses leading/guiding China where the source concerns getting ahead of China. These additions do not change the four-post minimum error count. The original review's “good” dispositions for those outputs are superseded.

## Initial Gemini run

The independent review found four erroneous posts and left the French post unresolved. Parent review adds the Korean headline's English **“China must lead”**, which reverses the omitted subject/object relationship of Trump's call to get ahead of China. It resolves the French post as defective: the Japanese becomes a direct chicken/coward insult, while the Chinese introduces **US** cents (`美分`) although the source says only `cts`. That currency error is independently sufficient even without resolving the idiom. This yields **six confirmed erroneous source posts out of eight**.

## Linguistic evidence

The French dictionary records a colloquial sense of *poulet* for something exceptionally good; interpreting it as admiration in a post celebrating a very low token price is a contextual inference. [Wiktionnaire](https://fr.wiktionary.org/wiki/poulet).

The Korean national dictionary lists *앞서다* as outstripping or surpassing. The supplied headline attributes the demand to Trump and contrasts it with slowing AI development; reading the omitted comparison relation as getting ahead of China follows that context. [National Institute of Korean Language](https://krdict.korean.go.kr/eng/dicSearch/SearchView?ParaWordNo=71587&nation=eng&nationCode=6).

## Next configuration

Both second attempts keep the source text and existing translation semantics unchanged, enable a bounded 2,048-token reasoning allowance, and add corresponding output headroom. Small interface probes confirmed actual nonzero reasoning usage for each route. Reasoning is an experiment, not an assumed solution: cost, latency, every missing output, and remaining meaning errors must still be counted. No extra translation or repair call is introduced.
