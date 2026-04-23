import streamlit as st
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

# =========================
# FUNCTIONS
# =========================

def parse_actual_time(raw_time):
    if not raw_time:
        return None
    return datetime.fromisoformat(raw_time.replace("Z", "+00:00")).astimezone(
        ZoneInfo("America/New_York")
    )


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

st.title("🏀 NBA Dashboard")

game_id = st.text_input("Enter Game ID", "0042500132")

run = st.button("Load Game Feed")

# =========================
# FILTERS (COLLAPSIBLE)
# =========================

with st.expander("🏀 Quarter Filter", expanded=False):
    USE_QUARTER_FILTER = st.checkbox("Enable Quarter Filter", value=False)
    TARGET_QUARTERS = st.multiselect(
        "Select Quarters",
        [1, 2, 3, 4, "OT"],
        default=[2],
        disabled=not USE_QUARTER_FILTER,
    )

with st.expander("⏱️ Game Clock Filter", expanded=False):
    USE_CLOCK_FILTER = st.checkbox("Enable Game Clock Filter", value=False)
    MIN_CLOCK = st.text_input("Min Clock (MM:SS)", "06:00", disabled=not USE_CLOCK_FILTER)
    MAX_CLOCK = st.text_input("Max Clock (MM:SS)", "00:00", disabled=not USE_CLOCK_FILTER)

with st.expander("🕒 Actual Time Filter (ET)", expanded=False):
    USE_TIME_FILTER = st.checkbox("Enable Actual Time Filter", value=False)

    if "START_TIME" not in st.session_state:
        st.session_state.START_TIME = "2024-01-01 12:00"
    if "END_TIME" not in st.session_state:
        st.session_state.END_TIME = "2026-12-31 23:59"

    START_TIME = st.text_input(
        "Start Time (YYYY-MM-DD HH:MM)",
        st.session_state.START_TIME,
        disabled=not USE_TIME_FILTER,
    )

    END_TIME = st.text_input(
        "End Time (YYYY-MM-DD HH:MM)",
        st.session_state.END_TIME,
        disabled=not USE_TIME_FILTER,
    )

    st.session_state.START_TIME = START_TIME
    st.session_state.END_TIME = END_TIME


# =========================
# MAIN LOGIC
# =========================

if run:
    url = f"https://cdn.nba.com/static/json/liveData/playbyplay/playbyplay_{game_id}.json"

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://www.nba.com/",
    }

    try:
        data = requests.get(url, headers=headers, timeout=10).json()
        plays = data.get("game", {}).get("actions", [])

        # -------------------------
        # CLOCK FILTER
        # -------------------------
        START_SEC = None
        END_SEC = None

        if USE_CLOCK_FILTER:
            START_SEC = clock_to_seconds(MAX_CLOCK)
            END_SEC = clock_to_seconds(MIN_CLOCK)

        # -------------------------
        # TIME FILTER
        # -------------------------
        START_DT = None
        END_DT = None

        if USE_TIME_FILTER:
            START_DT = datetime.fromisoformat(START_TIME).replace(
                tzinfo=ZoneInfo("America/New_York")
            )
            END_DT = datetime.fromisoformat(END_TIME).replace(
                tzinfo=ZoneInfo("America/New_York")
            )

        # -------------------------
        # EVENTS
        # -------------------------
        events = []

        for play in plays:
            period_display = normalize_period(play.get("period"))
            period_group = group_period_for_filter(period_display)

            clock = format_clock(play.get("clock"))
            actual_dt = parse_actual_time(play.get("timeActual"))

            if USE_QUARTER_FILTER and TARGET_QUARTERS and period_group not in TARGET_QUARTERS:
                continue

            if USE_CLOCK_FILTER:
                sec = clock_to_seconds(clock)
                if sec is not None and START_SEC is not None and END_SEC is not None:
                    if not (START_SEC <= sec <= END_SEC):
                        continue

            if USE_TIME_FILTER and actual_dt and START_DT and END_DT:
                if not (START_DT <= actual_dt <= END_DT):
                    continue

            events.append(
                {
                    "Quarter": period_display,
                    "Clock": clock,
                    "Score": f"{play.get('scoreAway')} - {play.get('scoreHome')}",
                    "Description": play.get("description"),
                    "Shot Result": play.get("shotResult"),
                    "ET Time": actual_dt.strftime("%Y-%m-%d %H:%M:%S %Z")
                    if actual_dt
                    else None,
                }
            )

        # -------------------------
        # OUTPUT
        # -------------------------
        for e in events:
            st.markdown("---")

            label = (
                f"🔥 {e['Quarter']}"
                if str(e["Quarter"]).startswith("OT")
                else f"🏀 Q{e['Quarter']}"
            )

            st.write(f"**{label} | ⏱️ {e['Clock']}**")
            st.write(f"📊 Score: {e['Score']}")
            st.write(f"📌 {e['Description']}")

            if e["Shot Result"]:
                st.write(f"🎯 Shot: {e['Shot Result']}")

            st.success(f"🕒 Timestamp {e['ET Time']}")

        st.success(f"Loaded {len(events)} events")

    except Exception as e:
        st.error(f"Failed to fetch data: {e}")
