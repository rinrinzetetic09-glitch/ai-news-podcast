#!/usr/bin/env python3
"""原稿テキスト → mp3 (edge-tts) → episodes.json 更新 → feed.xml 再生成。

使い方:
    python3 scripts/make_episode.py 原稿ファイル.md [--date YYYY-MM-DD] [--title タイトル]

原稿はプレーンテキストか Markdown。Markdown の場合はリンク・記号類を
読み上げ用に除去してから TTS にかける。
"""

import argparse
import datetime
import html
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

# ---- 設定 -------------------------------------------------------------
BASE_URL = "https://rinrinzetetic09-glitch.github.io/ai-news-podcast"
PODCAST_TITLE = "毎朝のAIニュース"
PODCAST_DESCRIPTION = "Hacker News・Reddit・はてなブックマークから毎朝収集したAI・Techニュースを音声でお届けする自分専用ポッドキャスト。"
PODCAST_AUTHOR = "rinrin"
LANGUAGE = "ja"
VOICE = "ja-JP-NanamiNeural"
RATE = "+8%"          # わずかに早口（ポッドキャストアプリ側でも倍速可能）
BITRATE_BPS = 48000    # edge-tts 既定 (audio-24khz-48kbitrate-mono-mp3)
FEED_EPISODE_LIMIT = 30   # feed.xml に載せる最新エピソード数
KEEP_DAYS = 90            # これより古い mp3 は削除（リポジトリ肥大化防止）
# -----------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
EPISODES_DIR = ROOT / "episodes"
MANIFEST = ROOT / "episodes.json"
FEED = ROOT / "feed.xml"


