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

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/149.0.0.0 Safari/537.36"
    )
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
        .replace("&amp;", "&")
    )


def download_events():
    r = requests.get(
        SOURCE_URL,
        headers=HEADERS,
        timeout=30
    )

    r.raise_for_status()

    return r.json()


# =====================================================
# PLAYLIST GENERATOR
# =====================================================

def build_playlist(events):

    total_events = 0
    total_streams = 0
    total_drm = 0

    with open(M3U_FILE, "w", encoding="utf-8") as m3u:

        # M3U HEADER
        m3u.write(
            '#EXTM3U '
            'refresh="900"\n'
        )

        for event in events:

            total_events += 1

            event_id = event.get("id", "")
            category = event.get("cat", "LIVE")

            event_info = event.get("eventInfo", {})

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

            for stream in event.get("formats", []):

                total_streams += 1

                stream_title = stream.get(
                    "title",
                    "Unknown"
                )

                stream_type = str(
                    stream.get("type", "")
                )

                stream_url = clean_url(
                    stream.get("link", "")
                )

                stream_logo = stream.get(
                    "logo",
                    ""
                )

                drm = stream.get(
                    "api",
                    ""
                )

                if drm:
                    total_drm += 1

                # =====================================
                # EXTINF
                # =====================================
                m3u.write(
                    f'#EXTINF:-1 '
                    f'tvg-id="{event_id}" '
                    f'tvg-name="{stream_title}" '
                    f'tvg-logo="{stream_logo}" '
                    f'group-title="{category}",'
                    f'{stream_title}\n'
                )

                # =====================================
                # GROUP
                # =====================================
                m3u.write(
                    f"#EXTGRP:{category}\n"
                )

                # =====================================
                # VLC OPTS
                # =====================================
                m3u.write(
                    "#EXTVLCOPT:http-user-agent="
                    f'{HEADERS["User-Agent"]}\n'
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
                        "#KODIPROP:inputstream="
                        "inputstream.adaptive\n"
                    )

                    m3u.write(
                        "#KODIPROP:"
                        "inputstream.adaptive.manifest_type=mpd\n"
                    )

                    m3u.write(
                        "#KODIPROP:"
                        "inputstream.adaptive.license_type="
                        "com.widevine.alpha\n"
                    )

                    m3u.write(
                        "#KODIPROP:"
                        f"inputstream.adaptive.license_key={kid}:{key}\n"
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

                if drm:

                    log("DRM=YES")

                    if ":" in drm:

                        kid, key = drm.split(
                            ":",
                            1
                        )

                        log(
                            f"KID={kid}"
                        )

                        log(
                            f"KEY={key}"
                        )

                else:

                    log("DRM=NO")

                log("-" * 80)

    log("")
    log("=" * 80)
    log(f"TOTAL_EVENTS={total_events}")
    log(f"TOTAL_STREAMS={total_streams}")
    log(f"TOTAL_DRM_STREAMS={total_drm}")
    log("=" * 80)


# =====================================================
# MAIN
# =====================================================

def main():

    with open(
        LOG_FILE,
        "w",
        encoding="utf-8"
    ):
        pass

    print("Downloading feed...")

    events = download_events()

    print(
        f"Loaded {len(events)} events"
    )

    build_playlist(events)

    print(
        f"Playlist written: {M3U_FILE}"
    )

    print(
        f"Log written: {LOG_FILE}"
    )

    print("Done.")


if __name__ == "__main__":
    main()
