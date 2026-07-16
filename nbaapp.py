import streamlit as st
import requests
from datetime import datetime, time as dtime, date as ddate, timedelta
from zoneinfo import ZoneInfo
import time

# =========================
# PAGE CONFIG & TITLE
# =========================
st.set_page_config(page_title="NBA Play by Play", page_icon="🏀", layout="wide")
st.title("🏀 NBA Play by Play")

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

# ESPN endpoints — same pattern as WNBA/NHL, sport slug = nba
ESPN_HEADERS    = {"User-Agent": "Mozilla/5.0 (compatible; NBA-Dashboard/1.0)"}
ESPN_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
ESPN_SUMMARY    = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary"

def nba_logo(logo_url: str) -> str:
    """Return ESPN-provided logo URL directly. ESPN scoreboard gives full URL."""
    return logo_url or ""

# Scoring play emojis — only shown when the score actually changed
SCORING_EMOJI = {
    "3pt":        "🔥",
    "2pt":        "🟢",
    "dunk":       "💥",
    "layup":      "🟢",
    "free throw": "🎯",
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

# =========================
# SESSION STATE INIT
# =========================
for key, default in {
    "selected_game_id":   None,
    # cached parsed events (keyed by game_id so stale data is never shown)
    "cached_events":      None,
    "cached_game_id":     None,
    # persisted filter result so reruns don't re-filter
    "filtered_events":    None,
    "filters_applied":    False,
    # FIX 4: stores the filter state *at the time Apply was clicked*
    # so banners reflect what was actually applied, not current checkbox state
    "applied_filter_state": {},
    # last schedule date — defaults to today on first load, then persists
    "schedule_date":      datetime.today().date(),
    "last_refresh":       None,
    "force_bucket":       0,
    "sort_newest_first":  False,
    # ESPN event id + fallback scores (stored at game entry)
    "selected_event_id":   None,
    "selected_away_score": 0,
    "selected_home_score": 0,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# =========================
# HELPERS
# =========================
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

def _play_emoji(desc: str, is_scoring: bool) -> str:
    """
    Emoji selection rules:
    1. If description contains "miss" → always MISS_EMOJI (🤦)
    2. Scoring play emojis (3pt/dunk/layup etc.) → only shown if score changed
    3. Non-scoring emojis (rebound/foul/turnover etc.) → always shown
    4. Fallback → 🏀
    """
    d = (desc or "").lower()
    if "miss" in d:
        return MISS_EMOJI
    for k, v in SCORING_EMOJI.items():
        if k in d:
            return v if is_scoring else "🏀"
    for k, v in PLAY_EMOJI.items():
        if k in d:
            return v
    return "🏀"

# =========================
# CACHED API CALLS
# =========================
@st.cache_data(ttl=300, show_spinner=False)
def fetch_schedule(date_str: str) -> list:
    """ESPN NBA scoreboard — same pattern as WNBA/NHL, proven on Streamlit Cloud.
    date_str: YYYY-MM-DD. ESPN wants YYYYMMDD — converted inside.
    Returns list of parsed game dicts.
    Source: WNBA doc25 fetch_schedule, sport slug wnba→nba.
    """
    url  = f"{ESPN_SCOREBOARD}?dates={date_str.replace('-', '')}&limit=50"
    try:
        resp = requests.get(url, headers=ESPN_HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        st.error(f"ESPN schedule error: {e}")
        return []

    games = []
    for event in data.get("events", []):
        comp        = (event.get("competitions") or [{}])[0]
        status      = comp.get("status", {})
        state       = status.get("type", {}).get("state", "")  # pre/in/post
        detail      = status.get("type", {}).get("detail", "")
        competitors = comp.get("competitors", [])
        away_info   = next((c for c in competitors if c.get("homeAway") == "away"), {})
        home_info   = next((c for c in competitors if c.get("homeAway") == "home"), {})
        away_abbr   = away_info.get("team", {}).get("abbreviation", "?")
        home_abbr   = home_info.get("team", {}).get("abbreviation", "?")
        away_logo   = away_info.get("team", {}).get("logo", "")
        home_logo   = home_info.get("team", {}).get("logo", "")
        away_score  = int(away_info.get("score", 0) or 0)
        home_score  = int(home_info.get("score", 0) or 0)
        et_dt       = to_et(comp.get("date", ""))
        is_live     = state == "in"
        is_final    = state == "post"
        period      = status.get("period", 0) or 0
        is_ot       = period > 4 and (is_live or is_final)
        if is_live:
            disp_clock   = status.get("displayClock", "")
            status_badge = f"LIVE — Q{period} {disp_clock}"
        elif is_final:
            status_badge = "Final"
        else:
            status_badge = "Scheduled"
        games.append({
            "gameId":           event.get("id", ""),
            "away_abbr":        away_abbr,
            "home_abbr":        home_abbr,
            "away_logo":        away_logo,
            "home_logo":        home_logo,
            "away_score":       away_score,
            "home_score":       home_score,
            "time_str":         fmt_et(et_dt),
            "status":           status_badge,
            "is_live_or_final": is_live or is_final,
            "is_ot":            is_ot,
        })
    return sorted(games, key=lambda x: x["time_str"])

@st.cache_data(ttl=60, show_spinner=False)
def fetch_play_by_play(game_id: str, cache_bucket: int = 0) -> tuple:
    """ESPN NBA summary — same pattern as WNBA, sport slug wnba→nba.
    Returns (away_abbr, home_abbr, away_logo, home_logo, status_detail, plays_raw).
    Source: WNBA doc25 fetch_play_by_play exact.
    """
    url  = f"{ESPN_SUMMARY}?event={game_id}"
    try:
        resp = requests.get(url, headers=ESPN_HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        st.error(f"ESPN play-by-play error: {e}")
        st.stop()
    header      = data.get("header", {})
    competitions = header.get("competitions", [{}])
    comp         = competitions[0] if competitions else {}
    competitors  = comp.get("competitors", [])
    away_info    = next((c for c in competitors if c.get("homeAway") == "away"), {})
    home_info    = next((c for c in competitors if c.get("homeAway") == "home"), {})
    away_abbr    = away_info.get("team", {}).get("abbreviation", "?")
    home_abbr    = home_info.get("team", {}).get("abbreviation", "?")
    away_logo    = away_info.get("team", {}).get("logo", "")
    home_logo    = home_info.get("team", {}).get("logo", "")
    status_detail = comp.get("status", {}).get("type", {}).get("detail", "")
    plays_raw    = data.get("plays", [])
    return away_abbr, home_abbr, away_logo, home_logo, status_detail, plays_raw

# =========================
# PLAY PARSER
# =========================
def get_events(game_id: str) -> tuple:
    """Returns (away_abbr, home_abbr, away_logo, home_logo, status_detail, events).
    Caches in session_state — filter reruns never re-hit the API.
    Source: WNBA doc25 get_events, ESPN field names.
    """
    if st.session_state.cached_game_id == game_id and st.session_state.cached_events is not None:
        return st.session_state.cached_events

    bucket = st.session_state.get("force_bucket", 0)
    away_abbr, home_abbr, away_logo, home_logo, status_detail, plays_raw = \
        fetch_play_by_play(game_id, cache_bucket=bucket)

    events     = []
    prev_away = prev_home = 0

    for p in plays_raw:
        # ESPN field names (source: WNBA doc25)
        period    = p.get("period", {}).get("number", 0)
        clock_str = p.get("clock", {}).get("displayValue", "")  # already "MM:SS"
        desc      = p.get("text", "No description")
        action_dt = to_et(p.get("wallclock", ""))
        ptype     = p.get("type", {}).get("text", "")

        try:
            away_sc = int(p.get("awayScore", 0) or 0)
            home_sc = int(p.get("homeScore", 0) or 0)
        except (ValueError, TypeError):
            away_sc = home_sc = 0

        is_score = (away_sc + home_sc) > (prev_away + prev_home)
        prev_away, prev_home = away_sc, home_sc
        p_label  = f"OT{period - 4}" if period > 4 else f"Q{period}"

        # Player name: ESPN nests under participants (WNBA doc25 pattern)
        participants = p.get("participants", [])
        player = ""
        if participants:
            player = participants[0].get("athlete", {}).get("displayName", "")

        events.append({
            "period":        period,
            "period_label":  p_label,
            "clock_str":     clock_str,
            "desc":          desc,
            "away_score":    away_sc,
            "home_score":    home_sc,
            "score_str":     f"{away_sc} - {home_sc}",
            "is_scoring":    is_score,
            "action_dt":     action_dt,
            "action_dt_str": fmt_full_et(action_dt),
            "player":        player,
            "type":          ptype,
            "emoji":         _play_emoji(desc, is_score),
        })

    result = (away_abbr, home_abbr, away_logo, home_logo, status_detail, events)
    st.session_state.cached_events  = result
    st.session_state.cached_game_id = game_id
    return result

# ======================================================
# GAME FEED VIEW
# ======================================================
if st.session_state.selected_game_id:

    game_id = st.session_state.selected_game_id
    # Abbr/logo read after get_events() — ESPN provides them directly

    nav_col1, nav_col2, nav_col3, nav_col4, _ = st.columns([1.3, 0.9, 1.1, 1.8, 4.9])

    with nav_col1:
        if st.button("⬅ Back to Schedule", use_container_width=True):
            st.session_state.cached_events      = None
            st.session_state.cached_game_id     = None
            st.session_state.filtered_events    = None
            st.session_state.filters_applied    = False
            st.session_state.applied_filter_state = {}
            st.session_state.last_refresh       = None
            st.session_state.selected_game_id   = None
            st.rerun()

    with nav_col2:
        def _do_refresh():
            """Per-user cache bust — never calls .clear() (would affect all users)."""
            st.session_state.force_bucket   = int(time.time() // 30) + 1
            st.session_state.cached_events  = None
            st.session_state.cached_game_id = None
        st.button("🔄 Refresh", use_container_width=True, on_click=_do_refresh)

    with nav_col3:
        sort_label = "↓ Oldest first" if not st.session_state.sort_newest_first else "↑ Newest first"
        sort_type  = "secondary" if not st.session_state.sort_newest_first else "primary"
        if st.button(sort_label, use_container_width=True, type=sort_type, key="sort_toggle"):
            st.session_state.sort_newest_first = not st.session_state.sort_newest_first
            st.rerun()

    with nav_col4:
        refresh_time = st.session_state.last_refresh.strftime("%H:%M:%S ET")
        st.markdown(
            f'<div style="background-color:#2e7d32;color:white;padding:8px 16px;'
            f'border-radius:4px;font-size:14px;font-weight:bold;text-align:center;">'
            f'Last refresh {refresh_time}</div>',
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # Only show spinner on true first load (cache miss)
    _cache_hit = (st.session_state.cached_game_id == game_id
                  and st.session_state.cached_events is not None)
    if _cache_hit:
        away_abbr, home_abbr, away_logo, home_logo, status_detail, events = get_events(game_id)
    else:
        with st.spinner("Loading game data…"):
            away_abbr, home_abbr, away_logo, home_logo, status_detail, events = get_events(game_id)
        # last_refresh updated AFTER fetch completes so timestamp is accurate
        st.session_state.last_refresh = datetime.now(ET)

    # Score: from last event (ESPN scores are in every play row)
    # Falls back to entry-time scores stored in session state
    if events:
        away_runs = events[-1]["away_score"]
        home_runs = events[-1]["home_score"]
    else:
        away_runs = st.session_state.selected_away_score
        home_runs = st.session_state.selected_home_score

    # --- Header ---
    c1, c2, c3 = st.columns([1, 6, 1])
    with c1:
        st.image(nba_logo(away_logo), width=60)
    with c2:
        st.markdown(
            f"""<div style="display:flex;align-items:center;justify-content:center;
                font-weight:700;font-size:clamp(16px,2.6vw,28px);gap:10px;flex-wrap:wrap;text-align:center;">
                <span>{away_abbr}</span><span style="color:#888;">{away_runs}</span>
                <span>-</span>
                <span style="color:#888;">{home_runs}</span><span>{home_abbr}</span>
            </div>""",
            unsafe_allow_html=True,
        )
    with c3:
        st.image(nba_logo(home_logo), width=60)

    st.divider()

    # --- Filter defaults ---
    all_dts            = [e["action_dt"] for e in events if e["action_dt"]]
    game_start_default = min(all_dts) if all_dts else None
    game_end_default   = max(all_dts) if all_dts else None

    all_periods = sorted(
        {e["period_label"] for e in events},
        key=lambda x: (x.startswith("OT"), int(x[1:]) if x.startswith("Q") else int(x[2:]) + 100)
    )

    # --- Filter checkboxes ---
    USE_QUARTER_FILTER = st.checkbox("🏀 Filter by Quarter / OT", value=False, key="cb_quarter")
    USE_TIME_FILTER    = st.checkbox("🕐 Filter by Actual Time (ET)", value=False, key="cb_time")
    USE_SCORING_FILTER = st.checkbox("🔥 Scoring Plays Only", value=False, key="cb_scoring")

    START_DT = END_DT  = None
    selected_quarters  = []

    if USE_QUARTER_FILTER:
        selected_quarters = st.multiselect("Select quarters", options=all_periods, default=[], key="ms_quarter")

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

    # --- Action Buttons ---
    btn_col1, btn_col2, _ = st.columns([1.5, 1.5, 7])

    with btn_col1:
        if st.button("🚀 Apply Filters", use_container_width=True):
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

            # FIX 4: snapshot exactly which filters were active and their values
            # at Apply time — banners use this, not live checkbox state
            st.session_state.applied_filter_state = {
                "quarter":  USE_QUARTER_FILTER,
                "quarters": list(selected_quarters),
                "time":     USE_TIME_FILTER,
                "start_dt": START_DT,
                "end_dt":   END_DT,
                "scoring":  USE_SCORING_FILTER,
            }

    with btn_col2:
        # FIX 3: disabled when no filters are currently applied
        def reset_filters():
            st.session_state.filters_applied      = False
            st.session_state.filtered_events      = None
            st.session_state.applied_filter_state = {}
            st.session_state.cb_quarter = False
            st.session_state.cb_time    = False
            st.session_state.cb_scoring = False
            if "ms_quarter" in st.session_state:
                st.session_state.ms_quarter = []

        st.button(
            "🗑️ Remove Filters",
            use_container_width=True,
            on_click=reset_filters,
            disabled=not st.session_state.get("filters_applied", False),  # FIX 3
        )

    # Resolve which events to show
    filters_applied = st.session_state.filters_applied
    filtered        = st.session_state.filtered_events if filters_applied else None

    # FIX 4: banners use the snapshotted state from Apply time, not live checkboxes
    afs = st.session_state.applied_filter_state  # short alias

    if filters_applied and filtered is not None:
        total   = len(events)
        showing = len(filtered)

        if showing == 0:
            st.warning("⚠️ No results found — please check the filters applied.")
            st.stop()

        # Only show a banner for filters that were active when Apply was clicked
        if afs.get("quarter"):
            labels = afs["quarters"] if afs["quarters"] else ["none selected"]
            st.info(f"🏀 **Quarter filter:** {', '.join(str(l) for l in labels)} — showing **{showing}** of **{total}** plays")

        if afs.get("time") and afs.get("start_dt") and afs.get("end_dt"):
            st.info(
                f"🕐 **Time filter:** {afs['start_dt'].strftime('%Y-%m-%d %H:%M')} → "
                f"{afs['end_dt'].strftime('%Y-%m-%d %H:%M')} ET — showing **{showing}** of **{total}** plays"
            )

        if afs.get("scoring"):
            n_scoring = sum(1 for e in events if e["is_scoring"])
            st.info(f"🔥 **Scoring plays filter:** {n_scoring} scoring play(s) in game — showing **{showing}** of **{total}** plays")

    display_events = filtered if filters_applied else events
    # Sort applied AFTER filters, at render time only — stored list never mutated
    if st.session_state.sort_newest_first:
        display_events = display_events[::-1]
    for e in display_events:
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

    # key="schedule_date" lets Streamlit own widget state internally.
    # The init block seeds it with today on first load.
    # No manual write-back needed — Streamlit syncs key↔session_state automatically,
    # so the value never reverts on re-render.
    date     = st.date_input("Select date", key="schedule_date", format="YYYY-MM-DD")
    date_str = date.strftime("%Y-%m-%d")  # fetch_schedule converts internally
    st.markdown(f"## NBA Schedule — {date_str}")

    with st.spinner("Loading schedule…"):
        games = fetch_schedule(date_str)

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
        has_started = g["is_live_or_final"]

        btn_label = f"▶ Open {g['away_abbr']} @ {g['home_abbr']}" if has_started else "⏳ Not Started"
        btn_help  = "View play-by-play" if has_started else "Data will be available once the game starts."

        away_score_html = f'<span class="sched-score">{g["away_score"]}</span>' if has_started else ""
        home_score_html = f'<span class="sched-score">{g["home_score"]}</span>' if has_started else ""
        ot_badge        = ' <span class="sched-extra">OT</span>' if g["is_ot"] else ""

        if has_started:
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
                    btn_label,
                    key=f"go_{g['gameId']}",
                    use_container_width=True,
                    disabled=not has_started,
                    help=btn_help,
                ):
                    st.session_state.last_refresh         = datetime.now(ET)
                    st.session_state.cached_events        = None
                    st.session_state.cached_game_id       = None
                    st.session_state.filtered_events      = None
                    st.session_state.filters_applied      = False
                    st.session_state.applied_filter_state = {}
                    st.session_state.selected_game_id     = g["gameId"]
                    # ESPN scores stored as fallback for empty play feed
                    st.session_state.selected_event_id    = g["gameId"]
                    st.session_state.selected_away_score  = g["away_score"]
                    st.session_state.selected_home_score  = g["home_score"]
                    st.rerun()
