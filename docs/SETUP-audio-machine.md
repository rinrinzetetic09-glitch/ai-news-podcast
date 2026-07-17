# 音声生成マシンのセットアップ手順

このMacを「毎朝のAIニュース」ポッドキャストの音声生成マシンにする手順。
Claude Codeがこのファイルを読んで実行することを想定している。

## 全体像

- クラウドルーティーンが毎朝6:20 JSTに `digests/YYYY-MM-DD.md` を claude/pages ブランチにpushする
- このマシンのスケジュールタスクが毎朝7:06（Claude Codeアプリが開いていれば）に
  `scripts/nlm_episode.py` を実行し、digestをNotebookLMで音声解説にして
  `episodes/` と `feed.xml` を更新・pushする
- フィード: https://rinrinzetetic09-glitch.github.io/ai-news-podcast/feed.xml

## 手順

### 1. リポジトリのクローン（未クローンの場合）

```bash
git clone https://github.com/rinrinzetetic09-glitch/ai-news-podcast.git ~/coding/ai-news-podcast
```

pushできる認証があることを確認する（`gh auth status`。未認証ならユーザーに
`gh auth login` を実行してもらう）。

### 2. nlm CLI のインストール

```bash
# uvがなければ: curl -LsSf https://astral.sh/uv/install.sh | sh
uv tool install notebooklm-mcp-cli
nlm --version
```

### 3. NotebookLMへのログイン【ユーザーの手作業】

```bash
nlm login
```

ブラウザが開くので、**ポッドキャスト用の捨てGoogleアカウント**でログインしてもらう。
これはユーザー本人にやってもらうこと（Claudeがパスワード入力を代行してはいけない）。
Cookieは2〜4週間有効。切れると ntfy に再ログイン依頼が届く。

### 4. スケジュールタスクの作成

Claude Codeのスケジュールタスク（scheduled-tasks）として `daily-ai-news-audio` を
cron `3 7 * * *`（毎朝7:06ローカル）で作成する。タスクのプロンプトは
リポジトリ内の [task-prompt-audio.md](task-prompt-audio.md) の内容を使う。
その際、プロンプト中のリポジトリパスをこのマシンの実際のクローン先
（例: `$HOME/coding/ai-news-podcast`）の絶対パスに置き換えること。

### 5. スリープ対策【ユーザーの手作業・任意】

蓋を閉じて放置するとスケジュールタスクが動かない。常時起動運用にするなら:

- 電源アダプタに接続しておく
- 「ディスプレイがオフのときに自動でスリープさせない」を有効にする
  （システム設定 → ディスプレイ → 詳細設定、または `sudo pmset -c sleep 0`）
- Claude Codeアプリは起動したままにする（スケジュールタスクはアプリ起動中に動く。
  閉じていた場合は次回起動時に追い付き実行される）

### 6. 動作確認

```bash
cd ~/coding/ai-news-podcast
python3 scripts/nlm_episode.py
```

- 今日のdigestが未生成の時間帯なら「digestがまだありません」で正常
- 成功すると feed.xml に今日の .m4a エピソードが載り、ntfyに通知が届く

## 二重実行に注意

音声生成タスクを動かすマシンは**1台だけ**にする。他のマシンに同じ
スケジュールタスクが残っていると、同時実行時にgit pushが衝突する。
移行したら旧マシン側のタスクを削除すること。
