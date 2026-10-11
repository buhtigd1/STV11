#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
from datetime import datetime

# =====================================================
# CONFIG
# =====================================================

SOURCE_URL = (
    "https://raw.githubusercontent.com/"
    "darkbyteprojects/iptv_png/main/provider_6/live_events.json"
)

M3U_FILE = "stv11.m3u"
LOG_FILE = "stv11.log"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/149.0.0.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": USER_AGENT
}

# =====================================================
# HELPERS
# =====================================================

def log(message):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(message + "\n")


def now_log():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def clean_url(url):
    if not url:
        return ""

    return (
        url.strip()
        .replace("&amp;amp;", "&")
        .replace("&amp;", "&")
    )


def extract_headers(url):
    """
    Example:
    https://test.mpd|user-agent=Mozilla|Referer=https://abc.com
    """

    if "|" not in url:
        return url, {}

    base_url, params = url.split("|", 1)

    headers = {}

    for item in params.split("&"):
        if "=" in item:
            k, v = item.split("=", 1)
            headers[k.lower()] = v

    return base_url.strip(), headers


def write_vlc_options(m3u, headers):

    m3u.write(
        f"#EXTVLCOPT:http-user-agent="
        f"{headers.get('user-agent', USER_AGENT)}\n"
    )

    if "referer" in headers:
        m3u.write(
            f"#EXTVLCOPT:http-referrer={headers['referer']}\n"
        )

    if "origin" in headers:
        m3u.write(
            f"#EXTVLCOPT:http-origin={headers['origin']}\n"
        )


def download_events():

    response = requests.get(
        SOURCE_URL,
        headers=HEADERS,
        timeout=30
    )

    response.raise_for_status()

    return response.json()


# =====================================================
# PLAYLIST
# =====================================================

def build_playlist(events):

    total_events = 0
    total_streams = 0
    total_drm_streams = 0

    with open(M3U_FILE, "w", encoding="utf-8") as m3u:

        # Standard M3U header
        m3u.write("#EXTM3U\n\n")

        for event in events:

            total_events += 1

            event_id = event.get("id", "")
            category = event.get("cat", "LIVE")

            event_info = event.get(
                "eventInfo",
                {}
            )

            event_name = (
                event_info.get("eventName")
                or event.get("title", "")
            )

            start_time = event_info.get(
                "startTime",
                ""
            )

            end_time = event_info.get(
                "endTime",
                ""
            )

            for stream in event.get(
                "formats",
                []
            ):

                total_streams += 1

                stream_title = stream.get(
                    "title",
                    "Unknown"
                )

                stream_logo = stream.get(
                    "logo",
                    ""
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

                raw_url = clean_url(
                    stream.get(
                        "link",
                        ""
                    )
                )

                stream_url, url_headers = (
                    extract_headers(
                        raw_url
                    )
                )

                channel_name = (
                    f"{event_name} | "
                    f"{stream_title}"
                )

                # =====================================
                # COUNT DRM
                # =====================================

                if drm and ":" in drm:
                    total_drm_streams += 1

                # =====================================
                # EXTINF
                # =====================================

                m3u.write(
                    f'#EXTINF:-1 '
                    f'tvg-id="{event_id}" '
                    f'tvg-name="{channel_name}" '
                    f'tvg-logo="{stream_logo}" '
                    f'group-title="{category}",'
                    f'{channel_name}\n'
                )

                # =====================================
                # EXTVLCOPT
                # =====================================

                write_vlc_options(
                    m3u,
                    url_headers
                )

                # =====================================
                # KODI DRM
                # =====================================

                if (
                    stream_type == "1"
                    and drm
                    and ":" in drm
                ):

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
                        "#KODIPROP:inputstream.adaptive.license_type=com.widevine.alpha\n"
                    )

                    m3u.write(
                        "#KODIPROP:inputstream.adaptive.license_key="
                        f"{kid}:{key}\n"
                    )

                # =====================================
                # STREAM URL
                # =====================================

                m3u.write(
                    stream_url + "\n\n"
                )

                # =====================================
                # LOGGING
                # =====================================

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

                if drm and ":" in drm:

                    kid, key = drm.split(
                        ":",
                        1
                    )

                    log("DRM=YES")
                    log(
                        f"KID={kid}"
                    )
                    log(
                        f"KEY={key}"
                    )

                else:

                    log("DRM=NO")

                log(
                    "-" * 80
                )

    log("")
    log("=" * 80)
    log(
        f"TOTAL_EVENTS={total_events}"
    )
    log(
        f"TOTAL_STREAMS={total_streams}"
    )
    log(
        f"TOTAL_DRM_STREAMS="
        f"{total_drm_streams}"
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

    print("Downloading feed...")

    events = download_events()

    print(
        f"Loaded {len(events)} events"
    )

    build_playlist(events)

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
