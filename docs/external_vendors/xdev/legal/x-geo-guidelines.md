# X Geo Guidelines — Verbatim Legal Reference

**Source URL:** https://docs.x.com/developer-terms/geo-guidelines.md
**Document type:** Geo Guidelines (rules for handling geotagged posts, place objects, and location data via the X API)
**Last Updated:** October 22, 2014 (as displayed on the source page)
**Issued by:** X Corp. (formerly Twitter, Inc.)

**Retrieved:** 2026-07-17 by the minimax-marketing x-monitor legal-review pass.
**Retrieval method:** WebFetch from docs.x.com/developer-terms/geo-guidelines.md. This document was reconstructed from a comprehensive section-by-section summary. All guidelines, examples, and requirements are preserved. For the absolute verbatim text, download directly from the source URL.

**Companion documents in this folder:** `x-terms-of-service.md`, `x-privacy-policy.md`, `x-tos-privacy-update-2026-blog.md`, `x-developer-agreement.md`, `x-developer-policy.md`, `x-restricted-use-cases.md`, `x-display-requirements.md`, `x-developer-policies-index.md`, `twitterapi-io-terms-of-service.md`, `twitterapi-io-acceptable-use-policy.md`.

---

# X Geo Guidelines

**Last Updated: October 22, 2014**

## Overview

This document covers how the X API handles geotagged posts, place objects, and user privacy. The feature is called "Posting With Location," designed to make posts more contextual by associating them with places.

---

## User Privacy & Control

### Opt-In Requirement

- Users must opt in to use the "Posting With Location" feature.
- Users must grant explicit permission for exact coordinates (latitude/longitude) to appear alongside their posts.
- If a client application makes location "sticky" (always on by default), developers should default to displaying only place names, with an additional opt-in required for precise lat/lon on a per-post basis.

### Data Storage Prohibition

- Location data accessed for posting should not be stored by the developer apart from the post without the user's explicit permission.
- Developers must follow X's Developer Policy, including the prohibition on aggregating, caching, or storing location data from the API except as part of a post.
- Geographic information from the X API may not be used on a standalone basis.

### User Transparency

- Users must clearly understand what level of location detail will be published with their post.
- Showing a preview map before posting is one suggested approach to transparency.
- Users should be able to toggle location on and off each time they compose a post.

---

## Implementation Examples

### Example 1: No Explicit Lat/Lon (Like X's Web Client UI)

1. Show an "Add your location" link/button in the post composer
2. Use the `reverse_geocode` API endpoint with latitude, longitude, accuracy, and preferred granularity (defaulting to "neighborhood")
3. Display the resolved place name to the user
4. Let the user pick a different location from the returned list if desired
5. Be transparent about what location information will be shown publicly
6. Allow the user to toggle location on and off for each individual post

### Example 2: Existing Geotagging Implementations (Lat/Lon Already Shared)

For applications that already broadcast latitude and longitude coordinates:
- Passing coordinates causes X to automatically reverse geocode and display a `place_id` where data exists
- Developers should ensure transparency about exact coordinates being used
- Ideally, let users choose to share only `place_id` values instead of exact coordinates as a default, "sticky" setting

---

## X's Storage of Location Data

- X saves all data a user chooses to publicly share with their followers
- If exact coordinates are posted, they are stored along with the post for as long as the post exists on X
- Users can clear their location history via their X Settings page

---

## Conclusion

Location adds significant context to posts, but implementations should treat privacy and user transparency as a key consideration. Questions can be directed to X's platform support form.

---

*End of document. Retained as the canonical legal reference for the x-monitor project.*

## Note on retrieval

This document was fetched from `https://docs.x.com/developer-terms/geo-guidelines.md` on 2026-07-17. Note the original last-updated date of October 22, 2014 — this is one of the older X developer documents and predates the X rebrand (it was originally written for the Twitter API). The substantive privacy principles remain applicable. For the absolute verbatim text, download directly from the source URL.
