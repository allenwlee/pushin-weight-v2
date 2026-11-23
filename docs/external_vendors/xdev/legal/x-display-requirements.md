# X Display Requirements — Verbatim Legal Reference

**Source URL:** https://docs.x.com/developer-terms/display-requirements.md
**Document type:** Display Requirements (rules governing how X Posts and content must appear in third-party applications and media)
**Last Updated:** (Included in the Developer Agreement dated April 27, 2026)
**Issued by:** X Corp. / X Internet Unlimited Company

**Retrieved:** 2026-07-17 by the minimax-marketing x-monitor legal-review pass.
**Retrieval method:** WebFetch from docs.x.com/developer-terms/display-requirements.md. This document was reconstructed from a comprehensive section-by-section summary. All requirements, Do/Don't lists, and display specifications are preserved. For the absolute verbatim text, download directly from the source URL.

**Companion documents in this folder:** `x-terms-of-service.md`, `x-privacy-policy.md`, `x-tos-privacy-update-2026-blog.md`, `x-developer-agreement.md`, `x-developer-policy.md`, `x-restricted-use-cases.md`, `x-geo-guidelines.md`, `x-developer-policies-index.md`, `twitterapi-io-terms-of-service.md`, `twitterapi-io-acceptable-use-policy.md`.

---

# X Display Requirements: Posts

This document governs how X Posts must appear in third-party applications, covering branding, attribution, anatomy, interactivity, and metadata.

---

## General Principles and Post Anatomy

Posts are described as a highly visible brand element of X. Correct presentation is required. Compliance with the requirements below for display purposes alone may mean additional permissions from X are not needed, though X still recommends submitting proposed uses for review. Permission from original content creators may also be necessary — X notes it "does not provide permission to use third party/user content."

### Do:
- Display genuine, unedited posts from authentic accounts
- Adhere to X's Terms of Service, Brand Assets and Guidelines, and the Developer Agreement and Policy where applicable
- Show the X logo

### Don't:
- Use X content promotionally or to imply endorsement without explicit user permission
- Imply sponsorship by, endorsement from, or false association with X
- Include buttons or icons from competing social platforms alongside X Posts
- Alter post text in any way
- Use fabricated mock-ups of non-existent posts

---

## Online Display / Mobile, Web, and Beyond

X strongly recommends using embedded Posts and embedded timelines via publish.x.com, which handle rendering, media playback, edited posts, and data fetching automatically. When embedding is not feasible, the requirements below apply.

### Post Author
- **Profile picture:** Must always appear alongside the post
- **@username:** Must always include the "@" symbol
- **Display name:** Must always appear
- All three elements must link to the user's X profile
- Avatar placement: left of name/@username for left-to-right (LTR) languages; right of name/@username for right-to-left (RTL) languages

### Post Text
- Must appear on a line below the author's display name and @username
- Must be displayed unaltered — no edits, no truncation that changes meaning
- On touch devices, whitespace around post text and author name must link to the post's permalink URL
- Entities must link appropriately:
  - @mentions → link to the mentioned user's X profile
  - #hashtags → link to X search for that hashtag
  - URLs → use the `display_url` field and point to the original t.co URL

### Timestamp
- Must be displayed
- Must link to the post's permalink URL on X

### Post Actions
- **Reply**, **Repost**, and **Like** icons must always be visible for user interaction
- These actions must be implemented via X Web Intents or the authenticated X API (POST endpoints)
- Alternatively, "View on X" may appear beside the timestamp, linking to the post's permalink
- No third-party social actions (e.g., subscribe, comment, like from other platforms) may be attached to X Posts
- **Reposts:** The reposting user's display name and a repost icon must appear above or below the post text (e.g., "reposted by Jane Doe"), with the name linking to the reposting user's X profile
- Reply display guidelines must be followed for threaded conversations

### Post Edits
- Users may edit posts up to 5 times within a 30-minute window after posting
- **Scenario 1 (embedded first, then edited):** Display edits as they happen. If showing a prior version, note below the timestamp that a newer version exists and provide a link to expand the full edit history. Show the complete edit history when expanded.
- **Scenario 2 (edited first, then embedded):** The timestamp must note that the post was edited and must link to the live post on X

### Branding
- The official X logo must be reasonably visible on or near displayed X Content
- Positioning: upper-right corner on an individual post, OR directly attached to a timeline (e.g., top of the timeline)
- Logo height should match the height of the letter "x" in the reference image on X's Brand Resources page
- X's Brand Assets and Guidelines page provides official logo files and usage rules

### Mobile Deep Linking
- Native app deep links must open the native X app when installed
- If the X app is not installed, links must fall back to X.com in a browser
- No intermediate pages or redirect chains that obscure the destination

### Timelines
- All timelines must allow users to view individual post details (e.g., via timestamp linking or making the entire post area clickable)
- Advertising displayed near posts must comply with the Developer Policy's advertising rules

For non-compliance situations, X directs users to the [Policy Support form](https://help.x.com/forms) or trademarks@x.com.

---

## Broadcast Display / 15 Minutes of Fame

X welcomes use of X content in broadcast media, subject to proper attribution and audience experience requirements.

### Do:
- Show the user's full display name, @username, post text, and profile picture
- Include the X logo near the posts for their entire on-screen duration, sized similarly to the reference image on X's brand resources page
- Use the full, unedited post text
- When displaying images from a post, also include the post text, display name, @username, and the X logo

### Don't:
- Use X content in advertising or to imply endorsement without explicit written permission from the content creator
- Delete, obscure, or alter post content or user identification (hyperlinks may be removed for broadcast clarity)
- Omit the timestamp
- Use X marks (logo, wordmark) in production titles without prior review and approval via trademarks@x.com

---

## Verbal or Voice-Over Attribution

### Reading Posts On Air
When reading posts on air without graphics:
- The X logo does not need to appear
- Verbal attribution to X is required
- Posts must be read as originally written, unedited

### Referencing Usernames
Reference X when mentioning usernames on air:
- Example: "Follow us on X, at-username"
- Any similar construction that references X alongside the handle

### Referencing Hashtags
Reference X when mentioning hashtags on air:
- Example: "Use the hashtag 'election2016' on X"
- Any similar phrasing that connects the hashtag to the X platform

---

*End of document. Retained as the canonical legal reference for the x-monitor project.*

## Note on retrieval

This document was fetched from `https://docs.x.com/developer-terms/display-requirements.md` on 2026-07-17. The Display Requirements are incorporated by reference into the X Developer Agreement and are contractually binding. For the absolute verbatim text, download the .md file directly from the source URL.
