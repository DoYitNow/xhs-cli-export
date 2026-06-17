#!/usr/bin/env python
"""Standalone Xiaohongshu favorites/likes exporter to Markdown.

Exports notes from Xiaohongshu (via xhs-cli) into structured Markdown files
with frontmatter, original text, interaction data, and optional image downloads.

Usage:
    python xhs_export.py check
    python xhs_export.py export --source likes --max 200
    python xhs_export.py export --source favorites --output-dir ./my-notes

Output structure:
    <output-dir>/
      <source>-<run-id>/
        0001-<title>--<note_id>.md
        _xhs_export_index.md
      images/<note_id>/image-01.jpg
    <state-file> (default: ./xhs_state.json)
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import mimetypes
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

INVALID_FILENAME_CHARS = r'<>:"/\|?*'
SCRIPT_DIR = Path(__file__).resolve().parent
SOURCE_LABELS = {
    "favorites": "收藏",
    "likes": "点赞",
}
STABLE_HEADLESS_XHS = Path.home() / ".xiaohongshu-cli" / "headless-venv" / "Scripts" / "xhs.exe"
LEGACY_XHS_CONFIG = Path.home() / ".xhs-cli" / "cookies.json"
HEADLESS_XHS_CONFIG = Path.home() / ".xiaohongshu-cli" / "cookies.json"


# ── Helpers ──────────────────────────────────────────────────────────────

def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def today_string() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d")


def run_id_string(run_started: dt.datetime) -> str:
    return run_started.astimezone().strftime("%Y%m%dT%H%M%S")


def safe_print(text: Any = "") -> None:
    output = str(text)
    encoding = sys.stdout.encoding or "utf-8"
    print(output.encode(encoding, errors="replace").decode(encoding, errors="replace"))


class ProgressBar:
    """Simple text progress bar using carriage return."""

    def __init__(self, total: int, label: str = "导出") -> None:
        self.total = total
        self.label = label
        self.current = 0
        self._last_len = 0

    def update(self, n: int = 1, suffix: str = "") -> None:
        self.current += n
        if self.total <= 0:
            return
        pct = self.current * 100 // self.total
        bar_width = 30
        filled = bar_width * self.current // self.total
        bar = "█" * filled + "░" * (bar_width - filled)
        line = f"\r  {self.label} {bar} {pct}%  {self.current}/{self.total}"
        if suffix:
            line += f"  {suffix}"
        padding = max(0, self._last_len - len(line))
        sys.stdout.write(line + " " * padding)
        sys.stdout.flush()
        self._last_len = len(line)

    def finish(self, suffix: str = "") -> None:
        self.current = self.total
        self.update(0, suffix)
        sys.stdout.write("\n")
        sys.stdout.flush()


def _resolve_existing_path(value: str | Path) -> Path | None:
    path = Path(value).expanduser()
    return path if path.exists() else None


def find_xhs(explicit: str | None = None) -> str:
    """Find the preferred xhs executable.

    Prefer the patched headless venv used by this exporter. The global
    `xhs.exe` may still point to legacy xhs-cli 0.1.x, whose `status`
    command can report stale cookies as logged in.
    """
    if explicit:
        path = _resolve_existing_path(explicit)
        if path:
            return str(path)
        raise FileNotFoundError(f"xhs binary not found: {explicit}")

    env_path = os.environ.get("XHS_EXPORT_XHS_BIN") or os.environ.get("XHS_BIN")
    if env_path:
        path = _resolve_existing_path(env_path)
        if path:
            return str(path)
        raise FileNotFoundError(f"XHS_EXPORT_XHS_BIN points to a missing file: {env_path}")

    stable = _resolve_existing_path(STABLE_HEADLESS_XHS)
    if stable:
        return str(stable)

    found = shutil.which("xhs") or shutil.which("xhs.exe")
    if found:
        return found

    candidates = sorted(
        Path.home().glob("AppData/Roaming/Python/Python*/Scripts/xhs.exe"),
        reverse=True,
    )
    if candidates:
        return str(candidates[0])

    raise FileNotFoundError(
        "xhs executable not found. Install xhs-cli-headless or pass --xhs-bin."
    )


def xhs_command(xhs_bin: str, args: list[str]) -> list[str]:
    """Build a subprocess command for exe/cmd/ps1 wrappers."""
    path = Path(xhs_bin)
    suffix = path.suffix.lower()
    if suffix == ".ps1":
        return ["powershell", "-ExecutionPolicy", "Bypass", "-File", xhs_bin, *args]
    if suffix in {".cmd", ".bat"}:
        return ["cmd", "/c", xhs_bin, *args]
    return [xhs_bin, *args]


def run_xhs(
    xhs_bin: str,
    args: list[str],
    *,
    check: bool = True,
    cwd: str | None = None,
) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    proc = subprocess.run(
        xhs_command(xhs_bin, args),
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and proc.returncode != 0:
        message = proc.stderr.strip() or proc.stdout.strip() or f"xhs exited {proc.returncode}"
        raise RuntimeError(message)
    return proc


def parse_xhs_json(proc: subprocess.CompletedProcess) -> Any:
    text = (proc.stdout or proc.stderr or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def xhs_version_text(xhs_bin: str) -> str:
    version = run_xhs(xhs_bin, ["--version"], check=False)
    return (version.stdout or version.stderr or "").strip()


def is_headless_xhs(xhs_bin: str) -> bool:
    text = xhs_version_text(xhs_bin).lower()
    return "0.8." in text or "xhs, version" in text


def load_json_file(path: Path) -> Any:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-16", "gb18030"):
        try:
            return json.loads(raw.decode(encoding))
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass
    raise json.JSONDecodeError(f"Cannot decode JSON file with supported encodings: {path}", "", 0)


# ── Data helpers ─────────────────────────────────────────────────────────

def coerce_notes(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("notes", "data", "items", "list", "favorites", "likes"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = coerce_notes(value)
            if nested:
                return nested
    return []


def pick(mapping: dict[str, Any] | None, *keys: str, default: Any = "") -> Any:
    if not isinstance(mapping, dict):
        return default
    for key in keys:
        value = mapping.get(key)
        if value not in (None, ""):
            return value
    return default


def first_value(*values: Any, default: Any = "") -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return default


def note_card(item: dict[str, Any]) -> dict[str, Any]:
    card = pick(item, "note_card", "noteCard", "card", "note", default={})
    return card if isinstance(card, dict) and card else item


def user_block(*sources: dict[str, Any]) -> dict[str, Any]:
    for source in sources:
        user = pick(source, "user", "noteUser", "userInfo", "user_info", default={})
        if isinstance(user, dict) and user:
            return user
    return {}


def interact_block(*sources: dict[str, Any]) -> dict[str, Any]:
    for source in sources:
        interact = pick(source, "interactInfo", "interact_info", default={})
        if isinstance(interact, dict) and interact:
            return interact
    return {}


def normalize_detail(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    if payload.get("schema_version") and "data" in payload:
        return normalize_detail(payload.get("data"))
    data = payload.get("data")
    if isinstance(data, dict):
        nested = normalize_detail(data)
        if nested:
            return nested
    note = payload.get("note", payload)
    if isinstance(note, dict) and isinstance(note.get("note"), dict):
        note = note["note"]
    if isinstance(note, dict):
        card = pick(note, "note_card", "noteCard", "card", default={})
        if isinstance(card, dict) and card:
            return card
        items = note.get("items")
        if isinstance(items, list):
            for item in items:
                nested = normalize_detail(item)
                if nested:
                    return nested
        if any(key in note for key in (
            "desc", "description", "imageList", "image_list",
            "title", "displayTitle", "display_title", "noteId", "note_id",
        )):
            return note
    return {}


def note_id_from(item: dict[str, Any], detail: dict[str, Any] | None = None) -> str:
    card = note_card(item)
    return str(
        first_value(
            pick(item, "noteId", "note_id", "id"),
            pick(card, "noteId", "note_id", "id"),
            pick(detail or {}, "noteId", "note_id", "id"),
        )
    )


def xsec_token_from(item: dict[str, Any]) -> str:
    card = note_card(item)
    return str(
        first_value(
            pick(item, "xsec_token", "xsecToken"),
            pick(card, "xsec_token", "xsecToken"),
        )
    )


def sanitize_filename(value: str, *, fallback: str) -> str:
    value = value.strip() or fallback
    for char in INVALID_FILENAME_CHARS:
        value = value.replace(char, " ")
    value = re.sub(r"[\x00-\x1f]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip(" .")
    return (value or fallback)[:90]


def yaml_scalar(value: Any) -> str:
    text = str(value or "")
    return json.dumps(text, ensure_ascii=False)


def compact_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# ── Timestamp handling ───────────────────────────────────────────────────

def parse_timestamp(value: Any) -> dt.datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        seconds = float(value)
        if seconds > 10_000_000_000:
            seconds = seconds / 1000.0
        try:
            return dt.datetime.fromtimestamp(seconds, tz=dt.timezone.utc).replace(microsecond=0)
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value).strip()
    if not text:
        return None
    if re.fullmatch(r"\d{10,13}", text):
        return parse_timestamp(int(text))
    normalized = text.replace("Z", "+00:00")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            parsed = dt.datetime.strptime(text, fmt)
            return parsed.astimezone().astimezone(dt.timezone.utc).replace(microsecond=0)
        except ValueError:
            pass
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed.astimezone(dt.timezone.utc).replace(microsecond=0)


def find_timestamp_by_keys(node: Any, keys: set[str]) -> Any:
    if isinstance(node, dict):
        for key, value in node.items():
            if key.lower() in keys and value not in (None, ""):
                return value
        for value in node.values():
            found = find_timestamp_by_keys(value, keys)
            if found not in (None, ""):
                return found
    elif isinstance(node, list):
        for item in node:
            found = find_timestamp_by_keys(item, keys)
            if found not in (None, ""):
                return found
    return None


def action_timestamp_for(source: str, item: dict[str, Any], detail: dict[str, Any] | None = None) -> dt.datetime | None:
    if source == "favorites":
        keys = {"collecttime", "collect_time", "collectedtime", "collected_time",
                "collectiontime", "favorite_time", "favoritetime"}
    else:
        keys = {"liketime", "like_time", "likedtime", "liked_time", "likedat", "liked_at"}
    value = find_timestamp_by_keys(item, keys)
    if value in (None, "") and detail:
        value = find_timestamp_by_keys(detail, keys)
    return parse_timestamp(value)


# ── Media / images ───────────────────────────────────────────────────────

def is_media_url(value: str) -> bool:
    if not value.startswith(("http://", "https://")):
        return False
    if "/explore/" in value or "/user/profile/" in value:
        return False
    return (
        "xhscdn" in value
        or "xiaohongshu" in value
        or re.search(r"\.(jpg|jpeg|png|webp|gif|png!|avif)(\?|$)", value, re.I) is not None
    )


def image_url_from_node(node: Any) -> str:
    if isinstance(node, str):
        return node if is_media_url(node) else ""
    if not isinstance(node, dict):
        return ""

    for key in ("url_default", "urlDefault", "url", "url_pre", "urlPre"):
        value = node.get(key)
        if isinstance(value, str) and is_media_url(value):
            return value

    info_list = node.get("info_list") or node.get("infoList") or []
    if isinstance(info_list, list):
        candidates: list[tuple[int, str]] = []
        for info in info_list:
            if not isinstance(info, dict):
                continue
            url = info.get("url")
            if not isinstance(url, str) or not is_media_url(url):
                continue
            scene = str(info.get("image_scene") or info.get("imageScene") or "").upper()
            priority = 0
            if "DFT" in scene or "DEFAULT" in scene or "ORIGIN" in scene:
                priority = 2
            elif "PRV" in scene or "PRE" in scene:
                priority = 1
            candidates.append((priority, url))
        if candidates:
            candidates.sort(key=lambda item: item[0], reverse=True)
            return candidates[0][1]

    return ""


def looks_like_image_node(node: dict[str, Any]) -> bool:
    image_keys = {"url_default", "urlDefault", "url_pre", "urlPre", "info_list", "infoList"}
    container_keys = {"items", "data", "note", "note_card", "noteCard", "image_list", "imageList"}
    return bool(image_keys.intersection(node)) and not bool(container_keys.intersection(node))


def extract_media_urls(value: Any) -> list[str]:
    urls: list[str] = []

    def visit(node: Any) -> None:
        if isinstance(node, str):
            if is_media_url(node):
                urls.append(node)
            return
        if isinstance(node, list):
            for child in node:
                visit(child)
            return
        if isinstance(node, dict):
            if looks_like_image_node(node):
                url = image_url_from_node(node)
                if url:
                    urls.append(url)
                return
            for key, child in node.items():
                lower = key.lower()
                if (lower in {"url", "link", "urlpre", "urldefault", "url_default", "url_pre"}
                        or "image" in lower or "img" in lower
                        or lower in {"infolist", "info_list", "items", "data", "note", "note_card", "notecard"}):
                    visit(child)

    visit(value)
    seen: set[str] = set()
    deduped: list[str] = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            deduped.append(url)
    return deduped


def note_has_embedded_detail(item: dict[str, Any]) -> bool:
    if item.get("_detail_fetched") or item.get("detail_fetched"):
        return True
    card = note_card(item)
    image_value = first_value(
        pick(card, "image_list", "imageList"),
        pick(item, "image_list", "imageList"),
        default=[],
    )
    if isinstance(image_value, list) and len(image_value) > 1:
        return True
    has_desc = bool(compact_text(first_value(pick(card, "desc", "description"), pick(item, "desc", "description"))))
    has_token = bool(xsec_token_from(item))
    return has_desc and not has_token and bool(extract_media_urls(card or item))


def extension_from_response(url: str, content_type: str) -> str:
    parsed_suffix = Path(urlparse(url).path).suffix.lower()
    if parsed_suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"}:
        return parsed_suffix
    guessed = mimetypes.guess_extension(content_type.split(";")[0].strip())
    if guessed in {".jpe"}:
        return ".jpg"
    return guessed if guessed in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"} else ".jpg"


def download_images(
    urls: list[str],
    *,
    target_dir: Path,
    max_images: int,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    if not urls or max_images <= 0:
        return [], []
    import requests

    target_dir.mkdir(parents=True, exist_ok=True)
    saved: list[dict[str, str]] = []
    failed: list[dict[str, str]] = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.xiaohongshu.com/",
    }

    for url in urls:
        if len(saved) >= max_images:
            break
        try:
            response = requests.get(url, headers=headers, timeout=20, stream=True)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if "image" not in content_type.lower():
                failed.append({"url": url, "reason": f"not image: {content_type or 'unknown'}"})
                continue
            ext = extension_from_response(url, content_type)
            file_path = target_dir / f"image-{len(saved) + 1:02d}{ext}"
            with file_path.open("wb") as file:
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    if chunk:
                        file.write(chunk)
            saved.append({
                "url": url,
                "path": file_path.as_posix(),
                "content_type": content_type,
            })
        except Exception as exc:
            failed.append({"url": url, "reason": str(exc)})
    return saved, failed


# ── Markdown generation ──────────────────────────────────────────────────

def markdown_for_note(
    item: dict[str, Any],
    detail: dict[str, Any],
    *,
    captured_date: str,
    run_started_iso: str,
    window_start_iso: str,
    source: str,
    source_label: str,
    increment_reason: str,
    saved_images: list[dict[str, str]],
    failed_images: list[dict[str, str]],
    include_media_urls: bool,
    output_base: Path,
) -> tuple[str, str]:
    card = note_card(item)
    user = user_block(detail, card, item)
    interact = interact_block(detail, card, item)
    note_id = note_id_from(item, detail)
    title = str(
        first_value(
            pick(detail, "title", "displayTitle", "display_title"),
            pick(card, "displayTitle", "display_title", "title"),
            f"小红书{source_label}-{note_id or 'unknown'}",
        )
    ).strip()
    desc = compact_text(first_value(pick(detail, "desc", "description"), pick(card, "desc", "description")))
    author = str(pick(user, "nickname", "nick_name", "name", default="")).strip()
    note_type = str(first_value(pick(detail, "type", "noteType"), pick(card, "type", "noteType"), default="")).strip()
    source_url = f"https://www.xiaohongshu.com/explore/{note_id}" if note_id else ""
    action_ts = action_timestamp_for(source, item, detail)
    action_ts_iso = action_ts.isoformat() if action_ts else ""

    filename = sanitize_filename(f"{title}--{note_id}" if note_id else title, fallback="xhs-note")
    media_urls = extract_media_urls(detail or card or item) if include_media_urls else []

    # Make image paths relative to the output base
    rel_images = []
    for img in saved_images:
        try:
            rel = Path(img["path"]).relative_to(output_base).as_posix()
        except ValueError:
            rel = img["path"]
        rel_images.append({"path": rel, "url": img["url"]})

    frontmatter = [
        "---",
        "type: xhs_capture",
        "status: needs-review",
        f"created: {captured_date}",
        f"updated: {captured_date}",
        f"captured_at: {captured_date}",
        "source: xiaohongshu",
        f"xhs_export_source: {source}",
        f"xhs_export_source_label: {yaml_scalar(source_label)}",
        f"xhs_imported_at: {yaml_scalar(run_started_iso)}",
        f"xhs_increment_window_start: {yaml_scalar(window_start_iso)}",
        f"xhs_increment_window_end: {yaml_scalar(run_started_iso)}",
        f"xhs_increment_reason: {yaml_scalar(increment_reason)}",
        f"xhs_action_timestamp: {yaml_scalar(action_ts_iso)}",
        f"source_url: {yaml_scalar(source_url)}",
        f"xhs_note_id: {yaml_scalar(note_id)}",
        f"xhs_note_type: {yaml_scalar(note_type)}",
        f"author: {yaml_scalar(author)}",
        "tags: [source/xiaohongshu]",
        "---",
        "",
    ]

    lines = [
        *frontmatter,
        f"# {title}",
        "",
        "## 捕获摘要",
        "",
        f"- 导出来源: {source_label} (`{source}`)",
        f"- 来源: {'[小红书笔记](' + source_url + ')' if source_url else '未知'}",
        f"- 作者: {author or '未知'}",
        f"- 笔记 ID: {note_id or '未知'}",
        f"- 笔记类型: {note_type or '未知'}",
        f"- 导入时间: {run_started_iso}",
        f"- 增量窗口: {window_start_iso or '首次运行 / 无历史时间戳'} → {run_started_iso}",
        f"- 增量原因: {increment_reason}",
        "",
        "## 原文",
        "",
        desc or "未知",
        "",
        "## 互动数据",
        "",
        "| 指标 | 数值 |",
        "|---|---:|",
        f"| 点赞 | {pick(interact, 'likedCount', 'liked_count', default='未知')} |",
        f"| 收藏 | {pick(interact, 'collectedCount', 'collected_count', default='未知')} |",
        f"| 评论 | {pick(interact, 'commentCount', 'comment_count', default='未知')} |",
        f"| 分享 | {pick(interact, 'shareCount', 'share_count', default='未知')} |",
        "",
    ]

    lines.extend(["## 已保存图片", ""])
    if rel_images:
        lines.extend([f"- ![[{image['path']}]]" for image in rel_images])
    else:
        lines.append("无已保存图片。")

    if failed_images:
        lines.extend(["", "### 图片下载失败", "", "| URL | 原因 |", "|---|---|"])
        lines.extend([f"| {failure['url']} | {failure['reason']} |" for failure in failed_images[:20]])

    if media_urls:
        lines.extend(["", "## 远程图片 URL", ""])
        lines.extend([f"- {url}" for url in media_urls])

    lines.extend(["", ""])

    return filename + ".md", "\n".join(lines)


# ── State management ─────────────────────────────────────────────────────

def load_state(state_file: Path) -> dict[str, Any]:
    if not state_file.exists():
        return {"version": 1, "sources": {}}
    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"version": 1, "sources": {}}
        data.setdefault("version", 1)
        data.setdefault("sources", {})
        return data
    except json.JSONDecodeError:
        return {"version": 1, "sources": {}}


def save_state(state: dict[str, Any], state_file: Path) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def reset_source_state(source: str, state_file: Path) -> None:
    state = load_state(state_file)
    state.setdefault("sources", {}).pop(source, None)
    save_state(state, state_file)


def filter_incremental_notes(
    notes: list[dict[str, Any]],
    *,
    source: str,
    state: dict[str, Any],
    run_started: dt.datetime,
    all_history: bool,
) -> tuple[list[tuple[dict[str, Any], str]], str, list[str]]:
    source_state = state.setdefault("sources", {}).setdefault(source, {})
    window_start_iso = str(source_state.get("last_success_at", "") or "")
    window_start = parse_timestamp(window_start_iso)
    seen_note_ids = set(source_state.get("seen_note_ids", []))
    selected: list[tuple[dict[str, Any], str]] = []
    skipped: list[str] = []

    for item in notes:
        note_id = note_id_from(item)
        action_ts = action_timestamp_for(source, item)

        if all_history or window_start is None:
            reason = "all_history" if all_history else "first_run_no_previous_timestamp"
            selected.append((item, reason))
            continue

        if action_ts:
            if window_start < action_ts <= run_started:
                selected.append((item, f"action_timestamp_between_runs:{action_ts.isoformat()}"))
            else:
                skipped.append(note_id or "(unknown)")
            continue

        if note_id and note_id not in seen_note_ids:
            selected.append((item, "new_note_id_no_action_timestamp"))
        else:
            skipped.append(note_id or "(unknown)")

    return selected, window_start_iso, skipped


def update_incremental_state(
    state: dict[str, Any],
    *,
    source: str,
    run_started_iso: str,
    output_dir: Path,
    notes: list[dict[str, Any]],
    exported_count: int,
    state_file: Path,
) -> None:
    source_state = state.setdefault("sources", {}).setdefault(source, {})
    seen = set(source_state.get("seen_note_ids", []))
    for item in notes:
        nid = note_id_from(item)
        if nid:
            seen.add(nid)
    source_state["last_success_at"] = run_started_iso
    source_state["seen_note_ids"] = sorted(seen)
    runs = source_state.setdefault("runs", [])
    runs.append({
        "run_at": run_started_iso,
        "source": source,
        "output_dir": str(output_dir),
        "exported_count": exported_count,
        "seen_count": len(seen),
    })
    source_state["runs"] = runs[-20:]
    save_state(state, state_file)


# ── Export logic ─────────────────────────────────────────────────────────

def _drain_stream(stream: Any, target: "queue.Queue[str]") -> None:
    if stream is None:
        return
    for line in stream:
        target.put(line.rstrip("\n"))


def fetch_source_payload(args: argparse.Namespace, xhs_bin: str) -> tuple[Any, str, bool]:
    """Fetch notes from xhs CLI using streaming NDJSON.

    Each note is parsed and saved immediately to a JSONL file so that
    progress is never lost even if the process is interrupted.
    """
    if args.input_json:
        payload = load_json_file(Path(args.input_json))
        return payload, json.dumps(payload, ensure_ascii=False, indent=2), True

    source_label = SOURCE_LABELS[args.source]
    safe_print(f"正在从小红书获取{source_label}数据（流式加载中）...")
    safe_print("提示: 如有验证码弹窗，请在弹出的浏览器窗口中手动处理。")
    safe_print("")

    # Prepare incremental JSONL save file
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = output_dir / f"{args.source}_stream.jsonl"
    # Clear previous stream file
    jsonl_path.write_text("", encoding="utf-8")

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    if args.fetch_details:
        full_args = [args.source, "--max", str(args.max), "--json"]
        safe_print("完整详情模式：将逐条打开笔记以获取正文和全部图片，耗时会明显更长。")
        proc = subprocess.run(
            xhs_command(xhs_bin, full_args),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        stderr_text = (proc.stderr or "").strip()
        if stderr_text:
            preview = "\n".join(stderr_text.splitlines()[-8:])
            safe_print(f"⚠ xhs 信息:\n{preview[:1000]}")
        if proc.returncode != 0:
            raise RuntimeError(stderr_text or (proc.stdout or "").strip() or f"xhs exited {proc.returncode}")
        payload = parse_xhs_json(proc)
        if payload is None:
            raise RuntimeError("无法解析 xhs JSON 输出。")
        collected_notes = coerce_notes(payload)
        if not collected_notes:
            raise RuntimeError(
                f"未能加载任何{source_label}笔记。请检查登录状态，或尝试在浏览器中手动完成验证码。"
            )
        with jsonl_path.open("w", encoding="utf-8") as f:
            for note in collected_notes:
                f.write(json.dumps(note, ensure_ascii=False) + "\n")
        safe_print(f"✅ 已加载并保存 {len(collected_notes)} 条笔记到: {jsonl_path}")
        result = {"notes": collected_notes}
        raw_stdout = json.dumps(result, ensure_ascii=False, indent=2)
        return result, raw_stdout, True

    proc = subprocess.Popen(
        xhs_command(xhs_bin, [args.source, "--max", str(args.max), "--json", "--stream", "--no-detail"]),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    collected_notes: list[dict[str, Any]] = []
    line_num = 0
    progress = ProgressBar(args.max, label=f"加载{source_label}")
    stderr_lines: "queue.Queue[str]" = queue.Queue()
    stderr_thread = threading.Thread(target=_drain_stream, args=(proc.stderr, stderr_lines), daemon=True)
    stderr_thread.start()

    try:
        if proc.stdout is None:
            raise RuntimeError("无法读取 xhs 输出。")
        for line in proc.stdout:
            line_num += 1
            line = line.strip()
            if not line:
                continue

            # Skip non-JSON lines (progress messages from xhs-cli)
            if not line.startswith("{"):
                continue

            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Extract notes from the parsed object
            notes_batch = coerce_notes(obj) if isinstance(obj, (dict, list)) else []
            if not notes_batch and isinstance(obj, dict):
                # Single note object (typical NDJSON format)
                if "noteId" in obj or "note_id" in obj or "title" in obj:
                    notes_batch = [obj]

            if not notes_batch:
                continue

            # Save each note immediately to JSONL
            with jsonl_path.open("a", encoding="utf-8") as f:
                for note in notes_batch:
                    f.write(json.dumps(note, ensure_ascii=False) + "\n")
                    collected_notes.append(note)

            progress.total = max(progress.total, len(collected_notes))
            progress.current = len(collected_notes)
            progress.update(0, suffix=f"已加载 {len(collected_notes)} 条")
    finally:
        if proc.stdout:
            proc.stdout.close()
        proc.wait()
        stderr_thread.join(timeout=2)

    progress.finish(suffix=f"共加载 {len(collected_notes)} 条")

    stderr_text = "\n".join(line for line in list(stderr_lines.queue) if line.strip()).strip()
    if stderr_text:
        preview = "\n".join(stderr_text.splitlines()[-8:])
        safe_print(f"⚠ xhs 信息:\n{preview[:1000]}")

    fetch_complete = proc.returncode == 0
    if proc.returncode != 0:
        message = stderr_text or f"xhs exited {proc.returncode}"
        if collected_notes:
            safe_print(
                f"⚠ xhs 提前退出，已保留 {len(collected_notes)} 条流式结果；"
                "本次不会更新增量成功 checkpoint。"
            )
        else:
            raise RuntimeError(message)

    if not collected_notes:
        raise RuntimeError(
            f"未能加载任何{source_label}笔记。请检查登录状态，或尝试在浏览器中手动完成验证码。"
        )

    safe_print(f"✅ 已加载并保存 {len(collected_notes)} 条笔记到: {jsonl_path}")

    # Reconstruct the standard JSON format for compatibility
    result = {"notes": collected_notes}
    raw_stdout = json.dumps(result, ensure_ascii=False, indent=2)
    return result, raw_stdout, fetch_complete


def _write_export_index(
    *,
    run_dir: Path,
    source: str,
    source_label: str,
    captured_date: str,
    run_started_iso: str,
    window_start_iso: str,
    fetch_details: bool,
    save_images: bool,
    notes_count: int,
    generated: list[Path],
    skipped: list[str],
    detail_failures: list[dict[str, str]],
) -> None:
    """Write the _xhs_export_index.md file (shared by streaming and non-streaming paths)."""
    index_lines = [
        "---",
        "type: xhs_export_index",
        "status: needs-review",
        f"created: {captured_date}",
        f"updated: {captured_date}",
        "source: xiaohongshu",
        f"xhs_export_source: {source}",
        "---",
        "",
        f"# 小红书{source_label}导出索引 - {captured_date}",
        "",
        f"- 运行时间: `{run_started_iso}`",
        f"- 增量窗口起点: `{window_start_iso or '首次运行 / 无历史时间戳'}`",
        f"- 增量窗口终点: `{run_started_iso}`",
        f"- 获取详情: `{fetch_details}`",
        f"- 保存图片: `{save_images}`",
        f"- 加载笔记数: {notes_count}",
        f"- 生成捕获数: {len(generated)}",
        f"- 因状态/时间戳跳过: {len(skipped)}",
        "",
        "## 生成的文件",
        "",
        "| 文件 |",
        "|---|",
    ]
    index_lines.extend([f"| `{path.name}` |" for path in generated])

    if detail_failures:
        index_lines.extend(["", "## 详情获取失败", "", "| 笔记 ID | 原因 |", "|---|---|"])
        index_lines.extend([f"| {failure['note_id']} | {failure['reason']} |" for failure in detail_failures])

    (run_dir / "_xhs_export_index.md").write_text("\n".join(index_lines) + "\n", encoding="utf-8")


def _export_notes_streaming(
    *,
    args: argparse.Namespace,
    xhs_bin: str,
    source: str,
    source_label: str,
    output_dir: Path,
    run_dir: Path,
    image_root: Path,
    state_file: Path,
    run_started: dt.datetime,
    run_started_iso: str,
    run_id: str,
    captured_date: str,
) -> None:
    """Streaming detail export: fetch list via NDJSON, export each note immediately."""
    state = load_state(state_file)
    source_state = state.setdefault("sources", {}).setdefault(source, {})
    window_start_iso = str(source_state.get("last_success_at", "") or "")
    window_start = parse_timestamp(window_start_iso)
    seen_note_ids = set(source_state.get("seen_note_ids", []))

    run_dir.mkdir(parents=True, exist_ok=True)
    if args.save_images:
        image_root.mkdir(parents=True, exist_ok=True)

    safe_print(f"正在流式获取{source_label}数据，每条笔记获取后立即导出...")

    # Prepare incremental JSONL save file for crash recovery
    jsonl_path = output_dir / f"{source}_stream.jsonl"
    jsonl_path.write_text("", encoding="utf-8")

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    # Auto-retry loop: re-run CLI if it stopped early (browser scroll fallback
    # can hit MAX_STALE and stop before fetching all notes).
    MAX_RETRIES = 5
    RETRY_WAIT = 3  # seconds between retries
    collected_notes: list[dict[str, Any]] = []
    generated: list[Path] = []
    skipped: list[str] = []
    detail_failures: list[dict[str, str]] = []
    export_index = 0
    all_run_note_ids: set[str] = set(seen_note_ids)  # dedup across retries, seeded with prior state
    fetch_complete = False
    attempt = 0

    while attempt <= MAX_RETRIES:
        attempt += 1
        if attempt > 1:
            safe_print(f"\n--- 第 {attempt} 次获取（共已导出 {len(generated)} 条）---")
            import time
            time.sleep(RETRY_WAIT)

        proc = subprocess.Popen(
            xhs_command(xhs_bin, [source, "--max", str(args.max), "--json", "--stream", "--no-detail"]),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        run_new_count = 0
        stderr_lines: "queue.Queue[str]" = queue.Queue()
        stderr_thread = threading.Thread(target=_drain_stream, args=(proc.stderr, stderr_lines), daemon=True)
        stderr_thread.start()
        progress = ProgressBar(args.max, label=f"导出{source_label}")

        try:
            if proc.stdout is None:
                raise RuntimeError("无法读取 xhs 输出。")
            for line in proc.stdout:
                line = line.strip()
                if not line or not line.startswith("{"):
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                notes_batch = coerce_notes(obj) if isinstance(obj, (dict, list)) else []
                if not notes_batch and isinstance(obj, dict):
                    if "noteId" in obj or "note_id" in obj or "title" in obj:
                        notes_batch = [obj]
                if not notes_batch:
                    continue

                # Append each note to JSONL for crash recovery
                with jsonl_path.open("a", encoding="utf-8") as jf:
                    for note in notes_batch:
                        jf.write(json.dumps(note, ensure_ascii=False) + "\n")

                for item in notes_batch:
                    note_id = note_id_from(item)

                    # Dedup across retries
                    if note_id and note_id in all_run_note_ids:
                        continue
                    if note_id:
                        all_run_note_ids.add(note_id)

                    # Incremental filter
                    if not args.all_history and window_start is not None:
                        action_ts = action_timestamp_for(source, item)
                        if action_ts:
                            if not (window_start < action_ts <= run_started):
                                skipped.append(note_id or "(unknown)")
                                collected_notes.append(item)
                                continue
                        elif note_id and note_id in seen_note_ids:
                            skipped.append(note_id or "(unknown)")
                            collected_notes.append(item)
                            continue

                    collected_notes.append(item)
                    export_index += 1
                    run_new_count += 1

                    # Fetch detail
                    detail: dict[str, Any] = {}
                    detail_payload: Any = {}
                    token = xsec_token_from(item)
                    if note_id and not note_has_embedded_detail(item):
                        try:
                            detail_args = ["read", note_id, "--json"]
                            if token:
                                detail_args.extend(["--xsec-token", token])
                            proc_detail = run_xhs(xhs_bin, detail_args)
                            detail_payload = json.loads(proc_detail.stdout)
                            detail = normalize_detail(detail_payload)
                            detail_path = run_dir / "details"
                            detail_path.mkdir(parents=True, exist_ok=True)
                            (detail_path / f"{note_id}.json").write_text(
                                json.dumps(detail_payload, ensure_ascii=False, indent=2), encoding="utf-8",
                            )
                        except Exception as exc:
                            detail = {"export_error": str(exc)}
                            detail_failures.append({"note_id": note_id, "reason": str(exc)})

                    # Download images
                    media_urls = extract_media_urls(detail or detail_payload or item)
                    saved_images: list[dict[str, str]] = []
                    failed_images: list[dict[str, str]] = []
                    if args.save_images and media_urls and note_id:
                        saved_images, failed_images = download_images(
                            media_urls,
                            target_dir=image_root / sanitize_filename(note_id, fallback=f"note-{export_index:04d}"),
                            max_images=args.max_images_per_note,
                        )

                    # Write markdown immediately
                    increment_reason = "all_history" if args.all_history else "streaming_detail"
                    filename, markdown = markdown_for_note(
                        item, detail,
                        captured_date=captured_date,
                        run_started_iso=run_started_iso,
                        window_start_iso=window_start_iso,
                        source=source,
                        source_label=source_label,
                        increment_reason=increment_reason,
                        saved_images=saved_images,
                        failed_images=failed_images,
                        include_media_urls=args.include_media_urls,
                        output_base=output_dir,
                    )
                    target = run_dir / f"{export_index:04d}-{filename}"
                    title_short = (filename.split("--")[0] if "--" in filename else filename.replace(".md", ""))[:30]
                    if target.exists() and not args.overwrite:
                        progress.update(1, suffix=f"跳过 {title_short}")
                        generated.append(target)
                    else:
                        target.write_text(markdown, encoding="utf-8")
                        progress.update(1, suffix=title_short)
                        generated.append(target)

        finally:
            if proc.stdout:
                proc.stdout.close()
            proc.wait()
            stderr_thread.join(timeout=2)

        progress.finish(suffix=f"本次新增 {run_new_count} 条")

        # Persist incremental state after each round so interrupted runs don't
        # lose progress.  We merge all_run_note_ids into the existing
        # seen_note_ids so the next invocation skips already-exported notes.
        source_state["seen_note_ids"] = sorted(all_run_note_ids)
        save_state(state, state_file)

        stderr_text = "\n".join(line for line in list(stderr_lines.queue) if line.strip()).strip()
        if stderr_text:
            preview = "\n".join(stderr_text.splitlines()[-8:])
            safe_print(f"⚠ xhs 信息:\n{preview[:1000]}")

        fetch_complete = proc.returncode == 0
        if proc.returncode != 0 and not collected_notes:
            raise RuntimeError(stderr_text or f"xhs exited {proc.returncode}")

        # If user specified a max or no new notes found, stop retrying
        if args.max > 0 or run_new_count == 0:
            break

        safe_print(f"本轮获取 {run_new_count} 条新笔记，可能还有更多，自动重试...")

    # Write raw JSON from collected notes
    raw_path = run_dir / f"{source}_raw.json"
    raw_path.write_text(
        json.dumps({"notes": collected_notes}, ensure_ascii=False, indent=2), encoding="utf-8",
    )

    _write_export_index(
        run_dir=run_dir, source=source, source_label=source_label,
        captured_date=captured_date, run_started_iso=run_started_iso,
        window_start_iso=window_start_iso, fetch_details=args.fetch_details,
        save_images=args.save_images, notes_count=len(collected_notes),
        generated=generated, skipped=skipped, detail_failures=detail_failures,
    )

    if fetch_complete:
        update_incremental_state(
            state, source=source, run_started_iso=run_started_iso,
            output_dir=run_dir, notes=collected_notes, exported_count=len(generated), state_file=state_file,
        )
    else:
        if collected_notes:
            safe_print(
                f"⚠ xhs 提前退出，已保留 {len(collected_notes)} 条流式结果；"
                "本次不会更新增量成功 checkpoint。"
            )
        else:
            safe_print("⚠ 本次 xhs 拉取未完整成功，已跳过增量状态更新；修复登录/风控后可安全重跑。")

    safe_print(f"已导出 {len(generated)} 条{source_label}笔记。")
    safe_print(f"Markdown 输出: {run_dir}")
    safe_print(f"状态文件: {state_file}")


def export_notes(args: argparse.Namespace) -> None:
    run_started = now_utc()
    run_started_iso = run_started.isoformat()
    run_id = run_id_string(run_started)
    captured_date = args.date or today_string()
    source = args.source
    source_label = SOURCE_LABELS[source]
    output_dir = Path(args.output_dir).resolve()
    state_file = (Path(args.state_file).resolve() if args.state_file
                  else output_dir / "xhs_state.json")

    if args.reset_state:
        reset_source_state(source, state_file)
        safe_print(f"已重置 {source_label} 的增量状态")
        if args.reset_state_only:
            return

    xhs_bin = find_xhs(args.xhs_bin) if (not args.input_json or args.fetch_details) else None
    output_dir.mkdir(parents=True, exist_ok=True)
    run_dir = output_dir / f"{source}-{run_id}"
    image_root = run_dir / "images"

    if args.dry_run and not args.input_json:
        safe_print(f"将要导出来源: {source_label} ({source})")
        safe_print(f"xhs 可执行文件: {xhs_bin}")
        if args.fetch_details:
            safe_print(f"将要运行: xhs {source} --max {args.max} --json --stream --no-detail（流式详情）")
            safe_print("模式: 流式详情（逐条获取列表 → 逐条抓详情 → 逐条导出）")
        else:
            safe_print(f"将要运行: xhs {source} --max {args.max} --json --stream --no-detail")
            safe_print("模式: 快速列表（封面图优先，可能没有正文）")
        safe_print(f"将要导出 Markdown 到: {run_dir}")
        safe_print(f"将要使用状态文件: {state_file}")
        return

    # ── Streaming detail path: fetch list via NDJSON, export each note immediately ──
    if args.fetch_details and not args.input_json:
        _export_notes_streaming(
            args=args, xhs_bin=xhs_bin, source=source, source_label=source_label,
            output_dir=output_dir, run_dir=run_dir, image_root=image_root,
            state_file=state_file, run_started=run_started, run_started_iso=run_started_iso,
            run_id=run_id, captured_date=captured_date,
        )
        return

    # ── Non-streaming path (no-details / input-json) ──
    payload, raw_stdout, fetch_complete = fetch_source_payload(args, xhs_bin)
    notes = coerce_notes(payload)
    if args.limit:
        notes = notes[: args.limit]

    state = load_state(state_file)
    selected, window_start_iso, skipped = filter_incremental_notes(
        notes, source=source, state=state, run_started=run_started, all_history=args.all_history,
    )

    if args.dry_run:
        safe_print(f"将导出 {len(selected)} 条（共加载 {len(notes)} 条）{source_label}笔记到: {run_dir}")
        safe_print(f"增量窗口: {window_start_iso or '首次运行'} -> {run_started_iso}")
        return

    run_dir.mkdir(parents=True, exist_ok=True)
    if args.save_images:
        image_root.mkdir(parents=True, exist_ok=True)

    raw_path = run_dir / f"{source}_raw.json"
    raw_path.write_text(raw_stdout, encoding="utf-8")

    generated: list[Path] = []
    exported_items: list[dict[str, Any]] = []
    detail_failures: list[dict[str, str]] = []

    progress = ProgressBar(len(selected), label=f"导出{source_label}")

    for index, (item, increment_reason) in enumerate(selected, 1):
        detail: dict[str, Any] = {}
        detail_payload: Any = {}
        note_id = note_id_from(item)
        token = xsec_token_from(item)

        if note_id and xhs_bin and not note_has_embedded_detail(item):
            try:
                detail_args = ["read", note_id, "--json"]
                if token:
                    detail_args.extend(["--xsec-token", token])
                proc = run_xhs(xhs_bin, detail_args)
                detail_payload = json.loads(proc.stdout)
                detail = normalize_detail(detail_payload)
                detail_path = run_dir / "details"
                detail_path.mkdir(parents=True, exist_ok=True)
                (detail_path / f"{note_id}.json").write_text(
                    json.dumps(detail_payload, ensure_ascii=False, indent=2), encoding="utf-8",
                )
            except Exception as exc:
                detail = {"export_error": str(exc)}
                detail_failures.append({"note_id": note_id, "reason": str(exc)})

        media_urls = extract_media_urls(detail or detail_payload or item)
        saved_images: list[dict[str, str]] = []
        failed_images: list[dict[str, str]] = []
        if args.save_images and media_urls and note_id:
            saved_images, failed_images = download_images(
                media_urls,
                target_dir=image_root / sanitize_filename(note_id, fallback=f"note-{index:04d}"),
                max_images=args.max_images_per_note,
            )

        filename, markdown = markdown_for_note(
            item, detail,
            captured_date=captured_date,
            run_started_iso=run_started_iso,
            window_start_iso=window_start_iso,
            source=source,
            source_label=source_label,
            increment_reason=increment_reason,
            saved_images=saved_images,
            failed_images=failed_images,
            include_media_urls=args.include_media_urls,
            output_base=output_dir,
        )
        target = run_dir / f"{index:04d}-{filename}"
        title_short = (filename.split("--")[0] if "--" in filename else filename.replace(".md", ""))[:30]
        if target.exists() and not args.overwrite:
            progress.update(1, suffix=f"跳过 {title_short}")
            generated.append(target)
            exported_items.append(item)
            continue
        target.write_text(markdown, encoding="utf-8")
        progress.update(1, suffix=title_short)
        generated.append(target)
        exported_items.append(item)

    progress.finish(suffix=f"共 {len(generated)} 条")

    _write_export_index(
        run_dir=run_dir, source=source, source_label=source_label,
        captured_date=captured_date, run_started_iso=run_started_iso,
        window_start_iso=window_start_iso, fetch_details=args.fetch_details,
        save_images=args.save_images, notes_count=len(notes),
        generated=generated, skipped=skipped, detail_failures=detail_failures,
    )

    if fetch_complete:
        update_incremental_state(
            state, source=source, run_started_iso=run_started_iso,
            output_dir=run_dir, notes=notes, exported_count=len(generated), state_file=state_file,
        )
    else:
        safe_print("⚠ 本次 xhs 拉取未完整成功，已跳过增量状态更新；修复登录/风控后可安全重跑。")

    safe_print(f"已导出 {len(generated)} 条{source_label}笔记。")
    safe_print(f"Markdown 输出: {run_dir}")
    safe_print(f"状态文件: {state_file}")


# ── Check ────────────────────────────────────────────────────────────────

def check_install(args: argparse.Namespace) -> None:
    xhs_bin = find_xhs(args.xhs_bin)
    safe_print(f"xhs 可执行文件: {xhs_bin}")
    version = xhs_version_text(xhs_bin)
    safe_print(version)

    if is_headless_xhs(xhs_bin):
        doctor = run_xhs(xhs_bin, ["auth", "doctor", "--json"], check=False)
        payload = parse_xhs_json(doctor) or {}
        data = payload.get("data", {}) if isinstance(payload, dict) else {}
        login_status = data.get("login_status", "unknown")
        authenticated = bool(data.get("authenticated", False))
        safe_print(f"登录状态: {login_status} / authenticated={authenticated}")
        safe_print(f"cookie 文件: {data.get('cookie_path', HEADLESS_XHS_CONFIG)}")
        if data.get("validation_error"):
            safe_print(f"验证错误: {data['validation_error'].get('message', '')}")
        if not authenticated:
            safe_print("")
            safe_print("恢复建议:")
            safe_print("  1. 正常浏览器完成小红书登录/验证")
            safe_print(f"  2. 导入字段: \"{xhs_bin}\" auth import-fields --interactive")
            safe_print(f"  3. 或扫码: \"{xhs_bin}\" login --qr-output xhs-login-qr.png")
        return

    status = run_xhs(xhs_bin, ["status"], check=False)
    status_output = (status.stdout or status.stderr).strip()
    if status_output:
        safe_print(status_output)
    whoami = run_xhs(xhs_bin, ["whoami", "--json"], check=False)
    if whoami.returncode == 0:
        safe_print("真实会话验证: 可用")
    else:
        safe_print("真实会话验证: 失败或已过期")
        safe_print((whoami.stderr or whoami.stdout or "").strip())
        safe_print("建议切换到 xhs-cli-headless 或传入 --xhs-bin 指向 headless xhs.exe。")


def login(args: argparse.Namespace) -> None:
    xhs_bin = find_xhs(args.xhs_bin)
    qr_output = Path(args.qr_output or "xhs-login-qr.png").resolve()
    safe_print(f"xhs 可执行文件: {xhs_bin}")
    safe_print(f"二维码输出: {qr_output}")
    cmd = ["login", "--qr-output", str(qr_output)]
    if args.print_link:
        cmd.append("--print-link")
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    proc = subprocess.run(xhs_command(xhs_bin, cmd), env=env)
    if proc.returncode != 0:
        raise RuntimeError(
            "登录命令失败。如果提示 QR login requires verification，"
            "请在正常浏览器完成验证后运行: "
            f"\"{xhs_bin}\" auth import-fields --interactive"
        )


# ── CLI ──────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="将小红书收藏/点赞笔记导出为 Markdown 文件。",
    )
    parser.add_argument("--xhs-bin", help="xhs.exe 的完整路径（如果不在 PATH 中）。")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check_p = subparsers.add_parser("check", help="检查 xhs 安装和登录状态。")
    check_p.add_argument("--xhs-bin", default=argparse.SUPPRESS,
                         help="xhs.exe 的完整路径（如果不在 PATH 中）。")
    check_p.set_defaults(func=check_install)

    login_p = subparsers.add_parser("login", help="通过新版 xhs-cli-headless 登录。")
    login_p.add_argument("--xhs-bin", default=argparse.SUPPRESS,
                         help="xhs.exe 的完整路径（如果不在 PATH 中）。")
    login_p.add_argument("--qr-output", help="二维码 PNG 输出路径（默认: ./xhs-login-qr.png）。")
    login_p.add_argument("--print-link", action="store_true", help="同时打印原始 QR 登录链接。")
    login_p.set_defaults(func=login)

    export_p = subparsers.add_parser("export", help="导出小红书记录为 Markdown。")
    export_p.add_argument("--xhs-bin", default=argparse.SUPPRESS,
                          help="xhs.exe 的完整路径（如果不在 PATH 中）。")
    export_p.add_argument("--source", choices=sorted(SOURCE_LABELS), required=True,
                          help="要导出的记录类型 (favorites / likes)。")
    export_p.add_argument("--max", type=int, default=0,
                          help="从小红书加载的最大记录数；0 表示不限量。")
    export_p.add_argument("--limit", type=int, default=0,
                          help="只转换前 N 条加载到的记录。")
    export_p.add_argument("--output-dir", default=".",
                          help="输出目录（默认: 当前目录）。")
    export_p.add_argument("--state-file",
                          help="增量状态文件路径（默认: <output-dir>/xhs_state.json）。")
    export_p.add_argument("--date", help="输出子文件夹日期，默认: 今天。")
    export_p.add_argument("--input-json", help="从已有的 xhs JSON 文件离线转换。")
    export_p.add_argument("--fetch-details", dest="fetch_details", action="store_true",
                          help="获取笔记详情（正文和全部图片）。")
    export_p.add_argument("--no-fetch-details", dest="fetch_details", action="store_false",
                          help="跳过详情页抓取。")
    export_p.add_argument("--save-images", action="store_true", default=True,
                          help="下载笔记图片。")
    export_p.add_argument("--no-images", dest="save_images", action="store_false",
                          help="不下载图片。")
    export_p.add_argument("--max-images-per-note", type=int, default=20,
                          help="每条笔记最多保存的图片数。")
    export_p.add_argument("--include-media-urls", action="store_true",
                          help="在 Markdown 中包含远程图片 URL。")
    export_p.add_argument("--all-history", action="store_true",
                          help="忽略已有状态，导出所有加载到的记录。")
    export_p.add_argument("--reset-state", action="store_true",
                          help="运行前清除此来源的增量状态。")
    export_p.add_argument("--reset-state-only", action="store_true",
                          help="仅清除此来源的状态然后停止。")
    export_p.add_argument("--overwrite", action="store_true",
                          help="覆盖已生成的 Markdown 文件。")
    export_p.add_argument("--dry-run", action="store_true",
                          help="预览目标路径和数量，不写入文件。")
    export_p.set_defaults(fetch_details=True)
    export_p.set_defaults(func=export_notes)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
        return 0
    except Exception as exc:
        safe_print(f"错误: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
