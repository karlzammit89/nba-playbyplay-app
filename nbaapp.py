import streamlit as st
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

# =========================
# FUNCTIONS
# =========================

def parse_iso_time(t):
    if not t:
        return None
    return datetime.fromisoformat(t.replace("Z", "+00:00"))


def convert_to_et(dt):
    if dt:
        return dt.astimezone(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M:%S %Z")
    return None


def format_clock(clock):
    if not clock:
        return None
    return clock.replace("PT", "").replace("M", ":").replace(".00S", "")


def clock_to_seconds(clock):
    if not clock:
        return None
    try:
        m, s = clock.split(":")
        return int(m) * 60 + int(s)
    except:
        return None


def normalize_period(period):
    if period is None:
        return None
    if period >= 5:
        return f"OT {period - 4}"
    return period


def group_period_for_filter(period):
    if isinstance(period, str) and period.startswith("OT"):
        return "OT"
    return period


# =========================
# UI
# =========================

st.title("🏀 NBA Dashboard (Dual Filter Mode)")

game_id = st.text_input("Enter Game ID", "0042500132")

# -------------------------
# QUARTER FILTER
# -------------------------
USE_QUARTER_FILTER = st.checkbox("Filter by Quarter", value=False)
TARGET_QUARTERS = []

if USE_QUARTER_FILTER:
    TARGET_QUARTERS = st.multiselect(
        "Select Quarters",
        [1, 2, 3, 4, "OT"],
        default=[2]
    )

# -------------------------
# REAL TIME FILTER (timeActual)
# -------------------------
USE_TIME_FILTER = st.checkbox("Filter by Real Time (timeActual)", value=False)

START_TIME = None
END_TIME = None

if USE_TIME_FILTER:
    START_INPUT = st.text_input("Start Time (ISO)", "2024-01-01T00:00:00Z")
    END_INPUT = st.text_input("End Time (ISO)", "2026-12-31T23:59:59Z")

    START_TIME = parse_iso_time(START_INPUT)
    END_TIME = parse_iso_time(END_INPUT)

# -------------------------
# GAME CLOCK FILTER
# -------------------------
USE_CLOCK_FILTER = st.checkbox("Filter by Game Clock", value=False)

START_SEC = None
END_SEC = None

if USE_CLOCK_FILTER:
    MIN_CLOCK = st.text_input("Min Clock (MM:SS)", "00:00")
    MAX_CLOCK = st.text_input("Max Clock (MM:SS)", "12:00")

    START_SEC = clock_to_seconds(MAX_CLOCK)  # bigger (start of window)
    END_SEC = clock_to_seconds(MIN_CLOCK)    # smaller (end of window)

run = st.button("Load Game Feed")


# =========================
# MAIN LOGIC
# =========================

if run:
    url = f"https://cdn.nba.com/static/json/liveData/playbyplay/playbyplay_{game_id}.json"

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://www.nba.com/"
    }

    try:
        data = requests.get(url, headers=headers, timeout=10).json()
        plays = data.get("game", {}).get("actions", [])

        events = []

        for play in plays:
            raw_period = play.get("period")
            period_display = normalize_period(raw_period)
            period_group = group_period_for_filter(period_display)

            # =========================
            # REAL TIME FIELD
            # =========================
            raw_time = play.get("timeActual")
            event_time = parse_iso_time(raw_time)

            # =========================
            # GAME CLOCK FIELD
            # =========================
            clock_raw = play.get("clock")
            clock = format_clock(clock_raw)
            sec = clock_to_seconds(clock)

            # =========================
            # QUARTER FILTER
            # =========================
            if USE_QUARTER_FILTER and period_group not in TARGET_QUARTERS:
                continue

            # =========================
            # REAL TIME FILTER (timeActual)
            # =========================
            if USE_TIME_FILTER and event_time:
                if START_TIME and END_TIME:
                    if not (START_TIME <= event_time <= END_TIME):
                        continue

            # =========================
            # GAME CLOCK FILTER
            # =========================
            if USE_CLOCK_FILTER and sec is not None:
                if START_SEC is not None and END_SEC is not None:
                    if not (END_SEC <= sec <= START_SEC):
                        continue

            events.append({
                "Quarter": period_display,
                "Clock": clock,
                "Score": f"{play.get('scoreAway')} - {play.get('scoreHome')}",
                "Description": play.get("description"),
                "Shot Result": play.get("shotResult"),
                "ET Time": convert_to_et(event_time)
            })

        # =========================
        # OUTPUT
        # =========================

        for e in events:
            st.markdown("---")

            label = f"🔥 {e['Quarter']}" if str(e["Quarter"]).startswith("OT") else f"🏀 Q{e['Quarter']}"

            st.write(f"**{label} | ⏱️ {e['Clock']}**")
            st.write(f"📊 Score: {e['Score']}")
            st.write(f"📌 {e['Description']}")

            if e["Shot Result"]:
                st.write(f"🎯 Shot: {e['Shot Result']}")

            st.success(f"🕒 Timestamp {e['ET Time']}")

        st.success(f"Loaded {len(events)} events")

    except Exception as e:
        st.error(f"Failed to fetch data: {e}")
