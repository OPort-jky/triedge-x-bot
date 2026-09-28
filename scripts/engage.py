"""ターゲット handle に対する1日3件の auto-like。auto-reply はしない (ToS 準拠)。

構成:
- state/target_list.txt から handle を読む (1行1つ・# はコメント)
- 直近20時間以内に like 済みの target はスキップ (同日重複回避)
- ローテ (shuffle) で最大 3 件選び、各 handle の直近ツイート 1 件を like
- state/engage_log.jsonl に記録 (ToS 監査用)

コスト: Free tier read 枠は約 100/月。3件 x 30日 = 90 read/月。fetch_metrics.py 併用で
枠を超える恐れがあるため、稼働1週間は state/engage_log.jsonl の量を必ずモニタする。
"""
import os, json, pathlib, datetime, zoneinfo, random
import tweepy

ROOT = pathlib.Path(__file__).resolve().parent.parent
JST = zoneinfo.ZoneInfo("Asia/Tokyo")
TARGETS = ROOT / "state/target_list.txt"
LOG = ROOT / "state/engage_log.jsonl"
DAILY_LIMIT = 3  # ponytail: 1日3件固定・up にする場合は Free tier read 枠を先に確認


def load_targets() -> list[str]:
    """target_list.txt から handle 一覧を返す。@ は除去し、# コメント・空行は無視。"""
    if not TARGETS.exists():
        return []
    lines = [l.strip() for l in TARGETS.read_text(encoding="utf-8").splitlines()]
    return [l.lstrip("@") for l in lines if l and not l.startswith("#")]


def recent_liked_targets(hours: int = 20) -> set:
    """直近 hours 時間以内に like した target 集合を返す (同日重複回避用)。"""
    if not LOG.exists():
        return set()
    cutoff = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=hours)
    seen = set()
    for line in LOG.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            e = json.loads(line)
            ts = datetime.datetime.fromisoformat(e["ts"].replace("Z", "+00:00"))
            if ts >= cutoff:
                seen.add(e["target"])
        except Exception:
            continue
    return seen


def pick(targets: list[str], count: int) -> list[str]:
    """like 済みでない target を shuffle して先頭 count 件返す。"""
    liked = recent_liked_targets()
    pool = [t for t in targets if t not in liked]
    random.shuffle(pool)
    return pool[:count]


def log_engagement(target: str, tweet_id: str, text: str) -> None:
    now = datetime.datetime.now(datetime.UTC).isoformat()
    entry = {"ts": now, "target": target, "tweet_id": tweet_id, "text_preview": (text or "")[:80]}
    LOG.parent.mkdir(exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def main() -> None:
    targets = load_targets()
    if not targets:
        print("[engage] target_list.txt empty or missing, skip")
        return

    tw = tweepy.Client(
        consumer_key=os.environ["X_API_KEY"],
        consumer_secret=os.environ["X_API_SECRET"],
        access_token=os.environ["X_ACCESS_TOKEN"],
        access_token_secret=os.environ["X_ACCESS_SECRET"],
    )

    picked = pick(targets, DAILY_LIMIT)
    if not picked:
        print(f"[engage] all {len(targets)} targets liked recently, skip")
        return

    print(f"[engage] picked {picked} from {len(targets)} targets")
    likes = 0

    for target in picked:
        try:
            # handle → user_id
            u = tw.get_user(username=target, user_auth=True)
            if not u or not u.data:
                print(f"[engage] @{target} not found, skip")
                continue
            user_id = u.data.id

            # 最新ツイ 1 件 (RT/reply 除外)
            resp = tw.get_users_tweets(
                id=user_id, max_results=5,
                exclude=["retweets", "replies"], user_auth=True,
            )
            if not resp or not resp.data:
                print(f"[engage] @{target} no recent tweets, skip")
                continue
            t = resp.data[0]

            # like (X の rate limit: user context POST /2/users/:id/likes = 50/24h・十分余裕)
            tw.like(tweet_id=t.id, user_auth=True)
            log_engagement(target, str(t.id), t.text or "")
            print(f"[engage] liked @{target} tweet={t.id}: {(t.text or '')[:60]}…")
            likes += 1

        except Exception as e:
            # 個別 target の失敗は他に影響させない (rate limit / private / suspended 等)
            print(f"[engage] @{target} error: {e.__class__.__name__}: {e}")
            continue

    print(f"[engage] done: {likes}/{len(picked)} likes")


if __name__ == "__main__":
    main()