def clean_for_tts(text: str) -> str:
    """Markdown を読み上げ可能なプレーンテキストにする。"""
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)   # [t](url) -> t
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"!\[[^\]]*\]", "", text)
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*>+\s?", "", text, flags=re.MULTILINE)
    text = re.sub(r"\[!note\][+-]?", "", text)
    text = re.sub(r"[*_`#|]", "", text)
    text = re.sub(r"<br\s*/?>", "。", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"★{1,3}|☆{1,3}", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def run_edge_tts(text: str, out_mp3: Path) -> None:
    txt = out_mp3.with_suffix(".ttstext.tmp")
    txt.write_text(text, encoding="utf-8")
    base_args = [
        "--voice", VOICE, "--rate", RATE,
        "--file", str(txt), "--write-media", str(out_mp3),
    ]
    candidates = []
    if shutil.which("edge-tts"):
        candidates.append(["edge-tts"])
    candidates.append([sys.executable, "-m", "edge_tts"])
    if shutil.which("uvx"):
        candidates.append(["uvx", "edge-tts"])
    last_err = None
    try:
        for cmd in candidates:
            try:
                subprocess.run(cmd + base_args, check=True, capture_output=True,
                               text=True, timeout=600)
                return
            except (subprocess.CalledProcessError, FileNotFoundError,
                    subprocess.TimeoutExpired) as e:
                last_err = e
        raise RuntimeError(f"edge-tts の実行に失敗しました: {last_err}")
    finally:
        txt.unlink(missing_ok=True)


def run_gtts(text: str, out_mp3: Path) -> None:
    """HTTPのみで動くフォールバックTTS（クラウド環境はWebSocket不可のため）。"""
    from gtts import gTTS
    with out_mp3.open("wb") as f:
        gTTS(text=text, lang="ja").write_to_fp(f)


def synthesize(text: str, out_mp3: Path) -> str:
    """edge-tts優先、失敗したらgTTS。使ったエンジン名を返す。"""
    try:
        run_edge_tts(text, out_mp3)
        return "edge-tts"
    except Exception as e:
        print(f"edge-tts失敗、gTTSにフォールバック: {e}", file=sys.stderr)
    run_gtts(text, out_mp3)
    return "gtts"


def mp3_seconds(path: Path) -> int:
    try:
        import mutagen
        info = mutagen.File(str(path))
        return int(info.info.length)
    except Exception:
        return int(path.stat().st_size * 8 / BITRATE_BPS)


MIME_TYPES = {".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".wav": "audio/wav"}


def fmt_duration(seconds: int) -> str:
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{s:02d}"


def rfc2822(date_str: str) -> str:
    d = datetime.datetime.strptime(date_str, "%Y-%m-%d").replace(
        hour=7, minute=0, tzinfo=datetime.timezone(datetime.timedelta(hours=9))
    )
    return d.strftime("%a, %d %b %Y %H:%M:%S %z")


def load_manifest() -> list:
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    return []


def build_feed(episodes: list) -> str:
    items = []
    for ep in episodes[:FEED_EPISODE_LIMIT]:
        desc = html.escape(ep.get("description", ""))
        items.append(f"""    <item>
      <title>{html.escape(ep["title"])}</title>
      <description>{desc}</description>
      <pubDate>{rfc2822(ep["date"])}</pubDate>
      <enclosure url="{BASE_URL}/episodes/{ep["file"]}" length="{ep["bytes"]}" type="{ep.get("type", "audio/mpeg")}"/>
      <guid isPermaLink="false">{ep["file"]}</guid>
      <itunes:duration>{fmt_duration(ep["seconds"])}</itunes:duration>
    </item>""")
    items_xml = "\n".join(items)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{html.escape(PODCAST_TITLE)}</title>
    <link>{BASE_URL}/</link>
    <description>{html.escape(PODCAST_DESCRIPTION)}</description>
    <language>{LANGUAGE}</language>
    <itunes:author>{html.escape(PODCAST_AUTHOR)}</itunes:author>
    <itunes:image href="{BASE_URL}/cover.png"/>
    <itunes:explicit>false</itunes:explicit>
    <itunes:category text="News"><itunes:category text="Tech News"/></itunes:category>
    <atom:link href="{BASE_URL}/feed.xml" rel="self" type="application/rss+xml"/>
{items_xml}
  </channel>
</rss>
"""


def prune_old(episodes: list) -> list:
    cutoff = (datetime.date.today() - datetime.timedelta(days=KEEP_DAYS)).isoformat()
    kept = []
    for ep in episodes:
        if ep["date"] < cutoff:
            (EPISODES_DIR / ep["file"]).unlink(missing_ok=True)
            md = (EPISODES_DIR / ep["file"]).with_suffix(".md")
            md.unlink(missing_ok=True)
        else:
            kept.append(ep)
    return kept


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("script_file", help="原稿/ショーノート (txt/md)")
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    ap.add_argument("--title", default=None)
    ap.add_argument("--description", default=None)
    ap.add_argument("--audio", default=None,
                    help="既存の音声ファイル (m4a/mp3等)。指定時はTTSせずこれを使う")
    args = ap.parse_args()

    src = Path(args.script_file)
    raw = src.read_text(encoding="utf-8")

    title = args.title or f"{args.date} AIニュース"
    EPISODES_DIR.mkdir(exist_ok=True)

    if args.audio:
        audio_src = Path(args.audio)
        ext = audio_src.suffix.lower()
        if ext not in MIME_TYPES:
            sys.exit(f"未対応の音声形式です: {ext}")
        audio = EPISODES_DIR / f"{args.date}{ext}"
        shutil.copyfile(audio_src, audio)
        print(f"音声を取り込み: {audio_src} → {audio.name}")
    else:
        text = clean_for_tts(raw)
        if not text:
            sys.exit("原稿が空です")
        audio = EPISODES_DIR / f"{args.date}.mp3"
        print(f"TTS 生成中: {len(text)} 文字 → {audio.name}")
        engine = synthesize(text, audio)
        print(f"TTSエンジン: {engine}")

    size = audio.stat().st_size
    seconds = mp3_seconds(audio)

    # ショーノート（原稿そのもの）も残す
    (EPISODES_DIR / f"{args.date}.md").write_text(raw, encoding="utf-8")

    episodes = load_manifest()
    # 同日の旧エピソード（拡張子違いを含む）を削除
    for e in episodes:
        if e["date"] == args.date and e["file"] != audio.name:
            (EPISODES_DIR / e["file"]).unlink(missing_ok=True)
    episodes = [e for e in episodes if e["date"] != args.date]
    episodes.append({
        "date": args.date,
        "title": title,
        "description": args.description or f"{args.date} のAI・Techニュースまとめ。",
        "file": audio.name,
        "bytes": size,
        "seconds": seconds,
        "type": MIME_TYPES[audio.suffix.lower()],
    })
    episodes.sort(key=lambda e: e["date"], reverse=True)
    episodes = prune_old(episodes)

    MANIFEST.write_text(json.dumps(episodes, ensure_ascii=False, indent=2), encoding="utf-8")
    FEED.write_text(build_feed(episodes), encoding="utf-8")
    print(f"完了: {audio} ({size/1e6:.1f} MB, 約{seconds//60}分) / feed.xml 更新済み")


if __name__ == "__main__":
    main()
