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
# NEW: FETCH GAMES BY DATE
# =========================

@st.cache_data(ttl=60)
def get_games_by_date(date):
    date_str = date.strftime("%Y-%m-%d")

    url = f"https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_{date_str}.json"

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://www.nba.com/"
    }

    try:
        data = requests.get(url, headers=headers, timeout=10).json()
        games = data.get("scoreboard", {}).get("games", [])

        game_list = []

        for g in games:
            game_id = g.get("gameId")
            home = g.get("homeTeam", {}).get("teamName")
            away = g.get("awayTeam", {}).get("teamName")
            status = g.get("gameStatusText")

            label = f"{away} @ {home} ({status})"

            game_list.append((label, game_id))

        return game_list

    except Exception as e:
        st.error(f"Failed to fetch games: {e}")
        return []


# =========================
# UI
# =========================

st.title("🏀 NBA Dashboard")

# -------------------------
# DATE SEARCH (NEW)
# -------------------------
search_date = st.date_input("Select Game Date", datetime.today())

games = get_games_by_date(search_date)

game_id = None

if games:
    game_dict = {label: gid for label, gid in games}
    selected_game = st.selectbox("Select Game", list(game_dict.keys()))
    game_id = game_dict[selected_game]
else:
    st.warning("No games found for selected date")

# -------------------------
# Quarter Filter
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
# Game Clock Filter
# -------------------------
USE_CLOCK_FILTER = st.checkbox("Filter by Game Clock", value=False)

MIN_CLOCK = None
MAX_CLOCK = None

if USE_CLOCK_FILTER:
    MIN_CLOCK = st.text_input("Min Clock (MM:SS)", "06:00")
    MAX_CLOCK = st.text_input("Max Clock (MM:SS)", "00:00")

# -------------------------
# Actual Time Filter
# -------------------------
USE_TIME_FILTER = st.checkbox("Filter by Actual Time (ET)", value=False)

et_now = datetime.now(ZoneInfo("America/New_York"))

today_start = et_now.replace(hour=0, minute=0, second=0, microsecond=0)
today_end = et_now.replace(hour=23, minute=59, second=0, microsecond=0)

if "start_time" not in st.session_state:
    st.session_state.start_time = today_start.strftime("%Y-%m-%d %H:%M")

if "end_time" not in st.session_state:
    st.session_state.end_time = today_end.strftime("%Y-%m-%d %H:%M")

START_TIME = None
END_TIME = None

if USE_TIME_FILTER:
    START_TIME = st.text_input(
        "Start Time (YYYY-MM-DD HH:MM)",
        value=st.session_state.start_time,
        key="start_time"
    )

    END_TIME = st.text_input(
        "End Time (YYYY-MM-DD HH:MM)",
        value=st.session_state.end_time,
        key="end_time"
    )

run = st.button("Load Game Feed")


# =========================
# MAIN LOGIC
# =========================

if run and game_id:

    url = f"https://cdn.nba.com/static/json/liveData/playbyplay/playbyplay_{game_id}.json"

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://www.nba.com/"
    }

    try:
        data = requests.get(url, headers=headers, timeout=10).json()
        plays = data.get("game", {}).get("actions", [])

        START_SEC = None
        END_SEC = None

        if USE_CLOCK_FILTER and MIN_CLOCK and MAX_CLOCK:
            START_SEC = clock_to_seconds(MAX_CLOCK)
            END_SEC = clock_to_seconds(MIN_CLOCK)

        START_DT = None
        END_DT = None

        if USE_TIME_FILTER and START_TIME and END_TIME:
            START_DT = datetime.fromisoformat(START_TIME).replace(
                tzinfo=ZoneInfo("America/New_York")
            )
            END_DT = datetime.fromisoformat(END_TIME).replace(
                tzinfo=ZoneInfo("America/New_York")
            )

        events = []

        for play in plays:
            raw_period = play.get("period")
            period_display = normalize_period(raw_period)
            period_group = group_period_for_filter(period_display)

            clock = format_clock(play.get("clock"))
            actual_dt = parse_actual_time(play.get("timeActual"))

            # Quarter filter
            if USE_QUARTER_FILTER and period_group not in TARGET_QUARTERS:
                continue

            # Game clock filter
            if USE_CLOCK_FILTER:
                sec = clock_to_seconds(clock)
                if sec is not None and START_SEC is not None and END_SEC is not None:
                    if not (START_SEC <= sec <= END_SEC):
                        continue

            # Actual time filter
            if USE_TIME_FILTER and actual_dt and START_DT and END_DT:
                if not (START_DT <= actual_dt <= END_DT):
                    continue

            events.append({
                "Quarter": period_display,
                "Clock": clock,
                "Score": f"{play.get('scoreAway')} - {play.get('scoreHome')}",
                "Description": play.get("description"),
                "Shot Result": play.get("shotResult"),
                "ET Time": actual_dt.strftime("%Y-%m-%d %H:%M:%S %Z") if actual_dt else None
            })

        # =========================
        # OUTPUT
        # =========================

        for e in events:

            label = f"🔥 {e['Quarter']}" if str(e["Quarter"]).startswith("OT") else f"🏀 Q{e['Quarter']}"

            st.write(f"**{label} | ⏱️ {e['Clock']}**")
            st.write(f"📊 Score: {e['Score']}")
            st.write(f"📌 {e['Description']}")

            if e["Shot Result"]:
                st.write(f"🎯 Shot: {e['Shot Result']}")

            st.success(f"🕒 Timestamp: {e['ET Time']}")
            st.markdown("---")

        st.success(f"Loaded {len(events)} events")

    except Exception as e:
        st.error(f"Failed to fetch data: {e}")
