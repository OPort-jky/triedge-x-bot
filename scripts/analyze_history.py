"""@TriEdgeApp の直近ツイート最大100件を取得しログ出力。手動実行 (workflow_dispatch) 用。

コスト: N tweet × $0.005 (pay-per-use)。100 件でも $0.50 で済む一回限りの分析用。
"""
import os, json, tweepy

tw = tweepy.Client(
    consumer_key=os.environ["X_API_KEY"],
    consumer_secret=os.environ["X_API_SECRET"],
    access_token=os.environ["X_ACCESS_TOKEN"],
    access_token_secret=os.environ["X_ACCESS_SECRET"],
)

me = tw.get_me(user_auth=True)
print(f"account: @{me.data.username} id={me.data.id}")

resp = tw.get_users_tweets(
    id=me.data.id,
    max_results=100,
    tweet_fields=["created_at", "public_metrics", "non_public_metrics"],
    exclude=["retweets", "replies"],
    user_auth=True,
)
tweets = resp.data or []
print(f"fetched: {len(tweets)} tweets\n")

for i, t in enumerate(tweets, 1):
    pm = t.public_metrics or {}
    npm = t.non_public_metrics or {}
    print(f"--- [{i}] {t.created_at} id={t.id} ---")
    print(f"len={len(t.text)} likes={pm.get('like_count')} rt={pm.get('retweet_count')} reply={pm.get('reply_count')} imp={npm.get('impression_count')}")
    print(t.text)
    print()

# 一括JSONも末尾に出す (機械可読)
data = [{
    "id": str(t.id),
    "created_at": str(t.created_at),
    "text": t.text,
    "public_metrics": t.public_metrics,
    "non_public_metrics": t.non_public_metrics,
} for t in tweets]
print("---JSON---")
print(json.dumps(data, ensure_ascii=False, indent=2))
