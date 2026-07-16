# 毎朝のAIニュース（自分専用ポッドキャスト）

Hacker News・Reddit・はてなブックマークから毎朝収集したAI・Techニュースを、
音声（mp3）にしてポッドキャストとして配信するリポジトリ。

- **フィードURL**: `https://rinrinzetetic09-glitch.github.io/ai-news-podcast/feed.xml`
- スマホのポッドキャストアプリ（Apple Podcasts / Overcast など）で上記URLを登録して購読する。
- エピソードの生成は claude.ai のクラウドルーティーンが毎朝実行する（PC不要）。

## 仕組み

1. クラウドルーティーンがニュースを収集し、聞き流し用のラジオ原稿（Markdown）を作成
2. `scripts/make_episode.py` が edge-tts（無料・APIキー不要）で mp3 を生成
3. `episodes.json` と `feed.xml` を更新してこのリポジトリに push
4. GitHub Pages が `feed.xml` と mp3 を配信

## 手動でエピソードを作る

```bash
python3 scripts/make_episode.py 原稿.md --date 2026-07-16 --title "2026-07-16 AIニュース"
git add -A && git commit -m "Episode 2026-07-16" && git push
```

- 原稿は Markdown 可（リンクや記号は読み上げ時に自動除去）
- feed には最新30件を掲載、90日より古い mp3 は自動削除

## 注意

- このリポジトリは公開リポジトリ（GitHub Pages の無料配信のため）。
  フィードURLは非公開・未登録だが、URLを知っていれば誰でも聞ける。
