"""直近10ツイートのメトリクス取得→history.jsonl更新。1日1回のcronから。

コスト管理: 10ツイート×$0.005×30日 = $1.50/月。ここを増やすとリニアに伸びる。
"""
import os, json, pathlib, datetime
import tweepy

ROOT = pathlib.Path(__file__).resolve().parent.parent
HIST = ROOT / "state/history.jsonl"
LOOKBACK = 10  # ponytail: 直近10件のみ測定 (古い投稿はスコア変動小), 増やす場合は $/月 も増える


def main() -> None:
    if not HIST.exists():
        print("no history yet, skip")
        return

    entries = [json.loads(l) for l in HIST.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not entries:
        print("empty history")
        return

    targets = [e for e in entries[-LOOKBACK:] if e.get("tweet_id")]
    if not targets:
        print("nothing to measure")
        return

    tw = tweepy.Client(
        consumer_key=os.environ["X_API_KEY"],
        consumer_secret=os.environ["X_API_SECRET"],
        access_token=os.environ["X_ACCESS_TOKEN"],
        access_token_secret=os.environ["X_ACCESS_SECRET"],
    )
    resp = tw.get_tweets(
        ids=[str(e["tweet_id"]) for e in targets],
        tweet_fields=["public_metrics", "non_public_metrics"],
        user_auth=True,
    )
    fetched = {str(t.id): t for t in (resp.data or [])}
    now = datetime.datetime.now(datetime.UTC).isoformat()

    updated = 0
    for e in entries:
        tid = str(e.get("tweet_id", ""))
        t = fetched.get(tid)
        if not t: continue
        pm = t.public_metrics or {}
        npm = t.non_public_metrics or {}
        e["likes"] = pm.get("like_count")
        e["retweets"] = pm.get("retweet_count")
        e["replies"] = pm.get("reply_count")
        e["impressions"] = npm.get("impression_count")
        e["measured_at"] = now
        updated += 1

    with HIST.open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    print(f"metrics updated for {updated} tweets")


if __name__ == "__main__":
    main()
