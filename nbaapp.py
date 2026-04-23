import streamlit as st
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

# =========================
# FUNCTIONS
# =========================

def convert_to_et(raw_time):
    """Convert ISO timestamp (UTC) -> Eastern Time"""
    if raw_time:
        dt = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
        return dt.astimezone(ZoneInfo("America/New_York"))
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
# STREAMLIT UI
# =========================

st.title("🏀 NBA Dashboard")

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
# GAME CLOCK FILTER
# -------------------------
USE_CLOCK_FILTER = st.checkbox("Filter by Game Clock", value=False)

MIN_CLOCK = None
MAX_CLOCK = None

if USE_CLOCK_FILTER:
    MIN_CLOCK = st.text_input("Min Clock (MM:SS)", "06:00")
    MAX_CLOCK = st.text_input("Max Clock (MM:SS)", "00:00")


# -------------------------
# EASTERN TIME FILTER (NEW)
# -------------------------
USE_ET_FILTER = st.checkbox("Filter by Eastern Time (ET)", value=False)

START_ET = None
END_ET = None

if USE_ET_FILTER:
    col1, col2 = st.columns(2)

    with col1:
        START_ET = st.time_input("Start ET Time")

    with col2:
        END_ET = st.time_input("End ET Time")


run = st.button("Load Game Feed")


# =========================
# DATA FETCH (EXAMPLE)
# =========================

def fetch_game_data(game_id):
    """
    Replace this with your real NBA API endpoint
    """
    url = f"https://your-api.com/playbyplay/{game_id}"
    response = requests.get(url)
    return response.json()


# =========================
# MAIN LOGIC
# =========================

if run:

    st.info("Loading game data...")

    data = fetch_game_data(game_id)

    plays = data.get("plays", [])

    filtered_plays = []

    for play in plays:

        # -------------------------
        # PERIOD FILTER
        # -------------------------
        period = play.get("period")

        norm_period = normalize_period(period)
        group_period = group_period_for_filter(norm_period)

        if USE_QUARTER_FILTER:
            if group_period not in TARGET_QUARTERS:
                continue

        # -------------------------
        # CLOCK FILTER
        # -------------------------
        clock = play.get("clock")
        clock_sec = clock_to_seconds(format_clock(clock))

        if USE_CLOCK_FILTER and clock_sec is not None:
            min_sec = clock_to_seconds(MIN_CLOCK)
            max_sec = clock_to_seconds(MAX_CLOCK)

            if min_sec is not None and clock_sec < min_sec:
                continue
            if max_sec is not None and clock_sec > max_sec:
                continue

        # -------------------------
        # ET FILTER (NEW LOGIC)
        # -------------------------
        raw_time = play.get("date_time") or play.get("event_time") or play.get("timestamp")

        event_et = convert_to_et(raw_time)

        if USE_ET_FILTER and event_et:
            event_time_only = event_et.time()

            if START_ET and event_time_only < START_ET:
                continue
            if END_ET and event_time_only > END_ET:
                continue

        # -------------------------
        # KEEP PLAY
        # -------------------------
        play["event_et"] = event_et.strftime("%Y-%m-%d %H:%M:%S %Z") if event_et else None

        filtered_plays.append(play)

    # =========================
    # OUTPUT
    # =========================

    st.success(f"Loaded {len(filtered_plays)} filtered plays")

    for play in filtered_plays:
        st.write({
            "period": play.get("period"),
            "clock": play.get("clock"),
            "description": play.get("description"),
            "ET Time": play.get("event_et")
        })
