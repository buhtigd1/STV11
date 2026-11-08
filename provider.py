#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import requests

from html import unescape
from datetime import datetime
from threading import local

from concurrent.futures import (
    ThreadPoolExecutor,
    as_completed
)

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# =====================================================
# CONFIG
# =====================================================

SOURCE_URL = (
    "https://raw.githubusercontent.com/"
    "darkbyteprojects/iptv_png/main/provider_6/live_events.json"
)

M3U_FILE = "stv11.m3u"
LOG_FILE = "stv11.log"

THREADS = min(
    64,
    (os.cpu_count() or 4) * 8
)

CHECK_TIMEOUT = 10

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/149.0.0.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": USER_AGENT
}

VALID_CONTENT_TYPES = (
    "mpegurl",
    "dash+xml",
    "video/",
    "octet-stream"
)

_thread_local = local()

validation_cache = {}
log_buffer = []

# =====================================================
# LOGGING
# =====================================================

def log(message):
    log_buffer.append(message)


def flush_log():

    with open(
        LOG_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        f.write(
            "\n".join(log_buffer)
        )


def now_log():

    return datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

# =====================================================
# URL HELPERS
# =====================================================

def clean_url(url):

    if not url:
        return ""

    url = url.strip()

    while "&amp;" in url:
        url = unescape(url)

    return url


def extract_headers(url):

    url = clean_url(url)

    if "|" not in url:
        return url, {}

    base_url, params = url.split(
        "|",
        1
    )

    headers = {}

    for item in params.split("&"):

        if "=" not in item:
            continue

        k, v = item.split(
            "=",
            1
        )

        key = k.lower().strip()

        if key in (
            "user-agent",
            "useragent",
            "http-user-agent"
        ):
            key = "user-agent"

        elif key in (
            "referer",
            "referrer"
        ):
            key = "referer"

        elif key == "origin":
            key = "origin"

        headers[key] = v.strip()

    return (
        base_url.strip(),
        headers
    )

# =====================================================
# VLC OPTIONS
# =====================================================

def write_vlc_options(
    m3u,
    headers
):

    ua = headers.get(
        "user-agent",
        USER_AGENT
    )

    m3u.write(
        f"#EXTVLCOPT:http-user-agent={ua}\n"
    )

    if "referer" in headers:

        m3u.write(
            f"#EXTVLCOPT:http-referrer="
            f"{headers['referer']}\n"
        )

# =====================================================
# SESSION
# =====================================================

def get_session():

    if hasattr(
        _thread_local,
        "session"
    ):
        return _thread_local.session

    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=0.5,
        status_forcelist=[
            429,
            500,
            502,
            503,
            504
        ]
    )

    adapter = HTTPAdapter(
        max_retries=retry,
        pool_connections=200,
        pool_maxsize=200
    )

    session = requests.Session()

    session.mount(
        "http://",
        adapter
    )

    session.mount(
        "https://",
        adapter
    )

    session.headers.update(
        HEADERS
    )

    _thread_local.session = session

    return session

# =====================================================
# DOWNLOAD FEED
# =====================================================

def download_events():

    with get_session().get(
        SOURCE_URL,
        timeout=30
    ) as r:

        r.raise_for_status()

        return r.json()

# =====================================================
# STREAM VALIDATION
# =====================================================

def is_stream_alive(
    url,
    extra_headers=None
):

    if url in validation_cache:
        return validation_cache[url]

    headers = HEADERS.copy()

    if extra_headers:
        headers.update(
            extra_headers
        )

    headers["Range"] = (
        "bytes=0-1023"
    )

    try:

        with get_session().get(
            url,
            headers=headers,
            stream=True,
            allow_redirects=True,
            timeout=CHECK_TIMEOUT
        ) as r:

            if r.status_code not in (
                200,
                206
            ):
                validation_cache[url] = False
                return False

            content_type = (
                r.headers.get(
                    "Content-Type",
                    ""
                ).lower()
            )

            alive = any(
                x in content_type
                for x in VALID_CONTENT_TYPES
            )

            validation_cache[url] = alive

            return alive

    except requests.RequestException:

        validation_cache[url] = False

        return False

# =====================================================
# PARSE EVENTS
# =====================================================

