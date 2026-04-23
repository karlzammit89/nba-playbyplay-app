import streamlit as st
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

# =========================
# FUNCTIONS
# =========================

def convert_to_et(raw_time):
    if raw_time:
        dt = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
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
    """
    Convert NBA period to display format:
    1–4 -> 1–4
    5 -> OT 1
    6 -> OT 2
    """
    if period is None:
        return None
    if period >= 5:
        return f"OT {period - 4}"
    return period


def group_period_for_filter(period):
    """Map OT 1, OT 2... back to 'OT' for filtering"""
    if isinstance(period, str) and period.startswith("OT"):
        return "OT"
    return period


# =========================
# STREAMLIT UI
# =========================

st.title("🏀 NBA Dashboard")

game_id = st.text_input("Enter Game ID", "0042500132")

# -------------------------
# QUARTER FILTER (WITH OT)
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
# CLOCK FILTER (COLLAPSIBLE)
# -------------------------
USE_CLOCK_FILTER = st.checkbox("Filter by Game Clock", value=False)

MIN_CLOCK = None
MAX_CLOCK = None

if USE_CLOCK_FILTER:
    MIN_CLOCK = st.text_input("Min Clock (MM:SS)", "06:00")
    MAX_CLOCK = st.text_input("Max Clock (MM:SS)", "00:00")

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

        # Clock range only active if enabled
        START_SEC = None
        END_SEC = None

        if USE_CLOCK_FILTER and MIN_CLOCK and MAX_CLOCK:
            START_SEC = clock_to_seconds(MAX_CLOCK)  # 00:00
            END_SEC = clock_to_seconds(MIN_CLOCK)    # 06:00

        events = []

        for play in plays:
            raw_period = play.get("period")
            period_display = normalize_period(raw_period)
            period_group = group_period_for_filter(period_display)

            clock = format_clock(play.get("clock"))

            # -------------------------
            # QUARTER FILTER
            # -------------------------
            if USE_QUARTER_FILTER and period_group not in TARGET_QUARTERS:
                continue

            # -------------------------
            # CLOCK FILTER
            # -------------------------
            if USE_CLOCK_FILTER:
                sec = clock_to_seconds(clock)
                if sec is not None and START_SEC is not None and END_SEC is not None:
                    if not (START_SEC <= sec <= END_SEC):
                        continue

            events.append({
                "Quarter": period_display,
                "Clock": clock,
                "Score": f"{play.get('scoreAway')} - {play.get('scoreHome')}",
                "Player": play.get("playerName"),
                "Description": play.get("description"),
                "Shot Result": play.get("shotResult"),
                "ET Time": convert_to_et(play.get("timeActual"))
            })

        # =========================
        # OUTPUT
        # =========================

        st.subheader("🏀 Play by Play")

        for e in events:
            st.markdown("---")
            label = f"Q{e['Quarter']}" if not str(e['Quarter']).startswith("OT") else f"{e['Quarter']}"

st.write(f"**{label} | {e['Clock']}**")
            st.write(f"Score: {e['Score']}")
            st.write(e["Description"])
            st.write(f"Real Time: {e['ET Time']}")

        st.success(f"Loaded {len(events)} events")

    except Exception as e:
        st.error(f"Failed to fetch data: {e}")
