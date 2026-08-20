"""history.jsonlからtop/bottom5を抽出→strategy.mdを再生成。fetch_metricsの直後に走る。

生成したstrategy.mdは次回post.pyのシステムプロンプトに丸ごと差し込まれる。
LLMが「反応良い投稿の型」を模倣し「反応悪い型」を避けるようになる = フィードバックループ。
"""
import json, pathlib, statistics

ROOT = pathlib.Path(__file__).resolve().parent.parent
HIST = ROOT / "state/history.jsonl"
OUT  = ROOT / "state/strategy.md"


def score(e: dict) -> float:
    # ponytail: 素朴な engagement 指標 (likes 3倍・retweets 5倍・imp 1%), 効きが悪ければ後で調整
    return ((e.get("likes") or 0) * 3
            + (e.get("retweets") or 0) * 5
            + (e.get("impressions") or 0) * 0.01)


def main() -> None:
    if not HIST.exists():
        OUT.write_text("（history未生成・戦略保留）\n", encoding="utf-8")
        return

    entries = [json.loads(l) for l in HIST.read_text(encoding="utf-8").splitlines() if l.strip()]
    measured = [e for e in entries if e.get("impressions") is not None]

    if len(measured) < 5:
        OUT.write_text(f"（データ蓄積中: 測定済 {len(measured)}/5・戦略生成保留）\n", encoding="utf-8")
        print(f"only {len(measured)} measured, skip strategy")
        return

    ranked = sorted(measured, key=score, reverse=True)
    top5 = ranked[:5]
    bottom5 = ranked[-5:]
    imps = [e["impressions"] or 0 for e in measured]
    likes = [e["likes"] or 0 for e in measured]

    md = []
    md.append("# TriEdge X 戦略メモ（bot自己生成・毎日00:00 JST更新）\n\n")
    md.append(f"直近測定: {len(measured)}件・impressions中央値 {int(statistics.median(imps))}・likes中央値 {int(statistics.median(likes))}\n\n")
    md.append("## トップ5（反応良・パターンを踏襲）\n")
    for e in top5:
        md.append(f"- [imp={e.get('impressions')} like={e.get('likes')} slot={e.get('slot')}] {e['text']}\n")
    md.append("\n## ボトム5（反応薄・パターンを避ける）\n")
    for e in bottom5:
        md.append(f"- [imp={e.get('impressions')} like={e.get('likes')} slot={e.get('slot')}] {e['text']}\n")
    md.append("\n## 次回生成時の指針\n")
    md.append("- 上のトップ5の構造・話題・トーンを優先する。\n")
    md.append("- ボトム5と似た表現・話題は避ける。\n")
    md.append("- 時間帯(slot)による反応差も踏まえる。\n")

    OUT.write_text("".join(md), encoding="utf-8")
    print(f"strategy.md updated ({len(measured)} measured)")


if __name__ == "__main__":
    main()
