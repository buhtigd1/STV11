#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
from datetime import datetime
from zoneinfo import ZoneInfo

SOURCE_URL = "https://raw.githubusercontent.com/darkbyteprojects/iptv_png/main/provider_6/live_events.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/149.0.0.0 Safari/537.36"
    )
}

M3U_FILE = "stv11.m3u"
LOG_FILE = "stv11.log"

JAKARTA_TZ = ZoneInfo("Asia/Jakarta")


def write_log(message):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(message + "\n")


def get_json():
    r = requests.get(SOURCE_URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def clean_url(url):
    if not url:
        return ""
    return url.replace("&amp;", "&").strip()


def utc_to_jakarta(dt_str):
    try:
        utc_dt = datetime.strptime(
            dt_str,
            "%Y/%m/%d %H:%M:%S %z"
        )
        return utc_dt.astimezone(JAKARTA_TZ)
    except Exception:
        return None


def kodi_props(stream_type, drm):
    props = []

    if str(stream_type) == "1" and drm and ":" in drm:
        kid, key = drm.split(":", 1)

        props.extend([
            "#KODIPROP:inputstream=inputstream.adaptive",
            "#KODIPROP:inputstream.adaptive.manifest_type=mpd",
            "#KODIPROP:inputstream.adaptive.license_type=com.widevine.alpha",
            f"#KODIPROP:inputstream.adaptive.license_key={kid}:{key}"
        ])

    return props


def build_files(events):

    total_streams = 0
    drm_streams = 0

    with open(M3U_FILE, "w", encoding="utf-8") as m3u:

        m3u.write("#EXTM3U\n")

        for event in events:

            event_id = event.get("id", "")
            category = event.get("cat", "LIVE")
            event_title = event.get("title", "")
            image = event.get("image", "")

            info = event.get("eventInfo", {})

            event_name = info.get("eventName", event_title)
            team_a = info.get("teamA", "")
            team_b = info.get("teamB", "")
            banner = info.get("eventBanner", "")

            start_dt = utc_to_jakarta(
                info.get("startTime", "")
            )

            end_dt = utc_to_jakarta(
                info.get("endTime", "")
            )

            start_str = (
                start_dt.strftime("%Y-%m-%d %H:%M WIB")
                if start_dt else ""
            )

            end_str = (
                end_dt.strftime("%Y-%m-%d %H:%M WIB")
                if end_dt else ""
            )

            for fmt in event.get("formats", []):

                total_streams += 1

                stream_title = fmt.get("title", "Unknown")
                stream_url = clean_url(fmt.get("link", ""))
                logo = fmt.get("logo", "")
                drm = fmt.get("api", "")
                stream_type = str(fmt.get("type", ""))

                if drm:
                    drm_streams += 1

                display_title = (
                    f"{event_name} [{start_str}] | "
                    f"{stream_title}"
                )

                for prop in kodi_props(stream_type, drm):
                    m3u.write(prop + "\n")

                m3u.write(
                    f'#EXTINF:-1 '
                    f'tvg-id="{event_id}" '
                    f'tvg-name="{display_title}" '
                    f'tvg-logo="{logo}" '
                    f'group-title="{category}",'
                    f'{display_title}\n'
                )

                m3u.write(stream_url + "\n")

                timestamp = datetime.now(
                    JAKARTA_TZ
                ).strftime("%Y-%m-%d %H:%M:%S WIB")

                write_log(
                    f"[{timestamp}] "
                    f"EVENT={event_name} "
                    f"START={start_str} "
                    f"END={end_str} "
                    f"STREAM={stream_title} "
                    f"TYPE={stream_type} "
                    f"DRM={'YES' if drm else 'NO'}"
                )

                if drm and ":" in drm:

                    try:
                        kid, key = drm.split(":", 1)

                        write_log(
                            f"MPD={stream_url}"
                        )

                        write_log(
                            f"KID={kid}"
                        )

                        write_log(
                            f"KEY={key}"
                        )

                    except Exception:
                        pass

                write_log(
                    f"EVENT_ID={event_id}"
                )
                write_log(
                    f"CATEGORY={category}"
                )
                write_log(
                    f"TEAM_A={team_a}"
                )
                write_log(
                    f"TEAM_B={team_b}"
                )
                write_log(
                    f"BANNER={banner}"
                )
                write_log("-" * 100)

    write_log("")
    write_log("=" * 100)
    write_log(
        f"TOTAL_EVENTS={len(events)}"
    )
    write_log(
        f"TOTAL_STREAMS={total_streams}"
    )
    write_log(
        f"TOTAL_DRM_STREAMS={drm_streams}"
    )
    write_log("=" * 100)


def main():

    open(LOG_FILE, "w", encoding="utf-8").close()

    print("Downloading events...")

    events = get_json()

    print(
        f"Events found: {len(events)}"
    )

    build_files(events)

    print(
        f"Playlist saved -> {M3U_FILE}"
    )

    print(
        f"Log saved -> {LOG_FILE}"
    )


if __name__ == "__main__":
    main()
