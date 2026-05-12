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

# Scoring play emojis — only shown when the score actually changed
SCORING_EMOJI = {
    "3pt":       "🔥",
    "2pt":       "🟢",
    "dunk":      "💥",
    "layup":     "🟢",
    "free throw":"🎯",
}

# Non-scoring play emojis — always shown regardless of score
PLAY_EMOJI = {
    "turnover":    "❌",
    "steal":       "🏃",
    "block":       "🚫",
    "rebound":     "🔄",
    "foul":        "🟡",
    "substitution":"🔁",
    "sub":         "🔁",
    "timeout":     "⏸️",
    "violation":   "🚨",
    "jump ball":   "⬆️",
}

MISS_EMOJI = "🤦"   # shown when a shot attempt description contains "miss"

def nba_logo(team_id: int) -> str:
    return f"https://cdn.nba.com/logos/nba/{team_id}/global/L/logo.svg"

# =========================
# SESSION STATE INIT
# =========================
for key, default in {
    "selected_game_id":   None,
    "selected_away_name": "",
    "selected_home_name": "",
    "selected_away_id":   None,
    "selected_home_id":   None,
    # cached parsed events (keyed by game_id so stale data is never shown)
    "cached_events":      None,
    "cached_game_id":     None,
    # persisted filter result so reruns don't re-filter
    "filtered_events":    None,
    "filters_applied":    False,
    # last schedule date — defaults to today on first load, then persists
    "schedule_date":      datetime.today().date(),
    "last_refresh":       None,  # ET datetime of last manual refresh
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

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
    label = "EDT" if dt.dst() != timedelta(0) else "EST"
    return dt.strftime(f"%Y-%m-%d %H:%M:%S {label}")

def fmt_clock(clock: str) -> str:
    if not clock:
        return ""
    try:
        c = clock.replace("PT", "").replace("S", "")
        mins, secs = c.split("M")
        return f"{int(mins):02}:{int(secs.split('.')[0]):02}"
    except Exception:
        return clock

def _play_emoji(desc: str, is_scoring: bool) -> str:
    """
    Emoji selection rules:
    1. If description contains "miss" → always MISS_EMOJI (🤦), regardless of play type
    2. Scoring play emojis (3pt/dunk/layup etc.) → only shown if score actually changed
    3. Non-scoring emojis (rebound/foul/turnover etc.) → always shown
    4. Fallback → 🏀
    """
    d = (desc or "").lower()

    # Rule 1 — miss overrides everything
    if "miss" in d:
        return MISS_EMOJI

    # Rule 2 — scoring shot types only when score changed
    for k, v in SCORING_EMOJI.items():
        if k in d:
            return v if is_scoring else "🏀"

    # Rule 3 — non-scoring play types always shown
    for k, v in PLAY_EMOJI.items():
        if k in d:
            return v

    return "🏀"

# =========================
# CACHED API CALLS
# (Streamlit cache — survives reruns, keyed by args)
# =========================
# NBA CDN requires browser-like headers — without them it returns
# 403 / HTML error pages which cause JSONDecodeError.
NBA_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://www.nba.com/",
    "Origin":          "https://www.nba.com",
}

def _safe_get(url: str, timeout: int = 15) -> dict:
    """GET with NBA headers. Raises a clean st.error instead of a raw crash."""
    resp = requests.get(url, headers=NBA_HEADERS, timeout=timeout)
    if resp.status_code != 200:
        st.error(f"NBA API returned HTTP {resp.status_code} for {url}")
        st.stop()
    try:
        return resp.json()
    except Exception:
        st.error(
            f"NBA API returned non-JSON for {url}. "
            f"Response starts with: {resp.text[:120]!r}"
        )
        st.stop()

@st.cache_data(ttl=300, show_spinner=False)
def fetch_schedule_raw() -> dict:
    return _safe_get(
        "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json"
    )

@st.cache_data(ttl=60, show_spinner=False)
def fetch_play_by_play(game_id: str) -> list:
    """Returns raw play list — cached 60s so live games stay fresh."""
    data = _safe_get(
        f"https://cdn.nba.com/static/json/liveData/playbyplay/playbyplay_{game_id}.json"
    )
    return data.get("game", {}).get("actions", [])

