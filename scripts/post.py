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


def post_x(text: str):
    """成功=(tweet_id, None) / 失敗=(None, (status, body))。上位でリトライ判断する。"""
    tw = tweepy.Client(
        consumer_key=os.environ["X_API_KEY"],
        consumer_secret=os.environ["X_API_SECRET"],
        access_token=os.environ["X_ACCESS_TOKEN"],
        access_token_secret=os.environ["X_ACCESS_SECRET"],
    )
    try:
        resp = tw.create_tweet(text=text)
    except tweepy.errors.HTTPException as e:
        body = getattr(e.response, "text", "(no body)")
        code = getattr(e.response, "status_code", "?")
        print(f"[X API error] status={code}\nbody={body}")
        return None, (code, body)
    return str(resp.data["id"]), None


def log_failed(now, slot: str, text: str, attempt: int, err: tuple) -> None:
    """失敗した生成テキストと X のレスポンスを state/failed.jsonl に追記。診断用。"""
    entry = {
        "posted_at": now.isoformat(),
        "slot": slot,
        "attempt": attempt,
        "text": text,
        "error_status": err[0],
        "error_body": err[1],
    }
    (ROOT / "state").mkdir(exist_ok=True)
    with (ROOT / "state/failed.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def validate(text: str) -> None:
    """生成テキストの投稿前チェック(長さ・ハッシュタグ数・禁止フレーズ)。"""
    assert 1 <= len(text) <= 280, f"len={len(text)}: {text!r}"
    hashtags = [w for w in text.split() if w.startswith("#")]
    assert 2 <= len(hashtags) <= 4, f"hashtags={hashtags}: 2〜4個必須 (過去投稿分布)・投稿中止"
    banned = ["作ってます", "作りたい", "開発中", "実装しました",
              "実装中", "開発してます", "唯一無二"]
    for b in banned:
        assert text.count(b) == 0, f"禁止フレーズ '{b}' が含まれる・投稿中止"
    assert "#TriEdge" in text, "#TriEdge タグが無い・投稿中止"


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
        "【直近投稿（★絶対に主題・語彙を重ねてはいけない）】\n"
        "以下は直近の投稿。X の重複コンテンツ検出に引っかかると 403 で投稿失敗する。\n"
        "同じ主題（例: 体重の変動 / ベンチプレス / 松屋牛丼 / 液体カロリー 等）や、\n"
        "同じ固有名詞・具体例を絶対に繰り返さない。全く別の切り口・別のジャンルで書く。\n\n"
        f"{recent}"
    )
    user = (
        f"次の投稿を1件だけ生成。時間帯: {slot}。"
        "本文だけを出力し、前置きや解説は一切不要。"
        "280字以内・ハッシュタグは #TriEdge を含めて2〜4個・URLは基本入れない（bio に固定）。"
        "★直近投稿と主題・語彙・構造すべて別物にすること（X の 403 duplicate detection 回避）。"
    )

    # attempt 1
    text = generate(system, user)
    print(f"--- generated (len={len(text)}) ---\n{text}\n--- end ---")
    validate(text)
    tweet_id, err = post_x(text)

    # X の 403 duplicate detection は false positive が多い(公式フォーラム多数報告)。
    # 主題が違っても同型テンプレは flag されうるので、1回だけ構造を変えて再生成しリトライ。
    if tweet_id is None and err[0] == 403:
        log_failed(now, slot, text, 1, err)
        retry_user = (
            f"次の投稿を1件だけ生成。時間帯: {slot}。"
            "★直前の生成が X から 403 で拒否されたので、構造を根本から変える。\n\n"
            f"【拒否された文（絶対に語彙・出だし・構造を再利用するな）】\n{text}\n\n"
            "拒否文と別の書き出し(質問/断定/データ提示/場面描写など)・別の主題・別のハッシュタグ組合せで書く。"
            "本文だけを出力・280字以内・#TriEdge 含めハッシュタグ2〜4個・URL不要。"
        )
        text2 = generate(system, retry_user)
        print(f"--- retry generated (len={len(text2)}) ---\n{text2}\n--- end ---")
        validate(text2)
        tweet_id, err2 = post_x(text2)
        if tweet_id is None:
            log_failed(now, slot, text2, 2, err2)
            raise SystemExit(f"[X API] retry も 403 で失敗。failed.jsonl 参照。")
        text = text2

    if tweet_id is None:
        # 403 以外の失敗(429/401/5xx等)は retry しない(原因が別so)
        log_failed(now, slot, text, 1, err)
        raise SystemExit(f"[X API] status={err[0]} で失敗。failed.jsonl 参照。")

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
