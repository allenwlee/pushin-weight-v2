---
title: "Test X Developer API coverage with fixed windows and known post IDs"
date: "2026-11-23"
category: workflow-issues
module: harvest
problem_type: workflow_issue
component: development_workflow
severity: medium
applies_when:
  - "Comparing X keyword search providers for the same brand"
  - "Checking XDev access to post fields, conversations, or a monitored list"
tags: [xdev, twitterapi, search-coverage, post-lookup, partial-errors, provider-billing]
---

# Test X Developer API coverage with fixed windows and known post IDs

## Context

The November 23, 2026 JST test checked what the project’s XDev app could return and compared one DeepSeek keyword query with TwitterAPI.io (TAPI). It exposed two ways to misread the results. A brand search can return extra IDs that add little to editorial coverage, and a successful HTTP response can contain a list or post error. The combination of a matched search and independent lookups answered questions that either test alone would have left open. [XDev endpoint measurement](../../external_vendors/xdev/research/2026-11-23-135930-official-x-api-measurement.md) · [Matched DeepSeek search](../../external_vendors/comparisons/2026-11-23-141144-deepseek-xdev-tapi-comparison.md)

## Guidance

1. Freeze the brand clause, start and end, recency ordering, and engagement cutoff before comparing providers. Send `start_time` and `end_time` with `GET /2/tweets/search/recent` on XDev. Append the corresponding Unix-second `since_time:` and `until_time:` operators to TAPI's query and set `queryType=Latest`. Verify returned timestamps, save the continuation status, and compare distinct post IDs and the content of provider-only posts. In the November 22 06:25–06:30 JST window, XDev returned 12, TAPI returned four, and three IDs overlapped. Both responses ended on the first page. Seven of the nine XDev-only IDs were similar promotions from one account. The union of 13 IDs is the observed result for that query and window. [Exact DeepSeek requests and overlap](../../external_vendors/comparisons/2026-11-23-141144-deepseek-xdev-tapi-comparison.md)
2. Check fields and relationships with known IDs. A `GET /2/tweets` lookup with `post.fields` exposed full long-form post text in `note_post.text` and a 56,576-character X Article body in `article.plain_text` on one known article. The fields represent separate content types. For thread search, use the `conversation_id` returned by lookup. An intermediate reply used as the root initially returned zero results. The corrected root returned three posts, and `in_reply_to_tweet_id:` with the known direct parent recovered the control reply. [Lookup and conversation results](../../external_vendors/xdev/research/2026-11-23-135930-official-x-api-measurement.md#endpoint-decisions)
3. Inspect errors inside successful responses and verify list access using the intended app. The configured monitoring list produced object-level not-found errors from list posts and list members. The `list:` search returned zero. Treat that combination as access unresolved for this app. An empty search cannot distinguish an unavailable list from an inaccessible one. [List access evidence](../../external_vendors/xdev/research/2026-11-23-135930-official-x-api-measurement.md#endpoint-decisions)
4. Track each attempted send, returned slots, distinct IDs, and payer balance observations. Reserve for the resources a request can return, including any expansions. The 31-send XDev batch had a $0.98 payer balance decrease. The 14-send search-and-count stage accounted for $0.60 of that balance change. The balance checks measured spend across batches. Individual endpoint prices or a production bill require separate evidence. [Credit receipts and scope](../../external_vendors/xdev/research/2026-11-23-135930-official-x-api-measurement.md#cost-and-scope)

Use these checks for a provider comparison or a specific capability probe. A routing decision still needs coverage evidence across representative brands and windows, a positive control for the intended monitoring list, and costs measured at the expected request mix.
