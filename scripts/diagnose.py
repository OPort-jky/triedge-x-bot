"""X API 側の状態確認: アカウント可視性 + 権限 + rate limit エラー時の body。手動用。

コスト: get_me 1回 (0円 or ~$0.005)、失敗時 create_tweet の403 body を露出。
"""
import os, sys, json
import tweepy
import requests
from requests_oauthlib import OAuth1

tw = tweepy.Client(
    consumer_key=os.environ["X_API_KEY"],
    consumer_secret=os.environ["X_API_SECRET"],
    access_token=os.environ["X_ACCESS_TOKEN"],
    access_token_secret=os.environ["X_ACCESS_SECRET"],
)

# 1. get_me: アカウントが suspend されてないか
print("=== [1] get_me ===")
try:
    me = tw.get_me(user_auth=True, user_fields=["public_metrics", "protected", "verified"])
    print(f"OK: @{me.data.username} id={me.data.id}")
    print(f"    followers={me.data.public_metrics.get('followers_count')}")
    print(f"    following={me.data.public_metrics.get('following_count')}")
    print(f"    tweet_count={me.data.public_metrics.get('tweet_count')}")
    print(f"    protected={me.data.protected} verified={me.data.verified}")
except Exception as e:
    print(f"FAIL: {type(e).__name__}: {e}")

# 2. 診断用の空リクエスト (create_tweet の代わりに raw HTTP で reason を取る)
#    ダミーテキストを送って403のbodyを露出させる (投稿はほぼ確実に失敗する内容にする)
print("\n=== [2] create_tweet with diagnostic text ===")
auth = OAuth1(
    os.environ["X_API_KEY"], os.environ["X_API_SECRET"],
    os.environ["X_ACCESS_TOKEN"], os.environ["X_ACCESS_SECRET"],
)
url = "https://api.x.com/2/tweets"
diagnostic_text = f"diag-{os.environ.get('GITHUB_RUN_ID', 'local')}"  # ユニーク文字列で重複回避
r = requests.post(url, json={"text": diagnostic_text}, auth=auth, timeout=15)
print(f"status={r.status_code}")
print(f"body={r.text[:600]}")

# 3. 投稿された場合は削除 (ゴミを残さない)
if r.status_code == 201:
    tid = r.json().get("data", {}).get("id")
    if tid:
        print(f"\n=== [3] cleanup: deleting diagnostic tweet {tid} ===")
        try:
            tw.delete_tweet(id=tid, user_auth=True)
            print("deleted")
        except Exception as e:
            print(f"delete failed: {e}")
