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
import tempfile
from pathlib import Path

# ---- 設定 -------------------------------------------------------------
BASE_URL = "https://rinrinzetetic09-glitch.github.io/ai-news-podcast"
REPO = "rinrinzetetic09-glitch/ai-news-podcast"
RELEASE_TAG = "episodes"   # 音声はこのReleaseに添付する（リポジトリ本体に貯めない）
PODCAST_TITLE = "毎朝のAIニュース"
PODCAST_DESCRIPTION = "Hacker News・Reddit・はてなブックマークから毎朝収集したAI・Techニュースを音声でお届けする自分専用ポッドキャスト。"
PODCAST_AUTHOR = "rinrin"
LANGUAGE = "ja"
VOICE = "ja-JP-NanamiNeural"
RATE = "+8%"          # わずかに早口（ポッドキャストアプリ側でも倍速可能）
BITRATE_BPS = 48000    # edge-tts 既定 (audio-24khz-48kbitrate-mono-mp3)
FEED_EPISODE_LIMIT = 30   # feed.xml に載せる最新エピソード数
KEEP_DAYS = 90            # これより古い音声（Release添付）は削除
# -----------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
EPISODES_DIR = ROOT / "episodes"
MANIFEST = ROOT / "episodes.json"
FEED = ROOT / "feed.xml"
OPENING = ROOT / "assets" / "ai-news_opening.mp3"   # 各エピソード冒頭に繋ぐ音源


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


def prepend_opening(audio: Path, workdir: Path, date: str) -> Path:
    """オープニング音源を頭に繋げた m4a を返す。

    ffmpeg が必要。オープニングが無い / ffmpeg が無い / 連結失敗のときは
    パイプラインを止めず、元の音声をそのまま返す（オープニング無しで続行）。
    """
    if not OPENING.exists():
        print(f"オープニング音源が無いのでスキップ: {OPENING}", file=sys.stderr)
        return audio
    if not shutil.which("ffmpeg"):
        print("ffmpegが無いのでオープニングをスキップ（要インストール）", file=sys.stderr)
        return audio
    outdir = workdir / "combined"      # 入力(audio)と同名衝突を避ける
    outdir.mkdir(exist_ok=True)
    out = outdir / f"{date}.m4a"
    # 両者を 44.1kHz / stereo に揃えてから連結し、AAC(m4a) で書き出す
    cmd = [
        "ffmpeg", "-y", "-i", str(OPENING), "-i", str(audio),
        "-filter_complex",
        "[0:a]aformat=sample_rates=44100:channel_layouts=stereo[a0];"
        "[1:a]aformat=sample_rates=44100:channel_layouts=stereo[a1];"
        "[a0][a1]concat=n=2:v=0:a=1[out]",
        "-map", "[out]", "-c:a", "aac", "-b:a", "128k", str(out),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not out.exists():
        print(f"オープニング連結に失敗、元音声を使用: {r.stderr[-300:]}", file=sys.stderr)
        return audio
    print("オープニングを冒頭に連結しました")
    return out


def gh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args, "-R", REPO],
                          capture_output=True, text=True)


def ensure_release() -> None:
    """音声置き場の Release（タグ RELEASE_TAG）が無ければ作る。"""
    if gh("release", "view", RELEASE_TAG).returncode == 0:
        return
    r = gh("release", "create", RELEASE_TAG,
           "-t", "Podcast audio",
           "-n", "毎朝のAIニュース ポッドキャストの音声ファイル置き場。"
                 "リポジトリ肥大化を避けるため音声はここ（Releasesの添付）に保存する。")
    if r.returncode != 0:
        raise RuntimeError(f"Release作成に失敗: {r.stderr}")


def upload_audio(audio: Path) -> str:
    """音声を Release に添付し、その公開ダウンロードURLを返す。"""
    ensure_release()
    r = gh("release", "upload", RELEASE_TAG, str(audio), "--clobber")
    if r.returncode != 0:
        raise RuntimeError(f"音声アップロードに失敗: {r.stderr}")
    return f"https://github.com/{REPO}/releases/download/{RELEASE_TAG}/{audio.name}"


def delete_asset(name: str) -> None:
    gh("release", "delete-asset", RELEASE_TAG, name, "-y")


def enclosure_url(ep: dict) -> str:
    # 新方式は Release のURLを保存。旧エピソード（Pages配下のmp3）は従来URL。
    return ep.get("url") or f"{BASE_URL}/episodes/{ep['file']}"


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
      <enclosure url="{enclosure_url(ep)}" length="{ep["bytes"]}" type="{ep.get("type", "audio/mpeg")}"/>
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
            if ep.get("url"):
                delete_asset(ep["file"])          # Release添付を削除
            else:
                (EPISODES_DIR / ep["file"]).unlink(missing_ok=True)  # 旧Pages配下mp3
            (EPISODES_DIR / f"{ep['date']}.md").unlink(missing_ok=True)
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
    ap.add_argument("--no-opening", action="store_true",
                    help="冒頭のオープニング音源を連結しない")
    args = ap.parse_args()

    src = Path(args.script_file)
    raw = src.read_text(encoding="utf-8")

    title = args.title or f"{args.date} AIニュース"
    EPISODES_DIR.mkdir(exist_ok=True)

    # 音声は tmp に作り、Releaseへアップロードする（リポジトリ本体には貯めない）
    with tempfile.TemporaryDirectory() as td:
        if args.audio:
            audio_src = Path(args.audio)
            ext = audio_src.suffix.lower()
            if ext not in MIME_TYPES:
                sys.exit(f"未対応の音声形式です: {ext}")
            audio = Path(td) / f"{args.date}{ext}"
            shutil.copyfile(audio_src, audio)
            print(f"音声を取り込み: {audio_src} → {audio.name}")
        else:
            text = clean_for_tts(raw)
            if not text:
                sys.exit("原稿が空です")
            audio = Path(td) / f"{args.date}.mp3"
            print(f"TTS 生成中: {len(text)} 文字 → {audio.name}")
            engine = synthesize(text, audio)
            print(f"TTSエンジン: {engine}")

        if not args.no_opening:
            audio = prepend_opening(audio, Path(td), args.date)

        size = audio.stat().st_size
        seconds = mp3_seconds(audio)
        print(f"音声をReleaseへアップロード中… ({size/1e6:.1f} MB)")
        url = upload_audio(audio)
        asset_name = audio.name
        mime = MIME_TYPES[audio.suffix.lower()]

    # ショーノート（原稿そのもの）はテキストなのでリポジトリに残す
    (EPISODES_DIR / f"{args.date}.md").write_text(raw, encoding="utf-8")

    episodes = load_manifest()
    # 同日の旧エピソード（拡張子違い）のRelease添付を掃除
    for e in episodes:
        if e["date"] == args.date and e["file"] != asset_name and e.get("url"):
            delete_asset(e["file"])
    episodes = [e for e in episodes if e["date"] != args.date]
    episodes.append({
        "date": args.date,
        "title": title,
        "description": args.description or f"{args.date} のAI・Techニュースまとめ。",
        "file": asset_name,
        "url": url,
        "bytes": size,
        "seconds": seconds,
        "type": mime,
    })
    episodes.sort(key=lambda e: e["date"], reverse=True)
    episodes = prune_old(episodes)

    MANIFEST.write_text(json.dumps(episodes, ensure_ascii=False, indent=2), encoding="utf-8")
    FEED.write_text(build_feed(episodes), encoding="utf-8")
    print(f"完了: {url} ({size/1e6:.1f} MB, 約{seconds//60}分) / feed.xml 更新済み")


if __name__ == "__main__":
    main()