def collect_streams(events):

    streams = []
    seen = set()

    for event in events:

        event_id = event.get(
            "id",
            ""
        )

        category = event.get(
            "cat",
            "LIVE"
        )

        info = event.get(
            "eventInfo",
            {}
        )

        event_name = (
            info.get(
                "eventName"
            )
            or event.get(
                "title",
                ""
            )
        )

        start_time = info.get(
            "startTime",
            ""
        )

        end_time = info.get(
            "endTime",
            ""
        )

        for stream in event.get(
            "formats",
            []
        ):

            raw_url = clean_url(
                stream.get(
                    "link",
                    ""
                )
            )

            if not raw_url:
                continue

            stream_url, headers = (
                extract_headers(
                    raw_url
                )
            )

            if not stream_url:
                continue

            if stream_url in seen:
                continue

            seen.add(stream_url)

            streams.append({

                "event_id":
                    event_id,

                "category":
                    category,

                "event_name":
                    event_name,

                "start_time":
                    start_time,

                "end_time":
                    end_time,

                "stream":
                    stream,

                "stream_url":
                    stream_url,

                "headers":
                    headers
            })

    return streams

# =====================================================
# VALIDATE STREAMS
# =====================================================

def validate_streams(streams):

    valid = []

    with ThreadPoolExecutor(
        max_workers=THREADS
    ) as executor:

        futures = {

            executor.submit(
                is_stream_alive,
                item["stream_url"],
                item["headers"]
            ): item

            for item in streams
        }

        total = len(futures)

        checked = 0

        for future in as_completed(
            futures
        ):

            checked += 1

            item = futures[future]

            try:

                if future.result():

                    valid.append(
                        item
                    )

                    print(
                        f"[OK] "
                        f"{checked}/{total} "
                        f"{item['event_name']}"
                    )

                else:

                    print(
                        f"[DEAD] "
                        f"{checked}/{total} "
                        f"{item['event_name']}"
                    )

            except Exception:

                print(
                    f"[ERROR] "
                    f"{checked}/{total} "
                    f"{item['event_name']}"
                )

    return valid

# =====================================================
# BUILD PLAYLIST
# =====================================================

def build_playlist(streams):

    total_streams = 0
    total_drm = 0

    with open(
        M3U_FILE,
        "w",
        encoding="utf-8"
    ) as m3u:

        m3u.write(
            "#EXTM3U\n\n"
        )

        for item in streams:

            total_streams += 1

            stream = item["stream"]

            stream_title = (
                stream.get(
                    "title",
                    "Unknown"
                )
            )

            logo = (
                stream.get(
                    "logo",
                    ""
                )
            )

            drm = stream.get(
                "api",
                ""
            )

            stream_type = str(
                stream.get(
                    "type",
                    ""
                )
            )

            channel_name = (
                f"{item['event_name']} | "
                f"{stream_title}"
            )

            m3u.write(
                f'#EXTINF:-1 '
                f'tvg-id="{item["event_id"]}" '
                f'tvg-name="{channel_name}" '
                f'tvg-logo="{logo}" '
                f'group-title="{item["category"]}",'
                f'{channel_name}\n'
            )

            write_vlc_options(
                m3u,
                item["headers"]
            )

            if (
                stream_type == "1"
                and drm
                and ":" in drm
            ):

                total_drm += 1

                kid, key = drm.split(
                    ":",
                    1
                )

                m3u.write(
                    "#KODIPROP:inputstream=inputstream.adaptive\n"
                )

                m3u.write(
                    "#KODIPROP:inputstream.adaptive.manifest_type=mpd\n"
                )

                m3u.write(
                    "#KODIPROP:inputstream.adaptive.license_type=clearkey\n"
                )

                m3u.write(
                    f"#KODIPROP:inputstream.adaptive.license_key={kid}:{key}\n"
                )

            m3u.write(
                item["stream_url"]
                + "\n\n"
            )

            log(
                f"[{now_log()}] "
                f"{channel_name}"
            )

    log("")
    log("=" * 80)
    log(f"TOTAL_VALID={total_streams}")
    log(f"TOTAL_DRM={total_drm}")
    log("=" * 80)

    flush_log()

# =====================================================
# MAIN
# =====================================================

def main():

    print(
        "Downloading feed..."
    )

    events = download_events()

    print(
        f"Loaded {len(events)} events"
    )

    streams = collect_streams(
        events
    )

    print(
        f"Found {len(streams)} streams"
    )

    print(
        "Checking streams..."
    )

    valid_streams = (
        validate_streams(
            streams
        )
    )

    print(
        f"Alive streams: "
        f"{len(valid_streams)}"
    )

    build_playlist(
        valid_streams
    )

    print(
        f"Playlist written: "
        f"{M3U_FILE}"
    )

    print(
        f"Log written: "
        f"{LOG_FILE}"
    )

    print("Done")


if __name__ == "__main__":
    main()