@st.cache_data(ttl=60, show_spinner=False)
def fetch_boxscore_scores(game_id: str):
    """Returns (away_score, home_score) tuple — cached 60s."""
    try:
        data = _safe_get(
            f"https://cdn.nba.com/static/json/liveData/boxscore/boxscore_{game_id}.json"
        )
        g = data.get("game", {})
        return g.get("awayTeam", {}).get("score", 0), g.get("homeTeam", {}).get("score", 0)
    except Exception:
        return 0, 0

# =========================
# SCHEDULE PARSER (cached)
# =========================
@st.cache_data(ttl=300, show_spinner=False)
def parse_schedule(date_str: str):
    raw    = fetch_schedule_raw()
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
            away_sc   = away.get("score", 0) or 0
            home_sc   = home.get("score", 0) or 0
            game_status_code = g.get("gameStatus", 1)  # 1=pre, 2=live, 3=final
            status_raw = g.get("gameStatusText", "").strip()
            is_final  = game_status_code == 3
            is_live   = game_status_code == 2
            # NBA API puts the tipoff time (e.g. "7:00 pm ET") in gameStatusText
            # for pre-game — replace with a clean label so it doesn't duplicate.
            if game_status_code == 1:
                status = "Scheduled"
            elif is_live:
                status = status_raw or "Live"
            else:
                status = status_raw or "Final"
            period    = g.get("period", 4) or 4
            is_ot     = period > 4 and (is_final or is_live)

            games.append({
                "gameId":           g.get("gameId"),
                "away_name":        away_name,
                "home_name":        home_name,
                "away_abbr":        away_ab,
                "home_abbr":        home_ab,
                "away_id":          away_id,
                "home_id":          home_id,
                "away_logo":        nba_logo(away_id) if away_id else "",
                "home_logo":        nba_logo(home_id) if home_id else "",
                "time_str":         fmt_et(et_dt),
                "status":           status,
                "away_score":       away_sc,
                "home_score":       home_sc,
                "is_live_or_final": is_final or is_live,
                "is_ot":            is_ot,
            })

    return sorted(games, key=lambda x: x["time_str"])

# =========================
# PLAY PARSER
# Stored in session_state — only re-runs when game_id changes,
# NOT on every filter checkbox toggle / Apply click.
# =========================
def get_events(game_id: str) -> list:
    """
    Returns parsed event list from session_state cache.
    Only fetches+parses when the game_id differs from what's cached.
    This means filter interactions (reruns) never re-hit the API or re-parse.
    """
    if st.session_state.cached_game_id == game_id and st.session_state.cached_events is not None:
        return st.session_state.cached_events

    raw_plays  = fetch_play_by_play(game_id)   # Streamlit-cached, fast
    events     = []
    prev_total = 0

    for p in raw_plays:
        period    = p.get("period", 0)
        desc      = p.get("description", "")
        action_dt = to_et(p.get("timeActual"))

        try:
            away_sc = int(p.get("scoreAway") or 0)
            home_sc = int(p.get("scoreHome") or 0)
        except (ValueError, TypeError):
            away_sc = home_sc = 0

        total    = away_sc + home_sc
        is_score = total > prev_total
        p_label  = f"OT{period - 4}" if period > 4 else f"Q{period}"

        events.append({
            "period":        period,
            "period_label":  p_label,
            "clock_str":     fmt_clock(p.get("clock", "")),
            "desc":          desc,
            "away_score":    away_sc,
            "home_score":    home_sc,
            "score_str":     f"{away_sc} - {home_sc}",
            "is_scoring":    is_score,
            "action_dt":     action_dt,
            # pre-formatted strings — avoids repeated strftime in render loop
            "action_dt_str": fmt_full_et(action_dt),
            "player":        p.get("playerNameI", ""),
            # pre-computed emoji — avoids repeated dict scan in render loop
            "emoji":         _play_emoji(desc, is_score),
        })
        prev_total = total

    st.session_state.cached_events  = events
    st.session_state.cached_game_id = game_id
    return events

