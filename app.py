"""Private, mobile-friendly Douyin/TikTok downloader.

Credentials are injected with environment variables, never committed to Git.
"""

from __future__ import annotations

import os
import re
import secrets
import shutil
import time
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, abort, flash, redirect, render_template, request, send_file, session, url_for
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

BASE_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)

APP_PASSWORD = os.environ.get("APP_PASSWORD", "")
SECRET_KEY = os.environ.get("SECRET_KEY", "")
COOKIE_FILE = os.environ.get("COOKIE_FILE", "").strip()
ALLOWED_HOSTS = ("douyin.com", "iesdouyin.com", "tiktok.com")
URL_RE = re.compile(r"https?://[^\s<>\"']+", re.I)
TRAILING_JUNK = ".,;:!?\"')]}"
# TikTok answers some posts with an empty format list most of the time. Asking
# again costs a couple of seconds and does sometimes get an answer, though it
# has never turned one of these posts into a downloadable video.
EXTRACT_ATTEMPTS = 3
EXTRACT_RETRY_DELAY = 1.5

app = Flask(__name__)
app.secret_key = SECRET_KEY or "development-only-change-me"
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")


def extract_url(value: str) -> str | None:
    """Extract one supported URL from ordinary sharing text."""
    for raw_url in URL_RE.findall(value or ""):
        url = raw_url.rstrip(TRAILING_JUNK)
        host = (urlparse(url).hostname or "").lower()
        if any(host == allowed or host.endswith("." + allowed) for allowed in ALLOWED_HOSTS):
            return url
    return None


def clean_old_downloads() -> None:
    """Keep completed files briefly so interrupted iPhone downloads can resume."""
    cutoff = time.time() - 2 * 60 * 60
    try:
        items = list(DOWNLOAD_DIR.iterdir())
    except OSError:
        # Render's disk is ephemeral, so the folder can vanish between requests.
        DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        return
    for item in items:
        try:
            if item.is_dir() and item.stat().st_mtime < cutoff:
                shutil.rmtree(item, ignore_errors=True)
        except OSError:
            pass


def friendly_error(url: str, error: Exception) -> str:
    text = str(error)
    lower = text.lower()
    host = (urlparse(url).hostname or "").lower()
    platform = "TikTok" if "tiktok.com" in host else "Douyin"
    if "fresh cookies" in lower or "cookie" in lower:
        return f"{platform} từ chối cookie hiện tại. Hãy cập nhật cookie {platform} trên máy chủ."
    if "no video formats" in lower:
        return (
            f"TikTok không trả luồng video cho bài đăng này, dù đã thử {EXTRACT_ATTEMPTS} lần. "
            "Bài vẫn xem được trên app, nhưng TikTok chặn tải với một số bài — phần lớn "
            "video khác vẫn tải bình thường. Cách khắc phục: nạp cookie TikTok của tài "
            "khoản đã đăng nhập vào máy chủ."
        )
    if "video unavailable" in lower:
        return "Video không còn khả dụng, ở chế độ riêng tư hoặc bị giới hạn khu vực."
    if "unsupported url" in lower:
        return "Link này chưa được hỗ trợ. Hãy thử copy lại link video gốc."
    return text.replace("ERROR: ", "").strip() or "Không thể tải video."


def extract_with_retry(ydl: YoutubeDL, url: str) -> dict | None:
    """Ask again when TikTok hands back a video with no formats attached.

    yt-dlp's own `retries` only covers the transfer, so this refusal - which
    arrives on a perfectly successful HTTP response - never gets a second try.
    """
    for attempt in range(1, EXTRACT_ATTEMPTS + 1):
        try:
            return ydl.extract_info(url, download=True)
        except DownloadError as error:
            if attempt == EXTRACT_ATTEMPTS or "no video formats" not in str(error).lower():
                raise
            time.sleep(EXTRACT_RETRY_DELAY)
    return None


