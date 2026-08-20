"""投稿1件生成→Xに投稿→history.jsonl追記。3投稿/日のcronから呼ばれる。"""
import os, json, pathlib, datetime, zoneinfo
import anthropic
import tweepy

ROOT = pathlib.Path(__file__).resolve().parent.parent
JST = zoneinfo.ZoneInfo("Asia/Tokyo")


def slot_of(hour: int) -> str:
    if 5 <= hour < 11:  return "morning"
    if 11 <= hour < 15: return "noon"
    return "night"


def read(p: pathlib.Path, default: str = "") -> str:
    return p.read_text(encoding="utf-8") if p.exists() else default


def recent_texts(history: pathlib.Path, n: int = 15) -> str:
    if not history.exists(): return "（初投稿）"
    lines = [l for l in history.read_text(encoding="utf-8").splitlines() if l.strip()]
    items = [json.loads(l) for l in lines[-n:]]
    return "\n".join(f"- {e['text']}" for e in items) or "（初投稿）"


def generate(system: str, user: str) -> str:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    text = msg.content[0].text.strip()
    # LLM がたまに「」や引用符で囲むのを剥がす
    for pair in [('"', '"'), ('「', '」'), ("'", "'")]:
        if text.startswith(pair[0]) and text.endswith(pair[1]):
            text = text[1:-1].strip()
    return text


def post_x(text: str) -> str:
    tw = tweepy.Client(
        consumer_key=os.environ["X_API_KEY"],
        consumer_secret=os.environ["X_API_SECRET"],
        access_token=os.environ["X_ACCESS_TOKEN"],
        access_token_secret=os.environ["X_ACCESS_SECRET"],
    )
    resp = tw.create_tweet(text=text)
    return str(resp.data["id"])


def main() -> None:
    now = datetime.datetime.now(JST)
    slot = slot_of(now.hour)

    base = read(ROOT / "prompts/base.md")
    slots = read(ROOT / "prompts/slots.md")
    strategy = read(ROOT / "state/strategy.md", "（データ蓄積中）")
    recent = recent_texts(ROOT / "state/history.jsonl")

    system = (
        f"{base}\n\n---\n【時間帯ガイド】\n{slots}\n\n---\n"
        f"【最新戦略メモ（自動生成）】\n{strategy}\n\n---\n"
        f"【直近投稿（重複回避用）】\n{recent}"
    )
    user = (
        f"次の投稿を1件だけ生成。時間帯: {slot}。"
        "本文だけを出力し、前置きや解説は一切不要。"
        "280字以内・ハッシュタグは最大2個・URLは https://triedge.app または App Store URL のみ。"
    )

    text = generate(system, user)
    print(f"--- generated (len={len(text)}) ---\n{text}\n--- end ---")
    assert 1 <= len(text) <= 280, f"len={len(text)}: {text!r}"
    hashtags = [w for w in text.split() if w.startswith("#")]
    assert 1 <= len(hashtags) <= 2, f"hashtags={hashtags}: プロンプト守られず・投稿中止"
    # 禁止フレーズ: 嘘（app は既に公開済so「作ってます」等は嘘）+ 誇大表現
    # ponytail: 「TriEdgeなら」は元々禁止してたが単発なら自然so許容, 連続使用は strategy.md 経由で自動抑制
    banned = ["作ってます", "作りたい", "開発中", "実装しました",
              "実装中", "開発してます", "唯一無二"]
    for b in banned:
        assert text.count(b) == 0, f"禁止フレーズ '{b}' が含まれる・投稿中止"
    # #TriEdge タグ必須（過去投稿全件で使用・ブランドタグ）
    assert "#TriEdge" in text, "#TriEdge タグが無い・投稿中止"

    tweet_id = post_x(text)

    entry = {
        "tweet_id": tweet_id,
        "posted_at": now.isoformat(),
        "slot": slot,
        "text": text,
        "likes": None, "retweets": None, "replies": None, "impressions": None,
        "measured_at": None,
    }
    with (ROOT / "state/history.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"posted id={tweet_id} slot={slot} len={len(text)}: {text[:60]}")


if __name__ == "__main__":
    main()
