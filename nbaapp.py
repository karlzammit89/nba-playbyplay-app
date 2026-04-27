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


def format_clock(clock):
    if not clock:
        return None
    try:
        # Convert ISO clock (PT03M59.00S) → MM:SS
        clock = clock.replace("PT", "").replace("S", "")
        minutes, seconds = clock.split("M")
        seconds = seconds.split(".")[0]
        return f"{int(minutes):02}:{int(seconds):02}"
    except:
        return clock


# =========================
# MODE 1 — SCHEDULE
# =========================
if mode == "Schedule":

    date_input = st.text_input("Enter date (YYYY-MM-DD)", "2026-04-25")

    if st.button("Load Games"):

        try:
            selected_date = datetime.fromisoformat(date_input).date()
        except:
            st.error("Invalid date format")
            st.stop()

        url = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json"
        data = requests.get(url, timeout=10).json()

        games = []

        for d in data.get("leagueSchedule", {}).get("gameDates", []):
            for game in d.get("games", []):

                game_id = game.get("gameId")

                away = game.get("awayTeam", {}).get("teamName")
                home = game.get("homeTeam", {}).get("teamName")

                et_dt = convert_to_et(game.get("gameDateTimeUTC"))

                if not et_dt:
                    continue

                # ✅ Match TRUE Eastern date
                if et_dt.date() != selected_date:
                    continue

                games.append({
                    "gameId": game_id,
                    "matchup": f"{away} @ {home}",
                    "time": et_dt.strftime("%H:%M")
                })

        if games:
            for game in sorted(games, key=lambda x: x["time"]):
                st.write(f"{game['gameId']} | 🏀 {game['matchup']} | 🕒 {game['time']} (ET)")
        else:
            st.warning("No games found for selected ET date")


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
        data = requests.get(url, timeout=10).json()

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
            clock = format_clock(play.get("clock"))  # ✅ FIXED
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

        # =========================
        # OUTPUT
        # =========================
        for e in events:

            label = f"🔥 OT" if e["period"] >= 5 else f"🏀 Q{e['period']}"

            st.write(f"**{label} | ⏱️ {e['clock']}**")
            st.write(f"📊 Score: {e['score']}")
            st.write(f"📌 {e['desc']}")
            st.success(f"🕒 {e['time']}")
            st.markdown("---")

        st.success(f"Loaded {len(events)} events")
