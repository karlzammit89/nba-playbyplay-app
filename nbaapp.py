import streamlit as st
import requests
from datetime import datetime, time as dtime, date as ddate, timedelta
from zoneinfo import ZoneInfo

# =========================
# PAGE CONFIG & TITLE
# =========================
st.set_page_config(page_title="NBA Dashboard", page_icon="🏀", layout="wide")
st.title("🏀 NBA Dashboard")

# Monday-first calendar via JS locale override
st.components.v1.html("""
<script>
(function() {
    const orig = Intl.DateTimeFormat;
    Intl.DateTimeFormat = function(l, o) { return new orig('en-GB', o); };
    Intl.DateTimeFormat.supportedLocalesOf = orig.supportedLocalesOf.bind(orig);
})();
</script>
""", height=0)

# =========================
# CONSTANTS
# =========================
ET = ZoneInfo("America/New_York")

# NBA team abbreviations keyed by full team name
TEAM_ABBREV = {
    "Atlanta Hawks": "ATL", "Boston Celtics": "BOS",
    "Brooklyn Nets": "BKN", "Charlotte Hornets": "CHA",
    "Chicago Bulls": "CHI", "Cleveland Cavaliers": "CLE",
    "Dallas Mavericks": "DAL", "Denver Nuggets": "DEN",
    "Detroit Pistons": "DET", "Golden State Warriors": "GSW",
    "Houston Rockets": "HOU", "Indiana Pacers": "IND",
    "Los Angeles Clippers": "LAC", "Los Angeles Lakers": "LAL",
    "Memphis Grizzlies": "MEM", "Miami Heat": "MIA",
    "Milwaukee Bucks": "MIL", "Minnesota Timberwolves": "MIN",
    "New Orleans Pelicans": "NOP", "New York Knicks": "NYK",
    "Oklahoma City Thunder": "OKC", "Orlando Magic": "ORL",
    "Philadelphia 76ers": "PHI", "Phoenix Suns": "PHX",
    "Portland Trail Blazers": "POR", "Sacramento Kings": "SAC",
    "San Antonio Spurs": "SAS", "Toronto Raptors": "TOR",
    "Utah Jazz": "UTA", "Washington Wizards": "WAS",
}

# NBA team ID → logo via cdn.nba.com
def nba_logo(team_id: int) -> str:
    return f"https://cdn.nba.com/logos/nba/{team_id}/global/L/logo.svg"

# Play type → emoji
PLAY_EMOJI = {
    "3pt":         "🔥",
    "2pt":         "🟢",
    "dunk":        "💥",
    "layup":       "🟢",
    "free throw":  "🎯",
    "turnover":    "❌",
    "steal":       "🏃",
    "block":       "🚫",
    "rebound":     "🔄",
    "foul":        "🟡",
    "substitution":"🔁",
    "timeout":     "⏸️",
    "violation":   "🚨",
    "jump ball":   "⬆️",
}

def play_emoji(desc: str) -> str:
    d = (desc or "").lower()
    for k, v in PLAY_EMOJI.items():
        if k in d:
            return v
    return "🏀"

# =========================
# SESSION STATE
# =========================
if "selected_game_id" not in st.session_state:
    st.session_state.selected_game_id   = None
if "selected_away_name" not in st.session_state:
    st.session_state.selected_away_name = ""
if "selected_home_name" not in st.session_state:
    st.session_state.selected_home_name = ""
if "selected_away_id" not in st.session_state:
    st.session_state.selected_away_id   = None
if "selected_home_id" not in st.session_state:
    st.session_state.selected_home_id   = None

# =========================
# HELPERS
# =========================
def abbrev(name: str) -> str:
    return TEAM_ABBREV.get(name, name[:3].upper())

def to_et(raw: str):
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(ET)
    except Exception:
        return None

def fmt_et(dt) -> str:
    return dt.strftime("%H:%M ET") if dt else "TBD"

def fmt_full_et(dt) -> str:
    if not dt:
        return "N/A"
    is_dst = dt.dst() != timedelta(0)
    label  = "EDT" if is_dst else "EST"
    return dt.strftime(f"%Y-%m-%d %H:%M:%S {label}")

def fmt_clock(clock: str) -> str:
    """Convert NBA ISO clock PT05M30.00S → 05:30"""
    if not clock:
        return ""
    try:
        c = clock.replace("PT", "").replace("S", "")
        mins, secs = c.split("M")
        secs = secs.split(".")[0]
        return f"{int(mins):02}:{int(secs):02}"
    except Exception:
        return clock