def download_video(url: str, prefer_h264: bool) -> tuple[Path, str]:
    job_dir = DOWNLOAD_DIR / secrets.token_urlsafe(12)
    job_dir.mkdir(parents=True)
    no_watermark = "[format_id!^=download_addr][format_note!*=watermark]"
    best = f"b{no_watermark}/b[format_note!*=watermark]/b"
    h264 = f"b[format_id^=h264]{no_watermark}/b[vcodec^=avc]{no_watermark}/{best}"
    options: dict = {
        "outtmpl": str(job_dir / "%(uploader,channel,creator|video).40s - %(title,description|video).60s - %(id)s.%(ext)s"),
        "format": h264 if prefer_h264 else best,
        "noplaylist": True,
        "windowsfilenames": True,
        "trim_file_name": 150,
        "quiet": True,
        "noprogress": True,
        "retries": 3,
        "fragment_retries": 3,
        # Give up well before gunicorn's own timeout so a stalled platform
        # response becomes a readable message instead of a killed worker.
        "socket_timeout": 30,
        "overwrites": False,
    }
    if COOKIE_FILE:
        source_cookie = Path(COOKIE_FILE)
        if not source_cookie.is_file():
            raise RuntimeError("Không tìm thấy Secret File cookie trên máy chủ Render.")
        # Render mounts secret files read-only, while yt-dlp may update its cookie
        # jar. Work on a private, writable copy for this download instead.
        cookie_copy = job_dir / "cookies.txt"
        shutil.copyfile(source_cookie, cookie_copy)
        options["cookiefile"] = str(cookie_copy)

    with YoutubeDL(options) as ydl:
        info = extract_with_retry(ydl, url)
        if not info:
            raise RuntimeError("Không đọc được thông tin video")
        if info.get("_type") == "playlist":
            info = next((entry for entry in info.get("entries", []) if entry), None)
        if not info:
            raise RuntimeError("Link không có video để tải")
        requested = info.get("requested_downloads") or []
        filepath = requested[0].get("filepath") if requested else ydl.prepare_filename(info)
        path = Path(filepath)
        if not path.is_file():
            matches = list(job_dir.glob("*"))
            path = next((item for item in matches if item.is_file()), path)
        if not path.is_file():
            raise RuntimeError("Tải xong nhưng không tìm thấy file video")
        if (info.get("vcodec") or "none") == "none":
            raise RuntimeError(
                "TikTok chỉ trả về phần nhạc của bài đăng này, không có hình. "
                "Hãy nạp cookie TikTok của tài khoản đã đăng nhập vào máy chủ."
            )
        return path, (info.get("title") or "video")


@app.before_request
def require_login():
    if request.endpoint in {"login", "static"}:
        return None
    if not APP_PASSWORD:
        abort(503, "Server chua duoc cau hinh APP_PASSWORD.")
    if not session.get("authenticated"):
        return redirect(url_for("login"))
    clean_old_downloads()
    return None


@app.route("/login", methods=["GET", "POST"])
def login():
    if not APP_PASSWORD:
        abort(503, "Server chua duoc cau hinh APP_PASSWORD.")
    if request.method == "POST":
        password = request.form.get("password", "")
        if secrets.compare_digest(password, APP_PASSWORD):
            session.clear()
            session["authenticated"] = True
            return redirect(url_for("index"))
        flash("Mật khẩu không đúng.", "error")
    return render_template("login.html")


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        url = extract_url(request.form.get("link", ""))
        if not url:
            flash("Không tìm thấy link Douyin hoặc TikTok hợp lệ.", "error")
            return render_template("index.html")
        try:
            filepath, title = download_video(url, request.form.get("h264") == "on")
            return send_file(filepath, as_attachment=True, download_name=filepath.name, mimetype="video/mp4")
        except Exception as error:  # yt-dlp gives provider-specific exceptions
            flash(friendly_error(url, error), "error")
    return render_template("index.html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=False)
