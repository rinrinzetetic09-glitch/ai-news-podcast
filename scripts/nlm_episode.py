#!/usr/bin/env python3
"""digest md → NotebookLM 音声解説 → エピソード公開（ローカル実行用）。

毎朝クラウドルーティーンが digests/YYYY-MM-DD.md をpushしている前提で、
1. リポジトリを claude/pages に同期
2. 今日の digest を NotebookLM にソース追加（nlm CLI・要ログイン済み）
3. 音声解説（日本語・deep_dive・long、focusは docs/audio-overview-prompt.md）を生成して .m4a をダウンロード
4. make_episode.py --audio でフィード更新 → コミット & push
5. ntfy へ結果通知
までを行う。冪等：今日の分が公開済みなら何もしない。

前提: `uv tool install notebooklm-mcp-cli` 済みで `nlm login` 済み。
"""

import datetime
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = Path.home() / ".config" / "ai-news-podcast"
NOTEBOOK_ID_FILE = CONFIG_DIR / "notebook_id"
AUDIO_OVERVIEW_PROMPT_FILE = ROOT / "docs" / "audio-overview-prompt.md"
NTFY_URL = "https://ntfy.sh/rinrin-Antigravity-Secret-517482848100"
BRANCH = "claude/pages"
AUDIO_WAIT_MAX_MIN = 30
DIGEST_WAIT_MAX_MIN = 90   # クラウドの徹底リサーチが終わるまで待つ上限
DIGEST_POLL_SEC = 300      # digest未着なら5分ごとに再確認
SOURCE_KEEP_DAYS = 7

os.environ.setdefault("NOTEBOOKLM_HL", "ja")


def sh(*args: str, check: bool = True, cwd: Path = ROOT) -> str:
    r = subprocess.run(args, capture_output=True, text=True, cwd=cwd)
    if check and r.returncode != 0:
        raise RuntimeError(f"コマンド失敗: {' '.join(args)}\n{r.stdout}\n{r.stderr}")
    return r.stdout.strip()


def nlm_json(*args: str) -> object:
    out = sh("nlm", *args, "--json")
    # 進捗表示などが混ざる場合に備え、最初の { か [ から読む
    m = re.search(r"[\[{]", out)
    if not m:
        raise RuntimeError(f"nlm がJSONを返しませんでした: {out[:300]}")
    return json.loads(out[m.start():])


def find_id(obj: object, *keys: str) -> str:
    """JSON応答からIDらしきフィールドを防御的に探す。"""
    if isinstance(obj, dict):
        for k in keys:
            if k in obj and isinstance(obj[k], str) and obj[k]:
                return obj[k]
        for v in obj.values():
            try:
                return find_id(v, *keys)
            except LookupError:
                pass
    elif isinstance(obj, list):
        for v in obj:
            try:
                return find_id(v, *keys)
            except LookupError:
                pass
    raise LookupError(f"IDが見つかりません: {keys}")


def notify(title: str, body: str) -> None:
    subprocess.run(
        ["curl", "--max-time", "10", "-H", f"Title: {title}", "-d", body, NTFY_URL],
        capture_output=True,
    )


def notebook_id() -> str:
    if NOTEBOOK_ID_FILE.exists():
        return NOTEBOOK_ID_FILE.read_text().strip()
    nb = nlm_json("notebook", "create", "Daily AI News")
    nb_id = find_id(nb, "notebook_id", "id", "notebookId")
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    NOTEBOOK_ID_FILE.write_text(nb_id)
    return nb_id


def wait_for_audio(nb: str, artifact_id: str) -> None:
    deadline = time.time() + AUDIO_WAIT_MAX_MIN * 60
    while time.time() < deadline:
        arts = nlm_json("status", "artifacts", nb, "--full")
        blob = json.dumps(arts, ensure_ascii=False)
        if artifact_id:
            # 該当アーティファクトの周辺だけ見る
            idx = blob.find(artifact_id)
            window = blob[max(0, idx - 500): idx + 500] if idx >= 0 else blob
        else:
            window = blob
        if re.search(r"(ready|complete|succeed|success)", window, re.IGNORECASE):
            return
        if re.search(r"(fail|error)", window, re.IGNORECASE):
            raise RuntimeError(f"音声生成が失敗した模様: {window[:300]}")
        time.sleep(60)
    raise RuntimeError(f"{AUDIO_WAIT_MAX_MIN}分待っても音声が完成しませんでした")