# =========================
# CACHED API CALLS
# =========================
@st.cache_data(ttl=300, show_spinner=False)
def fetch_schedule_raw() -> dict:
    return requests.get(
        "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json",
        timeout=10,
    ).json()

@st.cache_data(ttl=60, show_spinner=False)
def fetch_play_by_play(game_id: str) -> dict:
    return requests.get(
        f"https://cdn.nba.com/static/json/liveData/playbyplay/playbyplay_{game_id}.json",
        timeout=10,
    ).json()

@st.cache_data(ttl=60, show_spinner=False)
def fetch_boxscore(game_id: str) -> dict:
    return requests.get(
        f"https://cdn.nba.com/static/json/liveData/boxscore/boxscore_{game_id}.json",
        timeout=10,
    ).json()

# =========================
# SCHEDULE PARSER
# =========================
@st.cache_data(ttl=300, show_spinner=False)
def parse_schedule(date_str: str):
    raw  = fetch_schedule_raw()
    target = datetime.fromisoformat(date_str).date()
    games  = []

    for d in raw.get("leagueSchedule", {}).get("gameDates", []):
        for g in d.get("games", []):
            et_dt = to_et(g.get("gameDateTimeUTC"))
            if not et_dt or et_dt.date() != target:
                continue

            away      = g.get("awayTeam", {})
            home      = g.get("homeTeam", {})
            away_name = f"{away.get('teamCity','')} {away.get('teamName','')}".strip()
            home_name = f"{home.get('teamCity','')} {home.get('teamName','')}".strip()
            away_ab   = away.get("teamTricode") or abbrev(away_name)
            home_ab   = home.get("teamTricode") or abbrev(home_name)
            away_id   = away.get("teamId")
            home_id   = home.get("teamId")

            # Scores and status from schedule feed (may be 0 for upcoming)
            away_sc   = away.get("score", 0) or 0
            home_sc   = home.get("score", 0) or 0
            status    = g.get("gameStatusText", "Scheduled").strip()
            is_final  = "final" in status.lower()
            is_live   = g.get("gameStatus") == 2  # 1=pre, 2=live, 3=final

            # OT detection: period > 4
            period    = g.get("period", 4) or 4
            is_ot     = period > 4 and (is_final or is_live)

            games.append({
                "gameId":     g.get("gameId"),
                "away_name":  away_name,
                "home_name":  home_name,
                "away_abbr":  away_ab,
                "home_abbr":  home_ab,
                "away_id":    away_id,
                "home_id":    home_id,
                "away_logo":  nba_logo(away_id) if away_id else "",
                "home_logo":  nba_logo(home_id) if home_id else "",
                "time_str":   fmt_et(et_dt),
                "status":     status,
                "away_score": away_sc,
                "home_score": home_sc,
                "is_live_or_final": is_final or is_live,
                "is_ot":      is_ot,
            })

    return sorted(games, key=lambda x: x["time_str"])

# =========================
# PLAY PARSER
# =========================
@st.cache_data(ttl=60, show_spinner=False)
def parse_plays(game_id: str):
    raw   = fetch_play_by_play(game_id)
    plays = raw.get("game", {}).get("actions", [])
    events = []
    prev_total = 0

    for p in plays:
        period     = p.get("period", 0)
        clock_raw  = p.get("clock", "")
        clock_str  = fmt_clock(clock_raw)
        desc       = p.get("description", "")
        away_sc    = p.get("scoreAway") or 0
        home_sc    = p.get("scoreHome") or 0
        action_dt  = to_et(p.get("timeActual"))

        try:
            away_sc = int(away_sc)
            home_sc = int(home_sc)
        except (ValueError, TypeError):
            away_sc = home_sc = 0

        total    = away_sc + home_sc
        is_score = total > prev_total

        period_label = f"OT{period - 4}" if period > 4 else f"Q{period}"

        events.append({
            "period":        period,
            "period_label":  period_label,
            "clock_str":     clock_str,
            "desc":          desc,
            "away_score":    away_sc,
            "home_score":    home_sc,
            "score_str":     f"{away_sc} - {home_sc}",
            "is_scoring":    is_score,
            "action_dt":     action_dt,
            "action_dt_str": fmt_full_et(action_dt),
            "player":        p.get("playerNameI", ""),
            "action_type":   p.get("actionType", ""),
        })
        prev_total = total

    return events

