# TwitterAPI.io docs (reference library, mirrored 2026-07-30)

Reference copy of <https://docs.twitterapi.io>. Each file is a literal
download of the corresponding upstream `.md` URL — no LLM rewriting, no
extraction. The docs site publishes per-page `.md` URLs specifically for
machine consumption (see `llms.txt` at the upstream root).

**To refresh this library:**

```bash
curl -sSf https://docs.twitterapi.io/llms.txt | grep -oE "(https://docs\.twitterapi\.io/[^\)]+\.md)" | sed "s/\\_/_/g" | sort -u | while read url; do
  curl -sSf -o "endpoint/$(basename "$url")" "$url"
done
```

## Top-level pages

| File | Title | Description |
|---|---|---|
| [introduction.md](introduction.md) | Introduction | API overview and base URL. |
| [authentication.md](authentication.md) | Authentication | Learn how to authenticate your API requests using API keys. |
| [quickstart.md](quickstart.md) | Quickstart | Quickstart guide for getting started. |

## Endpoint reference

All endpoint specs are OpenAPI 3.0.1 YAML in code blocks, prefixed by a one-line
method+path header (e.g. `GET /twitter/tweet/advanced_search`). All require
`ApiKeyAuth` via the `X-API-Key` header.

| File | Title | Description |
|---|---|---|
| [add_user_to_monitor_tweet.md](endpoint/add_user_to_monitor_tweet.md) | Add  a twitter user to monitor his tweets | Add a user to monitor real-time tweets.Monitor tweets from specified accounts, including directly sent tweets, quoted tweets, reply tweets, and retweeted tweets. Please ref:https:/ |
| [add_webhook_rule.md](endpoint/add_webhook_rule.md) | Add Webhook/Websocket Tweet Filter Rule | Add a tweet filter rule. Default rule is not activated.You must call update_rule to activate the rule. |
| [authentication.md](endpoint/authentication.md) | Authentication | Learn how to authenticate your API requests using API keys |
| [batch_get_user_by_userids.md](endpoint/batch_get_user_by_userids.md) | Batch Get User Info By UserIds | Batch get user info by user ids. Pricing: |
| [bookmark_tweet_v2.md](endpoint/bookmark_tweet_v2.md) | Bookmark Tweet | Bookmark a tweet. You must set the login_cookie. You can get the login_cookie from /twitter/user_login_v2. Trial operation price: $0.002 per call. |
| [bookmarks_v2.md](endpoint/bookmarks_v2.md) | Get Bookmarks | Get the bookmarks list of the logged-in user. You must set the login_cookie. You can get the login_cookie from /twitter/user_login_v2. Returns tweets in the same format as other tw |
| [check_follow_relationship.md](endpoint/check_follow_relationship.md) | Check Follow Relationship | Check if the user is following/followed by the target user. Trial operation price: 100 credits per call. |
| [create_community_v2.md](endpoint/create_community_v2.md) | Create Community V2 | Create a community.You must set the login_cookies.You can get the login_cookies from /twitter/user_login_v2.Trial operation price: $0.003 per call.  |
| [create_tweet_v2.md](endpoint/create_tweet_v2.md) | Create/Reply tweet v2 | Create a tweet.You must set the login_cookie.You can get the login_cookie from /twitter/user_login_v2.Trial operation price: $0.003 per call.  |
| [delete_community_v2.md](endpoint/delete_community_v2.md) | Delete Community V2 | Delete a community.You must set the login_cookie.You can get the login_cookie from /twitter/user_login_v2.Trial operation price: $0.003 per call.  |
| [delete_tweet_v2.md](endpoint/delete_tweet_v2.md) | Delete Tweet | Delete a tweet.You must set the login_cookie.You can get the login_cookie from /twitter/user_login_v2.Trial operation price: $0.002 per call.  |
| [delete_webhook_rule.md](endpoint/delete_webhook_rule.md) | Delete Webhook/Websocket Tweet Filter Rule | Delete a tweet filter rule. You must set all parameters. |
| [follow_user_v2.md](endpoint/follow_user_v2.md) | Follow User | Follow a user.You must set the login_cookie.You can get the login_cookie from /twitter/user_login_v2.Trial operation price: $0.002 per call.  |
| [get_all_community_tweets.md](endpoint/get_all_community_tweets.md) | Search Tweets From All Community  | get tweets from all communities,each page returns up to 20 tweets. Use cursor for pagination. |
| [get_article.md](endpoint/get_article.md) | Get Article | get article by tweet id. cost 100 credit per article |
| [get_community_by_id.md](endpoint/get_community_by_id.md) | Get Community Info By Id | Get community info by community id. Price: 20 credits per call. Note: This API is a bit slow, we are still optimizing it. |
| [get_community_members.md](endpoint/get_community_members.md) | Get Community Members | Get members of a community. Page size is 20. |
| [get_community_moderators.md](endpoint/get_community_moderators.md) | Get Community Moderators | Get moderators of a community. Page size is 20. |
| [get_community_tweets.md](endpoint/get_community_tweets.md) | Get Community Tweets | Get tweets of a community. Page size is 20. Order by creation time desc.  |
| [get_list_followers.md](endpoint/get_list_followers.md) | Get List Followers | Get followers of a list. Page size is 20. |
| [get_list_members.md](endpoint/get_list_members.md) | Get List Members | Get members of a list. Page size is 20. |
| [get_my_info.md](endpoint/get_my_info.md) | Get My Account Info | Get my info |
| [get_space_detail.md](endpoint/get_space_detail.md) | Get Space Detail | Get spaces detail by space id |
| [get_trends.md](endpoint/get_trends.md) | Get Trends | Get trends by woeid |
| [get_tweet_by_ids.md](endpoint/get_tweet_by_ids.md) | Get Tweets by IDs | get tweet by tweet ids |
| [get_tweet_quote.md](endpoint/get_tweet_quote.md) | Get Tweet Quotations | get tweet quotes by tweet id.Each page returns exactly 20 quotes. Use cursor for pagination. Order by quote time desc |
| [get_tweet_replies_v2.md](endpoint/get_tweet_replies_v2.md) | Get Tweet Replies V2 | Get tweet replies by tweet id (V2). Each page returns up to 20 replies. Use cursor for pagination. Supports sorting by Relevance, Latest, or Likes. |
| [get_tweet_reply.md](endpoint/get_tweet_reply.md) | Get Tweet Replies | get tweet replies by tweet id.Each page returns up to 20 replies(Sometimes less than 20,because we will filter out ads or other not  tweets). Use cursor for pagination. Order by re |
| [get_tweet_retweeter.md](endpoint/get_tweet_retweeter.md) | Get Tweet Retweeters | get tweet retweeters by tweet id.Each page returns about 100 retweeters. Use cursor for pagination. Order by retweet time desc |
| [get_tweet_thread_context.md](endpoint/get_tweet_thread_context.md) | Get Tweet Thread Context | Get the thread context of a tweet.Suppose a tweet thread consists of t1, t2 (replying to t1), t3 (replying to t2), and t4, t5, t6 (all replying to t3). If we provide an API where y |
| [get_user_about.md](endpoint/get_user_about.md) | Get User Profile About | Get user profile about by screen name |
| [get_user_by_username.md](endpoint/get_user_by_username.md) | Get User Info | Get user info by screen name |
| [get_user_followers_ids.md](endpoint/get_user_followers_ids.md) | Get User Followers IDs (Bulk) | Get a user's follower IDs in bulk — **lightweight, IDs only, no profile metadata**. Designed for large-scale follower-graph collection where you join IDs against your own data ware |
| [get_user_followers.md](endpoint/get_user_followers.md) | Get User Followers | Get user followers (with full profile metadata) in reverse chronological order (newest first). Sorted by follow date — most recent followers appear on the first page. Use `cursor`  |
| [get_user_followings.md](endpoint/get_user_followings.md) | Get User Followings | Get user followings (with full profile metadata). Sorted by follow date — most recent followings appear on the first page. Use `cursor` for pagination. |
| [get_user_last_tweets.md](endpoint/get_user_last_tweets.md) | Get User Last Tweets | Retrieve tweets by user name.Sort by created_at. Results are paginated, with each page returning up to 20 tweets.If you only need to fetch the latest tweets from a single user very |
| [get_user_mention.md](endpoint/get_user_mention.md) | Get User Mentions | get tweet mentions by user screen name.Each page returns exactly 20 mentions. Use cursor for pagination. Order by mention time desc |
| [get_user_timeline.md](endpoint/get_user_timeline.md) | Get User TimeLine | Retrieve tweets by user id.Sort by created_at. Results are paginated, with each page returning up to 20 tweets.The content you see is in the same order as the tweets on the user's  |
| [get_user_to_monitor_tweet.md](endpoint/get_user_to_monitor_tweet.md) | Get Users to Monitor Tweet | Get the list of users being monitored for real-time tweets. Returns all users that have been added for tweet monitoring. Please ref:https://twitterapi.io/twitter-stream |
| [get_user_verified_followers.md](endpoint/get_user_verified_followers.md) | Get User Verified Followers | Get user verified followers in reverse chronological order (newest first). Returns exactly 20 verified followers per page, sorted by follow date. Most recent followers appear on th |
| [get_webhook_rules.md](endpoint/get_webhook_rules.md) | Get ALL test Webhook/Websocket Tweet Filter Rules | Get all tweet filter rules.Rule can be used in webhook and websocket.You can also modify the rule in our web page. |
| [introduction.md](endpoint/introduction.md) | Introduction | twitterapi.io docs.The best third-party Twitter API: reliable, high-performance, supports high QPS, and cost-effective. |
| [join_community_v2.md](endpoint/join_community_v2.md) | Join Community v2 | Join a community.You must set the login_cookie.You can get the login_cookie from /twitter/user_login_v2.Trial operation price: $0.003 per call.  |
| [leave_community_v2.md](endpoint/leave_community_v2.md) | Leave Community V2  | Leave a community.You must set the login_cookie.You can get the login_cookie from /twitter/user_login_v2.Trial operation price: $0.003 per call.  |
| [like_tweet_v2.md](endpoint/like_tweet_v2.md) | Like Tweet | Like a tweet.You must set the login_cookie.You can get the login_cookie from /twitter/user_login_v2.Trial operation price: $0.002 per call.  |
| [list_timeline.md](endpoint/list_timeline.md) | Get List Tweet TimeLine | Get timeline tweets  from list. Use cursor for pagination. |
| [remove_user_to_monitor_tweet.md](endpoint/remove_user_to_monitor_tweet.md) | Remove a user from  monitor list | Remove a user from monitor real-time tweets.Please ref:https://twitterapi.io/twitter-stream |
| [retweet_tweet_v2.md](endpoint/retweet_tweet_v2.md) | Retweet Tweet  | Retweet a tweet.You must set the login_cookie.You can get the login_cookie from /twitter/user_login_v2.Trial operation price: $0.002 per call.  |
| [search_user.md](endpoint/search_user.md) | Search user by keyword | Search user by keyword |
| [send_dm_v2.md](endpoint/send_dm_v2.md) | Send DM V2 | Send a direct message to a user.You must set the login_cookie..You can get the login_cookie from /twitter/user_login_v2.You can only send DMs to those who have enabled DMs. Sometim |
| [tweet_advanced_search.md](endpoint/tweet_advanced_search.md) | Advanced Search | Advanced search for tweets.Each page returns up to 20 replies(Sometimes less than 20,because we will filter out ads or other not  tweets).    |
| [unbookmark_tweet_v2.md](endpoint/unbookmark_tweet_v2.md) | Unbookmark Tweet | Remove a tweet from bookmarks. You must set the login_cookie. You can get the login_cookie from /twitter/user_login_v2. Trial operation price: $0.002 per call. |
| [unfollow_user_v2.md](endpoint/unfollow_user_v2.md) | Unfollow User | Unfollow a user.You must set the login_cookie.You can get the login_cookie from /twitter/user_login_v2.Trial operation price: $0.002 per call.  |
| [unlike_tweet_v2.md](endpoint/unlike_tweet_v2.md) | Unlike Tweet | Unlike a tweet.You must set the login_cookie.You can get the login_cookie from /twitter/user_login_v2.Trial operation price: $0.002 per call.  |
| [update_avatar_v2.md](endpoint/update_avatar_v2.md) | Update Avatar | Update your Twitter avatar/profile picture. You must set the login_cookie. You can get the login_cookie from /twitter/user_login_v2. Trial operation price: $0.003 per call. |
| [update_banner_v2.md](endpoint/update_banner_v2.md) | Update Banner | Update your Twitter banner/header image. You must set the login_cookie. You can get the login_cookie from /twitter/user_login_v2. Trial operation price: $0.003 per call. |
| [update_profile_v2.md](endpoint/update_profile_v2.md) | Update Profile | Update your Twitter profile information. You must set the login_cookie. You can get the login_cookie from /twitter/user_login_v2. Trial operation price: $0.003 per call. |
| [update_webhook_rule.md](endpoint/update_webhook_rule.md) | Update Webhook/Websocket Tweet Filter Rule | Update a tweet filter rule. You must set all parameters. |
| [upload_media_v2.md](endpoint/upload_media_v2.md) | Upload media | Upload media to twitter.You must set the login_cookie.You can get the login_cookie from /twitter/user_login_v2.Trial operation price: $0.003 per call.  |
| [user_login_v2.md](endpoint/user_login_v2.md) | Log in | Log in directly using your email, username, password, and 2FA secret key. And obtain the Login_cookie,  to post tweets, etc. Please note that the Login_cookie obtained through logi |

## Supplementary research

Local-scope notes this project's agents have added, not from the upstream docs site:

| File | Title | Description |
|---|---|---|
| [rate-limit-ux.md](rate-limit-ux.md) | Rate Limit & User Experience | What the docs actually say about QPS, what 30-day community research found, and what the 29 dead-lettered handles in Phase 2 reconciliation likely were. |
