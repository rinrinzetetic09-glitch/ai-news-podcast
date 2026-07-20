# 毎朝のAIニュース（自分専用ポッドキャスト）

Hacker News・Reddit・はてなブックマークから毎朝収集したAI・Techニュースを、
NotebookLMのラジオ風解説（Audio Overview）にしてポッドキャスト配信するリポジトリ。

- **フィードURL**: `https://rinrinzetetic09-glitch.github.io/ai-news-podcast/feed.xml`
- スマホのポッドキャストアプリ（Apple Podcasts / Overcast など）で上記URLを登録して購読する。
- フィードは GitHub Pages、音声ファイルは Cloudflare R2 から配信する。

## 仕組み（毎朝の全自動パイプライン）

1. **6:20** claude.ai のクラウドルーティーンがニュースを収集し、ダイジェスト
   （`digests/YYYY-MM-DD.md`）を `claude/pages` ブランチに push
2. Mac のスケジュールタスクが `scripts/nlm_episode.py` を実行:
   - ダイジェストを NotebookLM にソース追加し、音声解説（日本語・deep dive）を生成
   - 生成された m4a をダウンロード（20〜40分かかる）
3. `scripts/make_episode.py --audio` が仕上げ:
   - オープニング音源（`assets/ai-news_opening.mp3`）を冒頭に連結（ffmpeg）
   - 再生時間を ffprobe で実測
   - 音声を **Cloudflare R2** にアップロード
   - `episodes.json` と `feed.xml` を更新して push
4. GitHub Pages が `feed.xml` を配信、音声は R2 の公開URLから直接配信

## 配信インフラ

| 役割 | 場所 |
|---|---|
| フィード・ショーノート | GitHub Pages（`claude/pages` ブランチ） |
| 音声ファイル | Cloudflare R2 バケット `ai-news-podcast`（公開URL: `pub-4dbb7ec60a80442e8a73332e9fa2a690.r2.dev`） |
| R2 認証情報 | Mac の `~/.config/ai-news-podcast/r2.env`（APIトークン・アカウントID） |

- 以前は GitHub Releases から音声を配信していたが、ダウンロードURLのリダイレクトで
  再生が不安定になることがあったため R2 に移行した（egress無料・リダイレクトなし）。
- R2 の無料枠は 10GB。約20MB/日 × 90日保持なので余裕で収まる。

## ブランチ構成

- `claude/pages` — 配信用。feed.xml / episodes.json / digests / ショーノートを更新
- `main` — スクリプト・ドキュメントの修正のみ。PRは作らない

## 手動でエピソードを作る

```bash
# NotebookLM の音声を使う場合（通常フロー）
python3 scripts/nlm_episode.py

# 既存の音声ファイルから作る場合
python3 scripts/make_episode.py 原稿.md --date 2026-07-16 --audio 音声.m4a

# 原稿だけから TTS（edge-tts / gTTS フォールバック）で作る場合
python3 scripts/make_episode.py 原稿.md --date 2026-07-16 --title "タイトル"
```

- 原稿は Markdown 可（TTS時はリンクや記号を自動除去）
- feed には最新30件を掲載、90日より古い音声は R2 から自動削除

## 注意

- このリポジトリは公開リポジトリ（GitHub Pages の無料配信のため）。
  フィードURLは非公開・未登録だが、URLを知っていれば誰でも聞ける。
- NotebookLM の操作には非公式 CLI（`nlm` / notebooklm-mcp-cli）を専用の
  捨てGoogleアカウントで使用。認証が切れたら Mac で `nlm login` を手動実行する。