# ======================================================
# GAME FEED VIEW
# ======================================================
if st.session_state.selected_game_id:

    game_id   = st.session_state.selected_game_id
    away_name = st.session_state.selected_away_name
    home_name = st.session_state.selected_home_name
    away_id   = st.session_state.selected_away_id
    home_id   = st.session_state.selected_home_id
    away_ab   = abbrev(away_name)
    home_ab   = abbrev(home_name)

    if st.button("⬅ Back to Schedule"):
        st.session_state.selected_game_id = None
        st.rerun()

    with st.spinner("Loading game data…"):
        events = parse_plays(game_id)

    # --- Live score from boxscore ---
    try:
        bs        = fetch_boxscore(game_id)
        bs_game   = bs.get("game", {})
        away_runs = bs_game.get("awayTeam", {}).get("score", 0)
        home_runs = bs_game.get("homeTeam", {}).get("score", 0)
    except Exception:
        away_runs = events[-1]["away_score"] if events else 0
        home_runs = events[-1]["home_score"] if events else 0

    # --- Header ---
    c1, c2, c3 = st.columns([1, 6, 1])
    with c1:
        st.image(nba_logo(away_id), width=60)
    with c2:
        st.markdown(
            f"""<div style="display:flex;align-items:center;justify-content:center;
                font-weight:700;font-size:clamp(16px,2.6vw,28px);gap:10px;flex-wrap:wrap;text-align:center;">
                <span>{away_ab}</span><span style="color:#888;">{away_runs}</span>
                <span>-</span>
                <span style="color:#888;">{home_runs}</span><span>{home_ab}</span>
            </div>""",
            unsafe_allow_html=True,
        )
    with c3:
        st.image(nba_logo(home_id), width=60)

    st.divider()

    # --- Filter defaults ---
    all_dts            = [e["action_dt"] for e in events if e["action_dt"]]
    game_start_default = min(all_dts) if all_dts else None
    game_end_default   = max(all_dts) if all_dts else None

    # --- Filters ---
    USE_QUARTER_FILTER  = st.checkbox("🏀 Filter by Quarter / OT", value=False)
    USE_TIME_FILTER     = st.checkbox("🕐 Filter by Actual Time (ET)", value=False)
    USE_SCORING_FILTER  = st.checkbox("🔥 Scoring Plays Only", value=False)

    START_DT = END_DT = None
    selected_quarters  = []

    if USE_QUARTER_FILTER:
        all_periods = sorted(
            {e["period_label"] for e in events},
            key=lambda x: (x.startswith("OT"), int(x[1:]) if x.startswith("Q") else int(x[2:]) + 100)
        )
        selected_quarters = st.multiselect("Select quarters", options=all_periods, default=[])

    if USE_TIME_FILTER:
        def_start_date = game_start_default.date() if game_start_default else ddate.today()
        def_end_date   = game_end_default.date()   if game_end_default   else ddate.today()
        def_start_time = game_start_default.time() if game_start_default else dtime(19, 0)
        def_end_time   = game_end_default.time()   if game_end_default   else dtime(23, 59)

        st.markdown("**Start date/time (ET)**")
        sc1, sc2 = st.columns(2)
        with sc1:
            start_date_input = st.date_input("Start date", value=def_start_date, key="tf_start_date")
        with sc2:
            start_time_input = st.time_input("Start time", value=def_start_time, step=60, key="tf_start_time")

        st.markdown("**End date/time (ET)**")
        ec1, ec2 = st.columns(2)
        with ec1:
            end_date_input = st.date_input("End date", value=def_end_date, key="tf_end_date")
        with ec2:
            end_time_input = st.time_input("End time", value=def_end_time, step=60, key="tf_end_time")

        START_DT = datetime.combine(start_date_input, start_time_input).replace(tzinfo=ET)
        END_DT   = datetime.combine(end_date_input,   end_time_input).replace(tzinfo=ET)

    run_filters = st.button("🚀 Apply Filters")

    def passes(e):
        if USE_QUARTER_FILTER:
            if not selected_quarters or e["period_label"] not in selected_quarters:
                return False
        if USE_TIME_FILTER:
            if not e["action_dt"] or START_DT is None or END_DT is None:
                return False
            if not (START_DT <= e["action_dt"] <= END_DT):
                return False
        if USE_SCORING_FILTER and not e["is_scoring"]:
            return False
        return True

    filtered = events if not run_filters else [e for e in events if passes(e)]

    # --- Info banners ---
    if run_filters:
        total   = len(events)
        showing = len(filtered)

        if showing == 0:
            st.warning("⚠️ No results found — please check the filters applied.")
            st.stop()

        if USE_QUARTER_FILTER:
            labels = selected_quarters if selected_quarters else ["none selected"]
            st.info(f"🏀 **Quarter filter:** {', '.join(labels)} — showing **{showing}** of **{total}** plays")

        if USE_TIME_FILTER:
            st.info(
                f"🕐 **Time filter:** {START_DT.strftime('%Y-%m-%d %H:%M')} → "
                f"{END_DT.strftime('%Y-%m-%d %H:%M')} ET — showing **{showing}** of **{total}** plays"
            )

        if USE_SCORING_FILTER:
            n_scoring = sum(1 for e in events if e["is_scoring"])
            st.info(f"🔥 **Scoring plays filter:** {n_scoring} scoring play(s) in game — showing **{showing}** of **{total}** plays")

    # --- Output ---
    for e in filtered:
        emoji = play_emoji(e["desc"])
        st.subheader(f"{emoji} {e['period_label']} | ⏱️ {e['clock_str']}")

        if e["is_scoring"]:
            st.markdown(f"📊 **Score:** {e['score_str']} &nbsp; 🔥 *Scoring Play!*")
        else:
            st.markdown(f"📊 **Score:** {e['score_str']}")

        if e["player"]:
            st.markdown(f"👤 **Player:** {e['player']}")

        st.markdown(f"📋 **Play:** {e['desc']}")

        col_t1, = st.columns(1)
        with col_t1:
            st.markdown(f"🕐 **Time (ET)**  \n`{e['action_dt_str']}`")

        st.divider()

