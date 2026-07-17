
毎朝のAIニュースポッドキャストの「音声化」ステップを実行する。

背景: クラウドルーティーンが毎朝6:20にニュースダイジェスト（digests/YYYY-MM-DD.md）を GitHub リポジトリ rinrinzetetic09-glitch/ai-news-podcast の claude/pages ブランチにpushしている。このタスクはそれをNotebookLMの音声解説（Audio Overview）にして、GitHub Pagesのポッドキャストフィードに公開する。

実行手順:
1. `python3 /Users/rinrin/coding/ai-news-podcast/scripts/nlm_episode.py` を実行する（実行に20〜40分かかることを許可。NotebookLMの音声生成待ちが大半）。
2. スクリプトが正常終了したら、https://rinrinzetetic09-glitch.github.io/ai-news-podcast/feed.xml に今日のm4aエピソードが載っていることを確認して完了報告する。
3. 「今日の分は公開済み」と出たら何もせず完了。
4. 「digestがまだありません」の場合はクラウド側が未実行。1時間後に再試行するよう報告して終了。

エラー時の対処:
- `nlm login --check` で認証切れが判明したら: 自分でログインを試みてはいけない（Googleログインはユーザーの手作業）。ntfy（https://ntfy.sh/rinrin-Antigravity-Secret-517482848100）へ「NotebookLMの再ログインが必要: ターミナルで nlm login を実行してください」と通知し、ユーザーへの報告にも同じ内容を書く。
- nlm CLIのJSON応答の形が想定と違ってスクリプトが失敗した場合: nlmコマンド（nlm list notebooks --json 等）を手で叩いて実際の応答形式を確認し、/Users/rinrin/coding/ai-news-podcast/scripts/nlm_episode.py の該当箇所（find_id / wait_for_audio / cleanup_old_sources）を修正してから再実行する。修正したら main ブランチにもコミットして git push origin main しておく。
- NotebookLM側の仕様変更・アカウント停止が疑われる場合は、無理に回避せずntfyとユーザー報告で知らせる。

注意:
- 使用しているnlm CLI（notebooklm-mcp-cli）は非公式ツールで、専用の捨てGoogleアカウントで運用している。CAPTCHAやログイン画面の突破を自動化してはいけない。
- リポジトリのclaude/pagesブランチが配信ブランチ。mainにはスクリプト修正のみ。PRは作らない。