# Product X/Hugging Face identity policies

## V1 provenance (superseded for new proposals)

`product-x-hf-v1` established the first automatic known-publisher route. It
required the source Account's exact stable ID to be mapped to the Brand with
the `official` role, the Brand's Company to own a confirmed HF namespace, and
one exact public model-metadata response for the proposed repository. Blue
verification was recorded but never qualified the account. Each exact HF repo
was one Product; a base name never expanded to a sibling or quantized repo.

V1 deliberately left every previously unknown publisher for owner review. At
that time the implementation had no deterministic HF-organization social
backlink. The dated evidence was one separately authorized request to
`/api/organizations/MiniMaxAI`; its response contained only an `error` key and
the HTTP status was not retained. That result was treated only as response-shape
evidence, not as an organization availability claim.

V1 also fixed the operational boundary still used now: public metadata only,
two-second timeouts, zero retries, three normal-cycle request slots or one
staging slot, distinct failure outcomes, and no weights or repository-file
downloads. Existing v1 proposals keep this frozen known-publisher behavior.

## V2 current policy

`product-x-hf-v2` is the current deterministic policy for turning an X model
announcement into an exact Product and source link. A rule failure leaves the
durable proposal for owner review. It never guesses a Company, enables paid
brand harvesting, downloads repository files, or treats model category as
product identity.

## Evidence accepted by the policy

Both automatic routes require one exact `https://huggingface.co/{org}/{repo}`
link in the stored Post text or recursively stored expanded entities. The
extractor's `candidate_repo_id` must equal that link. Bare model text, a guessed
repository, another host, a userinfo URL, HTTP, query/fragment data, and deeper
paths such as `/tree/main` do not qualify.

The Post's author ID must still equal the proposal's stable Account ID, and the
current Account handle must still equal both stored source-handle snapshots.
A handle change stops automation; it cannot rebind the stable account silently.

### Known publisher

The stable Account must already have the Brand's `official` role. The Brand
must be linked to the Company that owns a confirmed `HFOrg` equal to the repo
namespace. One unauthenticated exact model-metadata response must return the
same repository ID and, when `author` is present, the same namespace.

Historical `product-x-hf-v1` proposals retain this established known-publisher
route so queued work does not change meaning after deployment. Newly extracted
proposals use v2 and therefore also require the stored exact source link and
unchanged handle snapshots.

### Previously unknown publisher

All of these independent facts must agree:

1. Both the stored Post snapshot and current Account say `verifiedType` is
   exactly `Business`. `isBlueVerified` never substitutes for this rule.
2. The unresolved candidate's source-observed name, after punctuation and case
   normalization, equals either the X handle or HF namespace. This prevents an
   arbitrary candidate or Company guess.
3. The exact public model-metadata document matches the repository and owner.
4. `GET /api/organizations/{name}/socials` returns the exact namespace and its
   self-provided `socialHandles.twitter` points back to the unchanged X handle.
5. The source Post/candidate has exactly one supported category. Ambiguous
   category evidence remains review work.

Passing creates or reuses one untracked Brand, one Product for the exact model
repository, and one `PostBrandProduct` evidence edge. A Brand nickname collision,
reviewed-candidate conflict, or Product owner conflict fails closed. If the
candidate already has `reviewed_brand`, that evidence is reused rather than
overwritten. Otherwise the new Brand is recorded on the candidate with the
automatic policy and evidence reason.

No Company is fabricated. When the exact namespace already has a confirmed
`HFOrg`, its existing Company ownership must agree and can be linked to the new
Brand. Otherwise `Product.hf_org` stays null. The Brand is not added to
`config.yaml::enabled_models` and receives no harvest keywords.

The source `ModelRelease` remains connected through the proposal. Its immutable
candidate-based identity and owner fields are not rewritten, because its
`release_identity` hash includes that original owner. The candidate's
`reviewed_brand` supplies canonical resolution without creating a second
release identity. The current schema has no direct `ModelRelease.product`
column; exact linkage is represented by `proposal.source_release` plus
`proposal.resolved_product` and the source-backed `PostBrandProduct` edge.

## Why Business/gold is necessary but not sufficient

X documents a blue check as a Premium subscription signal, not identity
verification. X documents a gold check as an official organization account
through Premium Business. In TwitterAPI.io's stored advanced-search payload,
the applicable field is `author.verifiedType`; the source corpus includes
`Business` values independently of `isBlueVerified`.

The policy still does not trust Business/gold alone. It requires the stable-ID,
unchanged-handle, exact source link, exact HF model owner, and bidirectional HF
organization-social checks above.

Sources checked 2026-09-24:

- [X profile labels and checkmarks](https://help.x.com/en/rules-and-policies/profile-labels)
- [X blue-check meaning](https://help.x.com/en/managing-your-account/about-x-bluecheck)
- [Hugging Face OpenAPI document](https://huggingface.co/.well-known/openapi.json),
  including `GET /api/organizations/{name}/socials`; its response says the
  social handles are provided by the organization.
- [TwitterAPI.io advanced-search endpoint documentation](https://twitterapi.io/docs/api-reference/endpoint/advanced_search)

The bounded live observation recorded by the owner at about 06:56 UTC on
2026-09-24 was one public request to
`/api/organizations/MiniMaxAI/socials`: HTTP 200, organization `MiniMaxAI`, X
handle `MiniMax_AI`, and GitHub handle `MiniMax-AI`. It confirms that one
payload only; it does not establish coverage for other organizations.

## Request and failure contract

- All automatic checks are unauthenticated public JSON requests with a
  two-second timeout and zero retries. Payload URLs are inert data and are never
  followed.
- The normal drain permits at most three physical requests; isolated staging
  permits one. The cycle deadline is checked before every request.
- A new-publisher proposal usually needs two physical requests: exact model
  metadata, then organization socials. If the first consumes the last slot,
  its exact payload is durably cached and the next drain requests only socials.
- Outcomes remain distinct: matched, missing, private, timeout, throttled,
  malformed, error, and deferred. Timeout/throttle/error retry no earlier than
  15 minutes. Evidence conflicts remain pending for owner review.
- Reviewer decisions clear the worker claim. A stale worker cannot overwrite a
  rejection or approval.
- When the owner previously approved an X-only Product for the same source
  release, later exact HF corroboration attaches the repo to that Product. A
  conflicting Product owner, type, or existing repository fails closed instead
  of creating a duplicate or rewriting the owner's decision.

Catalog enumeration is separately launched and bounded. It is not scheduled,
does not imply release activity, and never downloads weights. Completeness is
true only when the HF listing has no continuation cursor.
