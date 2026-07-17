# 音声生成マシンのセットアップ手順

このMacを「毎朝のAIニュース」ポッドキャストの音声生成マシンにする手順。
Claude Codeがこのファイルを読んで実行することを想定している。

## 全体像

- クラウドルーティーンが毎朝6:20 JSTから徹底リサーチを行い、完了後に
  `digests/YYYY-MM-DD.md` を claude/pages ブランチにpushする（所要時間は可変）
- このマシンのスケジュールタスクが毎朝6:50（Claude Codeアプリが開いていれば）に
  `scripts/nlm_episode.py` を実行する。スクリプトは今日のdigestがpushされるのを
  最大90分ポーリング待機し、揃ったらNotebookLMで音声解説を作って
  `episodes/` と `feed.xml` を更新・pushする（両ステージの時間差はスクリプトが吸収）
- フィード: https://rinrinzetetic09-glitch.github.io/ai-news-podcast/feed.xml

## 手順

### 1. リポジトリのクローン（未クローンの場合）

```bash
git clone https://github.com/rinrinzetetic09-glitch/ai-news-podcast.git ~/coding/ai-news-podcast
```

pushできる認証があることを確認する（`gh auth status`。未認証ならユーザーに
`gh auth login` を実行してもらう）。音声ファイルは GitHub Releases に
アップロードするので、gh は **repo スコープ付きで認証済み**である必要がある
（`gh release upload` が通ること）。

### 2. nlm CLI と ffmpeg のインストール

```bash
# uvがなければ: curl -LsSf https://astral.sh/uv/install.sh | sh
uv tool install notebooklm-mcp-cli
nlm --version

# ffmpeg（各エピソード冒頭にオープニング音源 assets/ai-news_opening.mp3 を
# 連結するために必要）。Homebrewが無ければ https://brew.sh から入れる。
brew install ffmpeg
ffmpeg -version | head -1
```

ffmpegが無い場合、エピソードは公開されるがオープニングは付かない（スキップして
続行し、警告を出す）。オープニングを必ず付けたいなら ffmpeg を入れておくこと。

### 3. NotebookLMへのログイン【ユーザーの手作業】

```bash
nlm login
```

ブラウザが開くので、**ポッドキャスト用の捨てGoogleアカウント**でログインしてもらう。
これはユーザー本人にやってもらうこと（Claudeがパスワード入力を代行してはいけない）。
Cookieは2〜4週間有効。切れると ntfy に再ログイン依頼が届く。

### 4. スケジュールタスクの作成

Claude Codeのスケジュールタスク（scheduled-tasks）として `daily-ai-news-audio` を
cron `50 6 * * *`（毎朝6:50ローカル）で作成する。タスクのプロンプトは
リポジトリ内の [task-prompt-audio.md](task-prompt-audio.md) の内容を使う。
その際、プロンプト中の `<このリポジトリのパス>` をこのマシンの実際のクローン先
（例: `$HOME/coding/ai-news-podcast`）の絶対パスに置き換えること。

6:50はクラウド開始（6:20）の直後。digestがまだでもスクリプトが最大90分
待つので、この時刻はクラウド完了より早くて構わない。アプリが閉じていて
6:50に発火できなかった場合も、次にアプリを開いたときに追い付き実行される。

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

## 音声の保存先（重要）

音声（m4a）は**リポジトリ本体には入れず、GitHub Releases（タグ `episodes`）の
添付ファイルとして保存**する。理由はリポジトリ容量とgit履歴の肥大化を避けるため。
`make_episode.py` が自動でReleaseへアップロードし、フィードのenclosure URLを
Releaseのダウンロードリンクにする。リポジトリにはテキスト（feed.xml・
episodes.json・ショーノートmd）だけが残るので、いくら日が経っても軽いまま。
古い音声（既定90日超）はRelease添付ごと自動削除される。

## 二重実行に注意

音声生成タスクを動かすマシンは**1台だけ**にする。他のマシンに同じ
スケジュールタスクが残っていると、同時実行時にgit push / Releaseアップロードが
衝突する。移行したら旧マシン側のタスクを削除すること。