# ======================================================
# GAME FEED VIEW
# ======================================================
if st.session_state.selected_game_id:

    game_id   = st.session_state.selected_game_id
    away_abbr = st.session_state.selected_away_abbr
    home_abbr = st.session_state.selected_home_abbr
    away_id   = st.session_state.selected_away_id
    home_id   = st.session_state.selected_home_id

    nav_col1, nav_col2, _ = st.columns([1, 1, 7])
    
    with nav_col1:
        if st.button("⬅ Back to Schedule"):
            st.session_state.cached_events   = None
            st.session_state.cached_game_id  = None
            st.session_state.filtered_events = None
            st.session_state.filters_applied = False
            st.session_state.selected_game_id = None
            st.rerun()
            
    with nav_col2:
        if st.button("🔄 Refresh"):
            st.session_state.cached_events  = None
            st.session_state.cached_game_id = None
            st.session_state.last_refresh   = datetime.now(ET)
            fetch_play_by_play.clear()
            st.rerun()

    # Place this BELOW the 'with' blocks so it appears underneath
    if st.session_state.last_refresh:
        st.markdown(
            f"""
            <div style="
                background-color: #2e7d32; 
                color: white; 
                padding: 4px 12px; 
                border-radius: 4px; 
                font-size: 16px; 
                font-weight: bold;
                width: fit-content;
                margin-top: -5px; /* Pulls it slightly closer to the buttons */
                margin-bottom: 20px;
            ">
                Last refresh {st.session_state.last_refresh.strftime('%H:%M:%S ET')}
            </div>
            """,
            unsafe_allow_html=True,
        )

    with st.spinner("Loading game data…"):
        away_abbr, home_abbr, away_id, home_id, status_detail, events = get_events(game_id)

    # Latest scores from last play
    if events:
        last = events[-1]
        away_runs, home_runs = last["away_score"], last["home_score"]
    else:
        away_runs = home_runs = 0

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

    # --- Filter defaults (computed once from events, not on every rerun) ---
    all_dts            = [e["action_dt"] for e in events if e["action_dt"]]
    game_start_default = min(all_dts) if all_dts else None
    game_end_default   = max(all_dts) if all_dts else None

    all_periods = sorted(
        {e["period_label"] for e in events},
        key=lambda x: (x.startswith("OT"), int(x[1:]) if x.startswith("Q") else int(x[2:]) + 100)
    )

    # --- Filter checkboxes ---
    USE_QUARTER_FILTER = st.checkbox("🏀 Filter by Quarter / OT", value=False)
    USE_TIME_FILTER    = st.checkbox("🕐 Filter by Actual Time (ET)", value=False)
    USE_SCORING_FILTER = st.checkbox("🔥 Scoring Plays Only", value=False)

    START_DT = END_DT  = None
    selected_quarters  = []

    if USE_QUARTER_FILTER:
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

    # --- Apply button ---
    if st.button("🚀 Apply Filters"):
        # Run filter once on click, store result — subsequent reruns skip this
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

        st.session_state.filtered_events = [e for e in events if passes(e)]
        st.session_state.filters_applied = True

    # Use stored filtered result if available, otherwise show all
    filters_applied = st.session_state.filters_applied
    filtered        = st.session_state.filtered_events if filters_applied else events

    # --- Info banners ---
    if filters_applied:
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

    # --- Output (render loop — no API calls, no parsing, no emoji lookups) ---
    for e in filtered:
        st.subheader(f"{e['emoji']} {e['period_label']} | ⏱️ {e['clock_str']}")

        if e["is_scoring"]:
            st.markdown(f"📊 **Score:** {e['score_str']} &nbsp; 🔥 *Scoring Play!*")
        else:
            st.markdown(f"📊 **Score:** {e['score_str']}")

        if e["player"]:
            st.markdown(f"👤 **Player:** {e['player']}")

        st.markdown(f"📋 **Play:** {e['desc']}")
        st.markdown(f"🕐 **Time (ET)** `{e['action_dt_str']}`")

        st.divider()

# ======================================================
# SCHEDULE VIEW
# ======================================================
else:

    date     = st.date_input("Select date", st.session_state.schedule_date, format="YYYY-MM-DD")
    # Persist whatever date the user picks so Back to Schedule restores it
    st.session_state.schedule_date = date
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
        ot_badge        = ' <span class="sched-extra">OT</span>' if g["is_ot"] else ""

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
                    # Clear any stale filter state from previous game
                    st.session_state.cached_events   = None
                    st.session_state.cached_game_id  = None
                    st.session_state.filtered_events = None
                    st.session_state.filters_applied = False
                    st.session_state.selected_game_id   = g["gameId"]
                    st.session_state.selected_away_name = g["away_name"]
                    st.session_state.selected_home_name = g["home_name"]
                    st.session_state.selected_away_id   = g["away_id"]
                    st.session_state.selected_home_id   = g["home_id"]
                    st.rerun()