# ======================================================
# SCHEDULE VIEW
# ======================================================
else:

    date     = st.date_input("Select date", datetime.today(), format="YYYY-MM-DD")
    date_str = date.strftime("%Y-%m-%d")
    st.markdown(f"## NBA Schedule — {date_str}")

    with st.spinner("Loading schedule…"):
        games = parse_schedule(date_str)

    if not games:
        st.info("No games scheduled for this date.")
        st.stop()

    st.markdown("""
<style>
div[data-testid="stVerticalBlockBorderWrapper"] {
    min-height: 150px;
}
.sched-team-row {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 4px;
}
.sched-team-row img {
    width: 34px;
    height: 34px;
    object-fit: contain;
}
.sched-team-name {
    font-size: 22px;
    font-weight: 800;
    letter-spacing: 0.4px;
}
.sched-score {
    font-size: 22px;
    font-weight: 800;
    color: #aaa;
    margin-left: auto;
}
.sched-meta {
    font-size: 13px;
    color: #999;
    margin-top: 4px;
    border-top: 1px solid rgba(255,255,255,0.08);
    padding-top: 5px;
}
.sched-extra {
    display: inline-block;
    background: #e67e22;
    color: #fff;
    font-size: 11px;
    font-weight: 700;
    padding: 1px 6px;
    border-radius: 4px;
    margin-left: 6px;
    vertical-align: middle;
    letter-spacing: 0.5px;
}
</style>
""", unsafe_allow_html=True)

    cols = st.columns(2)
    for i, g in enumerate(games):
        away_score_html = f'<span class="sched-score">{g["away_score"]}</span>' if g["is_live_or_final"] else ""
        home_score_html = f'<span class="sched-score">{g["home_score"]}</span>' if g["is_live_or_final"] else ""

        ot_badge = ' <span class="sched-extra">OT</span>' if g["is_ot"] else ""
        if g["is_live_or_final"]:
            meta = f'{g["time_str"]} &middot; {g["status"]}{ot_badge}'
        else:
            meta = f'{g["time_str"]} &middot; {g["status"]}'

        inner_html = f"""
<div class="sched-team-row">
  <img src="{g['away_logo']}" />
  <span class="sched-team-name">{g['away_abbr']}</span>
  {away_score_html}
</div>
<div class="sched-team-row">
  <img src="{g['home_logo']}" />
  <span class="sched-team-name">{g['home_abbr']}</span>
  {home_score_html}
</div>
<div class="sched-meta">{meta}</div>
"""

        with cols[i % 2]:
            with st.container(border=True):
                st.markdown(inner_html, unsafe_allow_html=True)
                if st.button(
                    f"▶  Open  {g['away_abbr']} @ {g['home_abbr']}",
                    key=f"go_{g['gameId']}",
                    use_container_width=True,
                ):
                    st.session_state.selected_game_id   = g["gameId"]
                    st.session_state.selected_away_name = g["away_name"]
                    st.session_state.selected_home_name = g["home_name"]
                    st.session_state.selected_away_id   = g["away_id"]
                    st.session_state.selected_home_id   = g["home_id"]
                    st.rerun()
