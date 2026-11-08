#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import requests

from html import unescape
from datetime import datetime
from zoneinfo import ZoneInfo
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
    "https://githubusercontent.com"
    "darkbyteprojects/iptv_png/main/provider_6/live_events.json"
)

M3U_FILE = "stv11.m3u"
LOG_FILE = "stv11.log"

THREADS = min(
    64,
    (os.cpu_count() or 4) * 8
)

JAKARTA_TZ = ZoneInfo(
    "Asia/Jakarta"
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
# TIME HELPER
# =====================================================

def format_jkt_timerange(
    start_time,
    end_time
):

    if (
        not start_time
        or not end_time
    ):
        return ""

    try:

        start_dt = datetime.strptime(
            start_time,
            "%Y/%m/%d %H:%M:%S %z"
        )

        end_dt = datetime.strptime(
            end_time,
            "%Y/%m/%d %H:%M:%S %z"
        )

        start_jkt = (
            start_dt.astimezone(
                JAKARTA_TZ
            )
        )

        end_jkt = (
            end_dt.astimezone(
                JAKARTA_TZ
            )
        )

        return (
            f"{start_jkt:%H:%M}"
            f" - "
            f"{end_jkt:%H:%M}"
        )

    except Exception:

        return ""

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

