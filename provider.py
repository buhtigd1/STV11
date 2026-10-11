#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
from datetime import datetime
from zoneinfo import ZoneInfo

# =========================
# CONFIG
# =========================

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

JAKARTA_TZ = ZoneInfo("Asia/Jakarta")


# =========================
# HELPERS
# =========================

def log(message):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(message + "\n")


def now_wib():
    return datetime.now(JAKARTA_TZ).strftime(
        "%Y-%m-%d %H:%M:%S WIB"
    )


def clean_url(url):
    if not url:
        return ""

    return (
        url.strip()
        .replace("&amp;", "&")
    )


def convert_time(time_str):
    try:
        utc_dt = datetime.strptime(
            time_str,
            "%Y/%m/%d %H:%M:%S %z"
        )

        return utc_dt.astimezone(
            JAKARTA_TZ
        )

    except Exception:
        return None


def format_wib(dt):
    if not dt:
        return ""

    return dt.strftime(
        "%Y-%m-%d %H:%M WIB"
    )


def download_events():
    r = requests.get(
        SOURCE_URL,
        headers=HEADERS,
        timeout=30
    )

    r.raise_for_status()

    return r.json()


# =========================
# KODI DRM SUPPORT
# =========================

def write_kodi_props(m3u, stream_type, drm):

    if str(stream_type) != "1":
        return

    if not drm or ":" not in drm:
        return

    kid, key = drm.split(":", 1)

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


# =========================
# PLAYLIST GENERATOR
# =========================

def build_playlist(events):

    total_events = 0
    total_streams = 0
    total_drm = 0

    with open(M3U_FILE, "w", encoding="utf-8") as m3u:

        # REQUIRED HEADER
        m3u.write(
            '#EXTM3U '
            'refresh="900" '
            'generator="STVB"\n'
        )

        for event in events:

            total_events += 1

            event_id = event.get("id", "")
            category = event.get("cat", "LIVE")

            info = event.get("eventInfo", {})

            event_name = (
                info.get("eventName")
                or event.get("title", "")
            )

            start_dt = convert_time(
                info.get("startTime", "")
            )

            end_dt = convert_time(
                info.get("endTime", "")
            )

            start_time = format_wib(start_dt)
            end_time = format_wib(end_dt)

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

                #
                # Kodi DRM tags
                #
                write_kodi_props(
                    m3u,
                    stream_type,
                    drm
                )

                #
                # EXTINF
                #
                m3u.write(
                    f'#EXTINF:-1 '
                    f'tvg-id="{event_id}" '
                    f'tvg-name="{stream_title}" '
                    f'tvg-logo="{stream_logo}" '
                    f'group-title="{category}",'
                    f'{stream_title}\n'
                )

                #
                # IPTV group
                #
                m3u.write(
                    f"#EXTGRP:{category}\n"
                )

                #
                # VLC options
                #
                m3u.write(
                    "#EXTVLCOPT:http-user-agent="
                    f'{HEADERS["User-Agent"]}\n'
                )

                #
                # URL
                #
                m3u.write(
                    stream_url + "\n\n"
                )

                #
                # LOGGING
                #
                log(
                    f"[{now_wib()}] "
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
    log(f"TOTAL_EVENTS={total_events}")
    log(f"TOTAL_STREAMS={total_streams}")
    log(f"TOTAL_DRM_STREAMS={total_drm}")
    log("=" * 80)


# =========================
# MAIN
# =========================

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
