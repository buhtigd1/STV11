#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests

from datetime import datetime
from concurrent.futures import (
    ThreadPoolExecutor,
    as_completed
)
from threading import local

# =====================================================
# CONFIG
# =====================================================

SOURCE_URL = (
    "https://raw.githubusercontent.com/"
    "darkbyteprojects/iptv_png/main/provider_6/live_events.json"
)

M3U_FILE = "stv11.m3u"
LOG_FILE = "stv11.log"

THREADS = 50
CHECK_TIMEOUT = 10

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/149.0.0.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": USER_AGENT
}

_thread_local = local()

# =====================================================
# LOGGING
# =====================================================

def log(message):
    with open(
        LOG_FILE,
        "a",
        encoding="utf-8"
    ) as f:
        f.write(message + "\n")


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

    return (
        url.strip()
        .replace("&amp;amp;amp;", "&amp;")
        .replace("&amp;amp;", "&amp;")
    )


def extract_headers(url):
    """
    URL example:

    https://test.mpd
    |user-agent=Mozilla/5.0
    &amp;referer=https://site.com
    """

    if "|" not in url:
        return url, {}

    base_url, params = url.split(
        "|",
        1
    )

    headers = {}

    for item in params.split("&amp;"):

        if "=" not in item:
            continue

        k, v = item.split(
            "=",
            1
        )

        headers[
            k.lower().strip()
        ] = v.strip()

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

    m3u.write(
        f"#EXTVLCOPT:http-user-agent="
        f"{headers.get('user-agent', USER_AGENT)}\n"
    )

    if "referer" in headers:

        m3u.write(
            f"#EXTVLCOPT:http-referrer="
            f"{headers['referer']}\n"
        )

    if "origin" in headers:

        m3u.write(
            f"#EXTVLCOPT:http-origin="
            f"{headers['origin']}\n"
        )

# =====================================================
# SESSION
# =====================================================

def get_session():

    if not hasattr(
        _thread_local,
        "session"
    ):

        session = requests.Session()

        adapter = (
            requests.adapters.HTTPAdapter(
                pool_connections=100,
                pool_maxsize=100
            )
        )

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

        _thread_local.session = (
            session
        )

    return _thread_local.session

# =====================================================
# DOWNLOAD JSON
# =====================================================

def download_events():

    session = get_session()

    response = session.get(
        SOURCE_URL,
        timeout=30
    )

    response.raise_for_status()

    return response.json()

# =====================================================
# STREAM CHECKER
# =====================================================

def is_stream_alive(
    url,
    extra_headers=None
):

    try:

        session = get_session()

        headers = HEADERS.copy()

        if extra_headers:
            headers.update(
                extra_headers
            )

        try:

            r = session.head(
                url,
                headers=headers,
                allow_redirects=True,
                timeout=CHECK_TIMEOUT
            )

            if (
                200
                <= r.status_code
                < 300
            ):
                return True

            if r.status_code in (
                403,
                404,
                410,
                500,
                502,
                503,
                504
            ):
                return False

        except Exception:
            pass

        r = session.get(
            url,
            headers={
                **headers,
                "Range":
                    "bytes=0-1023"
            },
            stream=True,
            allow_redirects=True,
            timeout=CHECK_TIMEOUT
        )

        if r.status_code in (
            200,
            206
        ):
            return True

        return False

    except (
        requests.exceptions.Timeout,
        requests.exceptions.ConnectionError,
        requests.exceptions.SSLError,
        requests.exceptions.RequestException
    ):

        return False

# =====================================================
# PARSE STREAMS
# =====================================================

def collect_streams(events):

    streams = []

    for event in events:

        event_id = event.get(
            "id",
            ""
        )

        category = event.get(
            "cat",
            "LIVE"
        )

        event_info = event.get(
            "eventInfo",
            {}
        )

        event_name = (
            event_info.get(
                "eventName"
            )
            or event.get(
                "title",
                ""
            )
        )

        start_time = (
            event_info.get(
                "startTime",
                ""
            )
        )

        end_time = (
            event_info.get(
                "endTime",
                ""
            )
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
# VALIDATION
# =====================================================

def validate_streams(
    streams
):

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

            item = futures[
                future
            ]

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

def build_playlist(
    streams
):

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

            stream = item[
                "stream"
            ]

            event_name = item[
                "event_name"
            ]

            event_id = item[
                "event_id"
            ]

            category = item[
                "category"
            ]

            start_time = item[
                "start_time"
            ]

            end_time = item[
                "end_time"
            ]

            stream_url = item[
                "stream_url"
            ]

            headers = item[
                "headers"
            ]

            stream_title = (
                stream.get(
                    "title",
                    "Unknown"
                )
            )

            stream_logo = (
                stream.get(
                    "logo",
                    ""
                )
            )

            stream_type = str(
                stream.get(
                    "type",
                    ""
                )
            )

            drm = stream.get(
                "api",
                ""
            )

            channel_name = (
                f"{event_name} | "
                f"{stream_title}"
            )

            m3u.write(
                f'#EXTINF:-1 '
                f'tvg-id="{event_id}" '
                f'tvg-name="{channel_name}" '
                f'tvg-logo="{stream_logo}" '
                f'group-title="{category}",'
                f'{channel_name}\n'
            )

            write_vlc_options(
                m3u,
                headers
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
                    "#KODIPROP:inputstream.adaptive.license_key="
                    f"{kid}:{key}\n"
                )

            m3u.write(
                stream_url +
                "\n\n"
            )

            log(
                f"[{now_log()}] "
                f"EVENT={event_name}"
            )
            log(
                f"START={start_time}"
            )
            log(
                f"END={end_time}"
            )
            log(
                f"CATEGORY={category}"
            )
            log(
                f"STREAM={stream_title}"
            )
            log(
                f"TYPE={stream_type}"
            )
            log(
                f"URL={stream_url}"
            )

            if (
                drm
                and ":" in drm
            ):
                log(
                    "DRM=YES"
                )
            else:
                log(
                    "DRM=NO"
                )

            log(
                "-" * 80
            )

    log("")
    log("=" * 80)
    log(
        f"TOTAL_VALID_STREAMS="
        f"{total_streams}"
    )
    log(
        f"TOTAL_DRM_STREAMS="
        f"{total_drm}"
    )
    log("=" * 80)

# =====================================================
# MAIN
# =====================================================

def main():

    open(
        LOG_FILE,
        "w",
        encoding="utf-8"
    ).close()

    print(
        "Downloading feed..."
    )

    events = download_events()

    print(
        f"Loaded "
        f"{len(events)} events"
    )

    streams = collect_streams(
        events
    )

    print(
        f"Found "
        f"{len(streams)} streams"
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

    print("Done.")

if __name__ == "__main__":
    main()
