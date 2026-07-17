
毎朝のAIニュースポッドキャストの「音声化」ステップを実行する。

背景: クラウドルーティーンが毎朝6:20から「徹底リサーチ」を行い、完了後にニュースダイジェスト（digests/YYYY-MM-DD.md）を GitHub リポジトリ rinrinzetetic09-glitch/ai-news-podcast の claude/pages ブランチにpushする。リサーチの所要時間は読めない（数十分〜1時間強）。このタスクはそのdigestをNotebookLMの音声解説（Audio Overview）にして、GitHub Pagesのポッドキャストフィードに公開する。

実行手順:
1. `python3 <このリポジトリのパス>/scripts/nlm_episode.py` を実行する（最大2時間近くかかることを許可。内訳: 今日のdigestがpushされるのを最大90分ポーリング待機 + NotebookLM音声生成待ち20〜40分）。スクリプトは(1)claude/pagesを同期し(2)今日のdigestが来るまで5分ごとにgitをポーリングして待ち(3)揃ったら音声化して公開、まで自動でやる。ローカルとクラウドの時間差はスクリプトが吸収するので、起動時刻がクラウド完了より早くても問題ない。
2. スクリプトが正常終了したら、https://rinrinzetetic09-glitch.github.io/ai-news-podcast/feed.xml に今日のm4aエピソードが載っていることを確認して完了報告する。
3. 「今日の分は公開済み」と出たら何もせず完了。
4. 「digestなし（タイムアウト）」で終了した場合はクラウド側が90分以内にpushできなかったということ。クラウドルーティーンの当日の実行ログ（claude.ai/code のルーティン daily-ai-news-podcast）を確認するようユーザーに報告して終了。

エラー時の対処:
- `nlm login --check` で認証切れが判明したら: 自分でログインを試みてはいけない（Googleログインはユーザーの手作業）。ntfy（https://ntfy.sh/rinrin-Antigravity-Secret-517482848100）へ「NotebookLMの再ログインが必要: ターミナルで nlm login を実行してください」と通知し、ユーザーへの報告にも同じ内容を書く。
- nlm CLIのJSON応答の形が想定と違ってスクリプトが失敗した場合: nlmコマンド（nlm list notebooks --json 等）を手で叩いて実際の応答形式を確認し、scripts/nlm_episode.py の該当箇所（find_id / wait_for_audio / cleanup_old_sources）を修正してから再実行する。修正したら main ブランチにもコミットして git push origin main しておく。
- NotebookLM側の仕様変更・アカウント停止が疑われる場合は、無理に回避せずntfyとユーザー報告で知らせる。

注意:
- 使用しているnlm CLI（notebooklm-mcp-cli）は非公式ツールで、専用の捨てGoogleアカウントで運用している。CAPTCHAやログイン画面の突破を自動化してはいけない。
- リポジトリのclaude/pagesブランチが配信ブランチ。mainにはスクリプト修正のみ。PRは作らない。
- 音声（m4a）はリポジトリに入れず GitHub Releases（タグ episodes）へアップロードされる（make_episode.pyが自動でやる）。そのため gh が repo スコープで認証済みであること。`gh release upload` が権限エラーで失敗したら、ntfyとユーザー報告で「gh auth を確認してほしい」と知らせる。