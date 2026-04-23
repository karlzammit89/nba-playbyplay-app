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
        [1, 2, 3, 4],
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

        # Clock range only computed if filter enabled
        START_SEC = None
        END_SEC = None

        if USE_CLOCK_FILTER and MIN_CLOCK and MAX_CLOCK:
            START_SEC = clock_to_seconds(MAX_CLOCK)  # 00:00
            END_SEC = clock_to_seconds(MIN_CLOCK)    # 06:00

        events = []

        for play in plays:
            period = play.get("period")
            clock = format_clock(play.get("clock"))

            # -------------------------
            # QUARTER FILTER
            # -------------------------
            if USE_QUARTER_FILTER and period not in TARGET_QUARTERS:
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
                "Quarter": period,
                "Clock": clock,
                "Score": f"{play.get('scoreAway')} - {play.get('scoreHome')}",
                "Player": play.get("playerName"),
                "Description": play.get("description"),
                "Shot Result": play.get("shotResult"),
                "ET Time": convert_to_et(play.get("timeActual"))
            })

        st.subheader("🏀 Play by Play")

        for e in events:
            st.markdown("---")
            st.write(f"**Q{e['Quarter']} | {e['Clock']}**")
            st.write(f"Score: {e['Score']}")
            st.write(e["Description"])
            st.write(f"Real Time: {e['ET Time']}")

        st.success(f"Loaded {len(events)} events")

    except Exception as e:
        st.error(f"Failed to fetch data: {e}")