def cleanup_old_sources(nb: str, today: str) -> None:
    cutoff = (datetime.date.fromisoformat(today)
              - datetime.timedelta(days=SOURCE_KEEP_DAYS)).isoformat()
    try:
        sources = nlm_json("list", "sources", nb)
        blob = sources if isinstance(sources, list) else sources.get("sources", [])
        for s in blob:
            title = str(s.get("title", ""))
            m = re.match(r"(\d{4}-\d{2}-\d{2})", title)
            if m and m.group(1) < cutoff:
                sid = find_id(s, "source_id", "id", "sourceId")
                sh("nlm", "delete", "source", sid, "-y", check=False)
    except Exception as e:
        print(f"古いソースの掃除に失敗（続行）: {e}", file=sys.stderr)


def sync_branch() -> None:
    sh("git", "fetch", "origin")
    sh("git", "checkout", BRANCH)
    sh("git", "pull", "--ff-only", "origin", BRANCH)


def already_published(today: str) -> bool:
    manifest = ROOT / "episodes.json"
    if not manifest.exists():
        return False
    for ep in json.loads(manifest.read_text()):
        if ep["date"] == today and ep.get("type") == "audio/mp4":
            return True
    return False


def wait_for_digest(today: str) -> Path:
    """クラウドが今日のdigestをpushし終えるまでgitをポーリングして待つ。

    クラウド側の「徹底リサーチ」は所要時間が読めないため、固定時刻で
    決め打ちせず、digestが claude/pages に現れるのを待ってから音声化する。
    """
    digest = ROOT / "digests" / f"{today}.md"
    deadline = time.time() + DIGEST_WAIT_MAX_MIN * 60
    while True:
        sync_branch()
        if digest.exists():
            return digest
        if time.time() >= deadline:
            notify("AI News Podcast ⚠️",
                   f"{today} のdigestが{DIGEST_WAIT_MAX_MIN}分待っても来ませんでした"
                   "（クラウド側が未実行か失敗の可能性）")
            sys.exit(f"digestなし（タイムアウト）: {digest}")
        print(f"digest待機中… {digest.name} を{DIGEST_POLL_SEC//60}分後に再確認")
        time.sleep(DIGEST_POLL_SEC)


def main() -> None:
    today = datetime.date.today().isoformat()

    sync_branch()
    if already_published(today):
        print("今日の分は公開済み。何もしません。")
        return

    digest = wait_for_digest(today)

    nb = notebook_id()

    print("digestをソース追加中…")
    src = nlm_json("add", "text", nb, digest.read_text(encoding="utf-8"),
                   "--title", f"{today} digest", "--wait")
    source_id = find_id(src, "source_id", "id", "sourceId")

    print("音声解説を生成中…")
    focus = AUDIO_OVERVIEW_PROMPT_FILE.read_text(encoding="utf-8").strip()
    art = nlm_json("audio", "create", nb,
                   "--format", "deep_dive", "--length", "long",
                   "--language", "ja",
                   "--focus", focus,
                   "-s", source_id, "--confirm")
    try:
        artifact_id = find_id(art, "artifact_id", "id", "artifactId", "task_id")
    except LookupError:
        artifact_id = ""

    wait_for_audio(nb, artifact_id)

    with tempfile.TemporaryDirectory() as td:
        m4a = Path(td) / f"{today}.m4a"
        dl = ["nlm", "download", "audio", nb, "-o", str(m4a), "--no-progress"]
        if artifact_id:
            dl += ["--id", artifact_id]
        sh(*dl)
        if not m4a.exists() or m4a.stat().st_size < 100_000:
            raise RuntimeError("ダウンロードした音声が小さすぎます")

        sh(sys.executable, str(ROOT / "scripts" / "make_episode.py"), str(digest),
           "--date", today,
           "--title", f"{today} 毎朝のAIニュース（ラジオ解説）",
           "--description", f"{today} のAI・Techニュースを対話形式で解説。",
           "--audio", str(m4a))

    sh("git", "add", "-A")
    sh("git", "commit", "-m", f"Episode {today} (NotebookLM)")
    sh("git", "push", "origin", BRANCH)

    if artifact_id:
        sh("nlm", "delete", "artifact", nb, artifact_id, "-y", check=False)
    cleanup_old_sources(nb, today)

    notify("AI News Podcast 🎙", f"{today} のラジオ版エピソードを公開しました")
    print("完了")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        notify("AI News Podcast ❌", f"音声生成に失敗: {e}")
        raise
