# Get User Profile About

Current project reference for TwitterAPI's `GET /twitter/user_about` endpoint.
It combines the provider's public schema with a value-free live response-shape
probe run on 2026-08-30. The public example is incomplete: the live success
response includes seven leaves that the example omits.

- Method and path: `GET https://api.twitterapi.io/twitter/user_about`
- Authentication: `X-API-Key` header
- Query: required `userName` string
- Public reference: <https://docs.twitterapi.io/api-reference/endpoint/get_user_about>
- Live evidence: staging job `job-da9kmc8n74is738e4gpg`, exact SHA
  `c4ca6be2672458c5fac54784859dc0ec3dc38d64`
- Conditional-leaf evidence: staging job `job-da9ktc9f2nfc73fs568g`, exact SHA
  `284e1fc18307b288eae63bb977bc3cb532da56ba`

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

## Live additions missing from the public example

| JSON path | Live JSON type | PushinWeight destination |
| --- | --- | --- |
| `data.isVerified` | boolean | existing `Account.verified` |
| `data.profilePicture` | string | existing `Account.profile_picture` |
| `data.verification_info.id` | string | `Account.verification_info_id` |
| `data.verification_info.is_identity_verified` | boolean | `Account.verification_info_is_identity_verified` |
| `data.verification_info.reason.verified_since_msec` | string | `Account.verification_info_reason_verified_since_msec`, parsed as a nonnegative bigint |
| `data.about_profile.created_country_accurate` | boolean | `Account.created_country_accurate` |
| `data.about_profile.username_changes.last_changed_at_msec` | string | `Account.username_changes_last_changed_at_msec`, parsed as a nonnegative bigint |

`isVerified` and `profilePicture` deliberately reuse fields populated by fresh
post-author payloads. The other five leaves receive nullable typed columns. No
raw response column is used.
