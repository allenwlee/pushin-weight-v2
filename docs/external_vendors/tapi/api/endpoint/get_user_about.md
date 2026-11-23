# Get User Profile About

Current project reference for TwitterAPI's `GET /twitter/user_about` endpoint.
It combines the provider's public schema with a value-free live response-shape
probe run on 2026-08-30. The public example is incomplete: the live success
response includes additional conditional leaves and structures that the example
omits.

- Method and path: `GET https://api.twitterapi.io/twitter/user_about`
- Authentication: `X-API-Key` header
- Query: required `userName` string
- Public reference: <https://docs.twitterapi.io/api-reference/endpoint/get_user_about>
- Live evidence: staging job `job-da9kmc8n74is738e4gpg`, exact SHA
  `c4ca6be2672458c5fac54784859dc0ec3dc38d64`
- Conditional-leaf evidence: staging job `job-da9ktc9f2nfc73fs568g`, exact SHA
  `284e1fc18307b288eae63bb977bc3cb532da56ba`
- Unavailable-variant evidence: staging job `job-da9l1j2jnfac73e6ajvg`, exact
  SHA `12f67affc56f0d67476c54028ef0dc98b9c23601`
- Identity-label long-description evidence: production smoke continuation job
  `job-daadckpf2nfc739vlfk0`, exact SHA
  `b4e411df913a72625bb14538f4efd83c709cfbfb`
- Verification override-year evidence: production continuation job
  `job-daafuqpf2nfc73a75210`, exact SHA
  `4fdbd395bca04430a716accbe3008712dfe02ea8`

The probe retained JSON paths and JSON types only. It discarded response
values, handles, account IDs, URLs, credentials, headers, and the raw payload.

## Success response schema

```json
{
  "status": "<string>",
  "msg": "<string>",
  "data": {
    "id": "<string>",
    "name": "<string>",
    "userName": "<string>",
    "createdAt": "<string>",
    "isVerified": true,
    "isBlueVerified": true,
    "protected": true,
    "profilePicture": "<string>",
    "verification_info": {
      "id": "<string>",
      "is_identity_verified": true,
      "reason": {
        "override_verified_year": 0,
        "verified_since_msec": "<numeric string>"
      }
    },
    "affiliates_highlighted_label": {
      "label": {
        "badge": {"url": "<string>"},
        "description": "<string>",
        "url": {"url": "<string>", "urlType": "<string>"},
        "userLabelDisplayType": "<string>",
        "userLabelType": "<string>"
      }
    },
    "about_profile": {
      "account_based_in": "<string>",
      "location_accurate": true,
      "created_country_accurate": true,
      "learn_more_url": "<string>",
      "affiliate_username": "<string>",
      "source": "<string>",
      "username_changes": {
        "count": "<numeric string>",
        "last_changed_at_msec": "<numeric string>"
      }
    },
    "identity_profile_labels_highlighted_label": {
      "label": {
        "badge": {"url": "<string>"},
        "description": "<string>",
        "long_description": {
          "text": "<string>",
          "entities": [
            {
              "from_index": 0,
              "to_index": 1,
              "ref": {
                "__isTimelineReferenceObject": "<string>",
                "__typename": "<string>",
                "screen_name": "<string>",
                "user_results": {}
              }
            }
          ]
        },
        "url": {"url": "<string>", "urlType": "<string>"},
        "userLabelDisplayType": "<string>",
        "userLabelType": "<string>"
      }
    }
  }
}
```

Optional objects or leaves may be absent, null, or empty. The live probe saw
both highlighted-label wrappers as empty objects; the nested label shapes above
come from the provider's public schema and remain valid conditional leaves.
The production population later observed `long_description` on an identity
label. PushinWeight stores its account-valued `text` leaf as
`Account.identity_profile_label_long_description`. It strictly validates the
entity annotation envelope and types, but does not persist entity offsets or
the nested `user_results` presentation cache; those are rich-text rendering
metadata rather than Account facts, and retaining the opaque object would
violate the no-raw-response contract.

The endpoint also returns a success envelope whose `data` is an unavailable
variant instead of a profile:

```json
{
  "status": "<string>",
  "msg": "<string>",
  "data": {
    "unavailable": true,
    "unavailableReason": "<string>"
  }
}
```

This variant has no `data.id`. PushinWeight therefore permits it to update only
`unavailable`, `unavailable_reason`, and `account_based_in_fetched_at` on the
originally selected Account, and only while that row still owns the exact
case-insensitive handle used for the request. It cannot update profile facts.

## Live additions missing from the public example

| JSON path | Live JSON type | PushinWeight destination |
| --- | --- | --- |
| `data.isVerified` | boolean | existing `Account.verified` |
| `data.profilePicture` | string | existing `Account.profile_picture` |
| `data.verification_info.id` | string | `Account.verification_info_id` |
| `data.verification_info.is_identity_verified` | boolean | `Account.verification_info_is_identity_verified` |
| `data.verification_info.reason.override_verified_year` | number | `Account.verification_info_reason_override_verified_year`, parsed as a validated year |
| `data.verification_info.reason.verified_since_msec` | string | `Account.verification_info_reason_verified_since_msec`, parsed as a nonnegative bigint |
| `data.unavailable` | boolean | `Account.unavailable` |
| `data.unavailableReason` | string | `Account.unavailable_reason` |
| `data.about_profile.created_country_accurate` | boolean | `Account.created_country_accurate` |
| `data.about_profile.username_changes.last_changed_at_msec` | string | `Account.username_changes_last_changed_at_msec`, parsed as a nonnegative bigint |
| `data.identity_profile_labels_highlighted_label.label.long_description.text` | string | `Account.identity_profile_label_long_description` |

`isVerified` and `profilePicture` deliberately reuse fields populated by fresh
post-author payloads. All account-valued additions receive nullable typed
columns. No raw response column is used.
