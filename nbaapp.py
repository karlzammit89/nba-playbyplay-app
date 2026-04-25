import streamlit as st
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# =========================
# TITLE
# =========================
st.title("🏀 NBA Dashboard")

# =========================
# MODE
# =========================
mode = st.radio("Select Mode", ["Schedule", "Game Feed"])

# =========================
# HELPERS
# =========================
def convert_to_et(raw_time):
    if not raw_time:
        return None
    try:
        dt = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
        return dt.astimezone(ZoneInfo("America/New_York")).replace(microsecond=0)
    except:
        return None


def convert_to_et_str(raw_time):
    dt = convert_to_et(raw_time)
    if not dt:
        return None

    is_dst = dt.dst() != timedelta(0)
    tz_label = "EDT" if is_dst else "EST"

    return dt.strftime(f"%Y-%m-%d %H:%M:%S {tz_label}")


# =========================
# MODE 1 — SCHEDULE
# =========================
if mode == "Schedule":

    date = st.text_input("Enter date (YYYY-MM-DD)", "2026-04-25")

    if st.button("Load Games"):

        url = f"https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json"
        data = requests.get(url).json()

        games = []

        for g in data.get("scoreboard", {}).get("games", []):
            game_id = g.get("gameId")

            away = g.get("awayTeam", {}).get("teamName")
            home = g.get("homeTeam", {}).get("teamName")

            game_time = convert_to_et_str(g.get("gameTimeUTC"))

            games.append({
                "gameId": game_id,
                "matchup": f"{away} @ {home}",
                "time": game_time
            })

        if games:
            for game in games:
                time_only = game["time"].split(" ")[1][:5] if game["time"] else "N/A"
                st.write(f"{game['gameId']} | 🏀 {game['matchup']} | 🕒 {time_only} (ET)")
        else:
            st.warning("No games found")


# =========================
# MODE 2 — GAME FEED
# =========================
if mode == "Game Feed":

    game_id = st.text_input("Enter Game ID", "0042500132")

    USE_QUARTER_FILTER = st.checkbox("Filter by Quarter", value=False)
    TARGET_QUARTERS = []

    if USE_QUARTER_FILTER:
        TARGET_QUARTERS = st.multiselect(
            "Select Quarters",
            [1, 2, 3, 4, "OT"],
            default=[2]
        )

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
        START_TIME = st.text_input("Start Time (YYYY-MM-DD HH:MM)", st.session_state.start_time)
        END_TIME = st.text_input("End Time (YYYY-MM-DD HH:MM)", st.session_state.end_time)

    if st.button("Load Game Feed"):

        url = f"https://cdn.nba.com/static/json/liveData/playbyplay/playbyplay_{game_id}.json"
        data = requests.get(url).json()

        plays = data.get("game", {}).get("actions", [])

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

            period = play.get("period")
            clock = play.get("clock")
            desc = play.get("description")

            actual_dt = convert_to_et(play.get("timeActual"))

            # Quarter filter
            if USE_QUARTER_FILTER:
                if period >= 5 and "OT" not in TARGET_QUARTERS:
                    continue
                if period <= 4 and period not in TARGET_QUARTERS:
                    continue

            # Time filter
            if USE_TIME_FILTER and actual_dt and START_DT and END_DT:
                if not (START_DT <= actual_dt <= END_DT):
                    continue

            events.append({
                "period": period,
                "clock": clock,
                "desc": desc,
                "score": f"{play.get('scoreAway')} - {play.get('scoreHome')}",
                "time": convert_to_et_str(play.get("timeActual"))
            })

        # OUTPUT
        for e in events:

            label = f"🔥 OT" if e["period"] >= 5 else f"🏀 Q{e['period']}"

            st.write(f"**{label} | ⏱️ {e['clock']}**")
            st.write(f"📊 Score: {e['score']}")
            st.write(f"📌 {e['desc']}")
            st.success(f"🕒 {e['time']}")
            st.markdown("---")

        st.success(f"Loaded {len(events)} events")
