# TriEdge X Bot

TriEdge (https://triedge.app) 公式X自動投稿 bot。
- **生成**: Claude Haiku が投稿を都度生成（固定文言ではない）
- **フィードバックループ**: 毎日メトリクス取得 → top/bottom5 を戦略メモに書き出し → 次回生成プロンプトに流し込む → 反応良かった型に自動収束

## 構成

```
scripts/
  post.py            投稿生成 + X 投稿 + history 追記
  fetch_metrics.py   直近10ツイートの impressions/likes 取得
  update_strategy.py history → strategy.md 再生成 (LLM 用)
prompts/
  base.md            アカウントの声 (人間が編集する)
  slots.md           朝/昼/夜の時間帯ガイド (人間が編集する)
state/
  history.jsonl      各投稿の記録 + メトリクス (bot が追記)
  strategy.md        自動生成の戦略メモ (次回プロンプトに注入)
.github/workflows/
  post.yml           07:30 / 12:30 / 21:00 JST cron
  metrics.yml        00:00 JST cron
```

## コスト (2026-07 pay-per-use)

| 項目 | 単価 | 月間 |
|---|---|---|
| X 投稿 | $0.015/tweet × 3/日 × 30日 | **$1.35** |
| X メトリクス取得 | $0.005/read × 10/日 × 30日 | **$1.50** |
| Claude Haiku (生成) | 500 in + 100 out / tweet × 90/月 | **~$0.05** |
| **合計** | | **~$3.00/月** |

`scripts/fetch_metrics.py` の `LOOKBACK = 10` を増減するとコストが線形に変わる。

## セットアップ（人間作業・~20分）

### 1. X Developer App
1. https://developer.x.com/en/portal/dashboard で新規アプリ作成
2. User authentication settings → **Read and Write** 有効化
3. Keys and tokens → **Access Token & Secret を Read and Write 権限で再発行**（Read-only のまま使うと 403）
4. 4キー取得: API Key / API Secret / Access Token / Access Token Secret
5. Billing → pay-per-use に登録（クレカ）

### 2. Anthropic API キー
TriEdge 本体で使っている `ANTHROPIC_API_KEY` を流用可能。無ければ https://console.anthropic.com で発行。

### 3. GitHub Secrets
リポジトリ Settings → Secrets and variables → Actions:
- `X_API_KEY`
- `X_API_SECRET`
- `X_ACCESS_TOKEN`
- `X_ACCESS_SECRET`
- `ANTHROPIC_API_KEY`

### 4. Actions permissions
Settings → Actions → General → Workflow permissions → **Read and write permissions**（bot が state/ を commit する）

### 5. 動作確認
Actions タブから `post` を workflow_dispatch で手動実行 → 実際に投稿されるかを目視で確認。

## 運用の触り方

- 投稿の声・禁止事項を変えたい → `prompts/base.md` を編集
- 時間帯別のテーマを変えたい → `prompts/slots.md` を編集
- 戦略メモの生成ロジックを変えたい → `scripts/update_strategy.py` の `score()` を触る
- 頻度変更 → `.github/workflows/post.yml` の cron を編集
- 完全停止 → GitHub UI から両ワークフローを disable

## フィードバックループの動き

```
[post 07:30] → generate → post → history 追記
[post 12:30] → generate (strategy.md 参照) → post → history 追記
[post 21:00] → generate (strategy.md 参照) → post → history 追記
      ↓ (次の日 00:00)
[metrics]   → 直近10件のメトリクス取得 → history 更新 → strategy.md 再生成
      ↓
[翌日以降の post] は更新された strategy.md を読んで生成される
```

`state/history.jsonl` と `state/strategy.md` は git 履歴に残るので、
「いつどう戦略が変わったか」を git log で追える。
