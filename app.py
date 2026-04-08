import streamlit as st
import json
import base64
import requests
import pandas as pd
from datetime import date, timedelta, datetime
import io
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="Kensite Prep Schedule", layout="wide", page_icon="🏗️")

# ── Brand constants ───────────────────────────────────────────────────────────
K_GREEN      = "#0d823b"
K_GREEN_DARK = "#0a6630"
K_GREEN_PALE = "#e8f5ee"
K_GREY       = "#40424a"
K_LGREY      = "#dadada"
K_WHITE      = "#ffffff"

_SVG_RAW = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 40"><rect width="120" height="40" rx="4" fill="#0d823b"/><text x="10" y="27" font-family="Figtree,Calibri,sans-serif" font-weight="800" font-size="18" fill="white" letter-spacing="1">KENSITE</text></svg>'
_SVG_B64 = base64.b64encode(_SVG_RAW.encode()).decode()
KENSITE_LOGO_HTML = f'<img src="data:image/svg+xml;base64,{_SVG_B64}" height="32" alt="Kensite"/>'

UNIT_TYPES = [
    "32ft AV", "24ft AV", "20ft AV", "10ft AV",
    "Mobile Welfare", "Static Welfare",
    "20ft Store", "10ft Store",
    "Stairs", "2+1", "3+1", "4+2",
    "Tank", "Steps", "IBC", "Generator",
    "Solar Loo Single", "Solar Loo Double", "Chemiloo",
    "Smoking Shelter",
]

# AV units that support configuration breakdown
AV_UNITS = {"32ft AV", "24ft AV", "20ft AV", "10ft AV"}
AV_CONFIGS = ["Canteen", "Office", "Drying Room", "Changing Room", "Welfare", "Meeting Room", "Other"]

JOB_TYPES = ["On Hire", "Off Hire", "Site Move"]
TEAM_MEMBERS = ["Jake", "Ewa", "Klaudia", "Chris", "Nick", "Chloe", "Peter", "Callum", "Nathan"]
TYPE_STYLE = {
    "On Hire":      (K_GREEN_PALE, K_GREEN_DARK, "●"),
    "Off Hire":     ("#fdecea",    "#7b1a1a",    "●"),
    "Site Move":    ("#eef2ff",    "#2d3a8c",    "●"),
    "Site Visit":   ("#f3e8ff",    "#5b21b6",    "●"),
}
K_PURPLE      = "#7c3aed"
K_PURPLE_PALE = "#f3e8ff"
K_PURPLE_DARK = "#5b21b6"

# ── Password protection ───────────────────────────────────────────────────────
def check_password():
    if st.session_state.get("authenticated"):
        return True
    st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Figtree:wght@400;600;800&display=swap');
    html,body,[class*="css"]{{font-family:'Figtree',Calibri,sans-serif;}}
    .login-outer{{display:flex;flex-direction:column;align-items:center;
                  justify-content:center;min-height:70vh;}}
    .login-card{{background:{K_WHITE};border:1.5px solid {K_LGREY};border-radius:14px;
                 padding:2.5rem 2rem;width:360px;text-align:center;}}
    .login-card h2{{color:{K_GREEN};font-size:22px;font-weight:800;margin-bottom:4px;}}
    .login-card p{{color:{K_GREY};font-size:13px;margin-bottom:1.5rem;}}
    </style>
    <div class="login-outer">
      <div class="login-card">
        <div style="margin-bottom:12px;">{KENSITE_LOGO_HTML}</div>
        <h2>Prep Schedule</h2>
        <p>Enter your password to continue</p>
      </div>
    </div>
    """, unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        pwd = st.text_input("Password", type="password",
                            placeholder="Password...", label_visibility="collapsed")
        if st.button("Log in", use_container_width=True, type="primary"):
            if pwd == st.secrets["APP_PASSWORD"]:
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("Incorrect password.")
    return False

if not check_password():
    st.stop()

# Auto-refresh every 30 seconds — paused when a file is being uploaded to avoid loop
_file_uploading = st.session_state.get("lh_uploader") is not None
if not _file_uploading:
    st_autorefresh(interval=30_000, limit=0, key="schedule_autorefresh")

# ── GitHub config ─────────────────────────────────────────────────────────────
GITHUB_TOKEN  = st.secrets["GITHUB_TOKEN"]
GITHUB_REPO   = st.secrets["GITHUB_REPO"]
GITHUB_BRANCH = st.secrets.get("GITHUB_BRANCH", "main")
DATA_FILE     = "data/jobs.json"
HEADERS = {"Authorization": f"token {GITHUB_TOKEN}",
           "Accept": "application/vnd.github.v3+json"}

def gh_get(path):
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    r = requests.get(url, headers=HEADERS, params={"ref": GITHUB_BRANCH})
    if r.status_code == 404:
        return None, None
    r.raise_for_status()
    d = r.json()
    return json.loads(base64.b64decode(d["content"]).decode()), d["sha"]

def gh_put(path, obj, sha=None, msg="Update schedule"):
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    payload = {"message": msg,
               "content": base64.b64encode(json.dumps(obj, indent=2).encode()).decode(),
               "branch": GITHUB_BRANCH}
    if sha:
        payload["sha"] = sha
    requests.put(url, headers=HEADERS, json=payload).raise_for_status()

@st.cache_data(ttl=30)
def load_data():
    data, sha = gh_get(DATA_FILE)
    if data is None:
        return {}, {}, {}, {}, {}, {}, None
    return (data.get("jobs", {}), data.get("mcs", {}),
            data.get("site_visits", {}), data.get("svr_confirmed", {}),
            data.get("checklist", {}), data.get("live_hire", {}), sha)

def save_data(jobs_dict, mcs_dict, sv_dict=None, svr_dict=None, cl_dict=None, lh_dict=None, _sha_hint=None):
    """Fetch latest SHA immediately before writing. Retries once on 409."""
    payload_obj = {
        "jobs":          jobs_dict,
        "mcs":           mcs_dict,
        "site_visits":   sv_dict  or {},
        "svr_confirmed": svr_dict or {},
        "checklist":     cl_dict  or {},
        "live_hire":     lh_dict  or {},
    }
    st.cache_data.clear()
    for attempt in range(3):
        _, fresh_sha = gh_get(DATA_FILE)
        try:
            gh_put(DATA_FILE, payload_obj, sha=fresh_sha)
            return
        except Exception as e:
            if attempt == 2:
                raise e
            import time; time.sleep(0.5)

def save_jobs(jobs_dict, _sha_hint=None):
    save_data(jobs_dict, mcs, site_visits, svr_confirmed, checklist, live_hire, _sha_hint)

# ── Date helpers ──────────────────────────────────────────────────────────────
def get_monday(d): return d - timedelta(days=d.weekday())
def fmt_key(d):    return d.strftime("%Y-%m-%d")
def week_num(d):   return d.isocalendar()[1]

# ── Bank holidays (England) ───────────────────────────────────────────────────
@st.cache_data(ttl=86400)
def get_bank_holidays():
    """Fetch England bank holidays from gov.uk API. Cache for 24 hours."""
    try:
        r = requests.get(
            "https://www.gov.uk/bank-holidays.json",
            timeout=5
        )
        r.raise_for_status()
        data = r.json()
        events = data.get("england-and-wales", {}).get("events", [])
        return {e["date"]: e["title"] for e in events}
    except Exception:
        # Fallback: hardcoded 2025-2026 England bank holidays
        return {
            "2025-01-01": "New Year's Day",
            "2025-04-18": "Good Friday",
            "2025-04-21": "Easter Monday",
            "2025-05-05": "Early May Bank Holiday",
            "2025-05-26": "Spring Bank Holiday",
            "2025-08-25": "Summer Bank Holiday",
            "2025-12-25": "Christmas Day",
            "2025-12-26": "Boxing Day",
            "2026-01-01": "New Year's Day",
            "2026-04-03": "Good Friday",
            "2026-04-06": "Easter Monday",
            "2026-05-04": "Early May Bank Holiday",
            "2026-05-25": "Spring Bank Holiday",
            "2026-08-31": "Summer Bank Holiday",
            "2026-12-25": "Christmas Day",
            "2026-12-28": "Boxing Day (substitute)",
        }

# ── Session state ─────────────────────────────────────────────────────────────
for k, v in [("week_offset", 0), ("n_weeks", 4),
             ("modal_date", None), ("modal_edit_idx", None),
             ("expand_date", None), ("expand_idx", None),
             ("day_view_date", None),
             ("move_from_date", None), ("move_job_idx", None),
             ("svr_modal_date", None), ("svr_modal_idx", None),
             ("msv_from_date", None), ("msv_idx", None),
             ("dialog_open", False)]:
    if k not in st.session_state:
        st.session_state[k] = v

jobs, mcs, site_visits, svr_confirmed, checklist, live_hire, sha = load_data()
bank_holidays = get_bank_holidays()

def open_dialog(**kwargs):
    """Set dialog state and mark dialog as open."""
    for k, v in kwargs.items():
        st.session_state[k] = v
    st.session_state.dialog_open = True

def close_dialog(**kwargs):
    """Clear dialog state and mark dialog as closed."""
    for k, v in kwargs.items():
        st.session_state[k] = v
    st.session_state.dialog_open = False

# ── Global CSS ────────────────────────────────────────────────────────────────
st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Figtree:wght@400;500;600;700;800&display=swap');
html,body,[class*="css"]{{font-family:'Figtree',Calibri,sans-serif;color:{K_GREY};}}
.main .block-container{{padding-top:0.75rem;padding-bottom:2rem;max-width:100%;}}

/* Header */
.ks-header{{display:flex;align-items:center;gap:12px;padding:10px 0 12px;
            border-bottom:2px solid {K_GREEN};margin-bottom:1rem;}}
.ks-title{{font-size:20px;font-weight:800;color:{K_GREEN};letter-spacing:-.3px;}}
.ks-sub{{font-size:12px;color:{K_GREY};opacity:.6;margin-left:auto;}}

/* Day cards */
.day-card{{border:1px solid {K_LGREY};border-radius:10px;overflow:hidden;
           min-height:130px;background:{K_WHITE};margin:2px;}}
.day-card.is-today{{border-color:{K_GREEN};border-width:2px;}}
.day-card.is-weekend{{background:#fafafa;}}
.day-head{{padding:7px 9px 5px;border-bottom:1px solid {K_LGREY};}}
.day-name{{font-size:10px;font-weight:700;color:{K_GREY};opacity:.5;
           text-transform:uppercase;letter-spacing:.07em;}}
.day-date{{font-size:17px;font-weight:800;color:{K_GREY};}}
.day-date.is-today{{color:{K_GREEN};}}
.day-body{{padding:5px;}}

/* Day summary pills inside card */
.day-sum-pill{{display:flex;align-items:center;gap:5px;padding:3px 5px;
               border-radius:5px;margin-bottom:2px;font-size:11px;font-weight:600;}}
.day-sum-dot{{width:8px;height:8px;border-radius:50%;flex-shrink:0;}}
.day-sum-label{{flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
.day-sum-haul{{font-size:9px;opacity:.65;margin-left:2px;}}
.day-empty{{font-size:10px;color:{K_GREY};opacity:.3;padding:4px 5px;font-style:italic;}}

/* Day click button — invisible, covers body */
.ks-day-btn button {{
  background: transparent !important;
  border: none !important;
  color: {K_GREEN} !important;
  font-size: 10px !important;
  font-weight: 600 !important;
  width: 100% !important;
  padding: 2px 4px !important;
  border-radius: 4px !important;
  opacity: 0.6;
}}
.ks-day-btn button:hover {{
  background: {K_GREEN_PALE} !important;
  opacity: 1;
}}

/* Job chips */
.jchip{{border-radius:6px;padding:5px 8px;margin-bottom:3px;
        font-size:11.5px;line-height:1.4;cursor:pointer;}}
.jchip:hover{{filter:brightness(.96);}}
.jchip-name{{font-weight:700;display:block;font-size:12px;}}
.jchip-sub{{font-size:10px;opacity:.75;display:block;}}
.jchip-units{{font-size:10px;opacity:.6;display:block;margin-top:1px;}}
.jchip-idtag{{display:inline-block;font-size:9.5px;font-weight:700;
              background:rgba(0,0,0,.08);border-radius:3px;padding:1px 5px;margin-top:2px;}}
.jchip-ts{{display:block;font-size:9px;opacity:.55;margin-top:2px;font-style:italic;}}

/* Add buttons — white background, green text/border */
.ks-add-btn button {{
  background-color: white !important;
  color: {K_GREEN} !important;
  border: 1.5px solid {K_GREEN} !important;
  font-weight: 700 !important;
  border-radius: 6px !important;
}}
.ks-add-btn button:hover {{
  background-color: {K_GREEN_PALE} !important;
}}

/* Chip button wrapper — hides the button, chip is the visual trigger */
.ks-chip-btn {{ margin-bottom: 4px; }}
.ks-chip-btn button {{
  background: transparent !important;
  border: none !important;
  color: {K_GREEN} !important;
  font-size: 10px !important;
  font-weight: 600 !important;
  padding: 1px 4px !important;
  margin-top: -2px !important;
  border-radius: 4px !important;
  height: auto !important;
  min-height: unset !important;
  opacity: 0.7;
}}
.ks-chip-btn button:hover {{
  background: {K_GREEN_PALE} !important;
  opacity: 1;
}}

/* Week bar */
.wk-bar{{background:{K_GREEN_PALE};border:1px solid #c3dfc9;border-radius:8px;
         padding:6px 10px;margin-bottom:6px;font-size:11px;color:{K_GREEN_DARK};}}
.wk-bar-title{{font-weight:700;font-size:11px;margin-bottom:3px;}}
.wk-unit-row{{display:flex;flex-wrap:wrap;gap:4px;}}
.wku{{background:{K_GREEN};color:white;border-radius:4px;padding:2px 7px;
      font-size:10.5px;font-weight:600;}}
.wku.off{{background:#c05500;}}

/* Pill summary */
.pill{{display:inline-block;border-radius:20px;padding:4px 12px;
       font-size:12px;font-weight:600;margin-right:5px;margin-bottom:5px;}}

/* Snapshot */
.snap-outer{{font-family:'Figtree',Calibri,sans-serif;}}
.snap-header{{background:{K_GREEN};color:white;padding:14px 20px;border-radius:10px 10px 0 0;}}
.snap-title{{font-size:18px;font-weight:800;letter-spacing:-.2px;}}
.snap-period{{font-size:12px;opacity:.8;margin-top:2px;}}
.snap-grid{{display:grid;grid-template-columns:repeat(7,1fr);
            border:1px solid {K_LGREY};border-top:none;}}
.snap-dh{{background:#f5f5f5;padding:6px 8px;border-right:1px solid {K_LGREY};
          border-bottom:1px solid {K_LGREY};}}
.snap-dname{{font-size:9px;font-weight:700;text-transform:uppercase;
             color:{K_GREY};opacity:.5;letter-spacing:.06em;}}
.snap-ddate{{font-size:14px;font-weight:800;color:{K_GREY};}}
.snap-ddate.snap-today{{color:{K_GREEN};}}
.snap-body{{padding:5px;border-right:1px solid {K_LGREY};
            border-bottom:1px solid {K_LGREY};min-height:80px;vertical-align:top;}}
.snap-chip{{border-radius:4px;padding:3px 6px;margin-bottom:2px;font-size:10px;line-height:1.3;}}
.snap-name{{font-weight:700;display:block;}}
.snap-sub{{font-size:9px;opacity:.7;}}
.snap-footer{{background:#f9f9f9;padding:8px 16px;border:1px solid {K_LGREY};
              border-top:none;border-radius:0 0 10px 10px;
              font-size:10px;color:{K_GREY};opacity:.6;text-align:right;}}

/* Day Complete animation */
@keyframes day-complete {{
  0%   {{ transform: scale(0.8); opacity: 0; }}
  50%  {{ transform: scale(1.08); opacity: 1; }}
  70%  {{ transform: scale(0.97); }}
  100% {{ transform: scale(1); opacity: 1; }}
}}
@keyframes confetti-spin {{
  0%   {{ transform: rotate(0deg) translateY(0);   opacity: 1; }}
  100% {{ transform: rotate(720deg) translateY(-20px); opacity: 0; }}
}}
.day-complete-banner {{
  animation: day-complete 0.6s cubic-bezier(.34,1.56,.64,1) forwards;
  background: linear-gradient(135deg, {K_GREEN} 0%, {K_GREEN_DARK} 100%);
  color: white; border-radius: 12px; padding: 16px 20px;
  text-align: center; margin: 1rem 0;
}}
.day-complete-title {{
  font-size: 20px; font-weight: 800; letter-spacing: -.3px; margin-bottom: 2px;
}}
.day-complete-sub {{
  font-size: 13px; opacity: .85;
}}
.day-card.is-bh {{ background: #fffbea !important; border-color: #e6c200 !important; }}
.bh-label {{ font-size: 9px; font-weight: 700; color: #7a6000;
             background: #fff3b0; border-radius: 3px; padding: 1px 5px;
             display: inline-block; margin-top: 2px; }}

/* Day card fully processed — gold glow */
@keyframes glow-pulse {{
  0%, 100% {{ box-shadow: 0 0 0 2px #f0b429, 0 0 10px 2px rgba(240,180,41,.25); }}
  50%       {{ box-shadow: 0 0 0 2px #f0b429, 0 0 18px 5px rgba(240,180,41,.4); }}
}}
.day-card.is-complete {{
  border-color: #f0b429 !important;
  border-width: 2px !important;
  animation: glow-pulse 2.5s ease-in-out infinite;
}}

/* MCS tick sparkle animation */
@keyframes mcs-sparkle {{
  0%   {{ transform: scale(1);   opacity: 1; }}
  20%  {{ transform: scale(1.35); opacity: 1; }}
  40%  {{ transform: scale(0.9);  opacity: 1; }}
  60%  {{ transform: scale(1.15); opacity: 1; }}
  100% {{ transform: scale(1);   opacity: 1; }}
}}
@keyframes mcs-stars {{
  0%   {{ opacity: 0; transform: scale(0) rotate(0deg); }}
  50%  {{ opacity: 1; transform: scale(1.4) rotate(180deg); }}
  100% {{ opacity: 0; transform: scale(0) rotate(360deg); }}
}}
.mcs-done {{
  animation: mcs-sparkle 0.5s ease;
  display: inline-flex; align-items: center; gap: 5px;
  background: {K_GREEN_PALE}; color: {K_GREEN_DARK};
  border-radius: 6px; padding: 4px 10px;
  font-size: 12px; font-weight: 700;
}}
.mcs-done-red {{
  animation: mcs-sparkle 0.5s ease;
  display: inline-flex; align-items: center; gap: 5px;
  background: #fdecea; color: #7b1a1a;
  border-radius: 6px; padding: 4px 10px;
  font-size: 12px; font-weight: 700;
}}
</style>
""", unsafe_allow_html=True)

# ── DAY VIEW DIALOG (all jobs for a day) ─────────────────────────────────────
@st.dialog("Day Schedule", width="large")
def day_view_dialog(date_key):
    day_label = datetime.strptime(date_key, "%Y-%m-%d").strftime("%A %-d %B %Y")
    bh = bank_holidays.get(date_key, "")
    header_extra = f"  ·  🏴󠁧󠁢󠁥󠁮󠁧󠁿 {bh}" if bh else ""
    st.markdown(
        f"<div style='font-size:14px;font-weight:700;color:{K_GREEN};"
        f"margin-bottom:1rem;'>📅 {day_label}{header_extra}</div>",
        unsafe_allow_html=True)

    day_jobs = jobs.get(date_key, [])

    if not day_jobs:
        st.info("No jobs booked for this day.")
    else:
        for ji, job in enumerate(day_jobs):
            bg, fg, _ = TYPE_STYLE[job["type"]]
            haulage    = job.get("haulage", "None")
            border_col = K_GREEN if haulage == "Internal Haulage" else ("#c0392b" if haulage == "External Haulage" else "transparent")

            units_html = ""
            if job.get("units"):
                unit_items = "".join(
                    f'<span style="display:inline-block;background:{bg};color:{fg};'
                    f'border-radius:4px;padding:2px 8px;font-size:11px;font-weight:600;'
                    f'margin:2px 2px 0 0;">{u} ×{q}</span>'
                    for u, q in job["units"].items() if q
                )
                units_html = f"<div style='margin-top:6px;'>{unit_items}</div>"

            # AV config breakdown
            av_cfg_html = ""
            av_cfgs = job.get("av_configs", {})
            if av_cfgs:
                cfg_lines = []
                for av_unit, cfgs in av_cfgs.items():
                    if cfgs:
                        parts = ", ".join(f"{c} ×{n}" for c, n in cfgs.items())
                        cfg_lines.append(
                            f'<div style="font-size:10.5px;opacity:.75;margin-top:3px;">'
                            f'<b>{av_unit}:</b> {parts}</div>'
                        )
                if cfg_lines:
                    av_cfg_html = (
                        f'<div style="margin-top:6px;padding-top:6px;'
                        f'border-top:1px solid rgba(0,0,0,.08);">'
                        + "".join(cfg_lines) + "</div>"
                    )

            tags = f'<span style="background:rgba(0,0,0,.09);border-radius:4px;padding:2px 8px;font-size:11px;font-weight:700;">{job["type"]}</span>'
            # Site Move sub-type
            if job.get("site_move_type"):
                sm_icon = "🔄" if job["site_move_type"] == "Movement on Same Site" else "🚚"
                tags += (f' <span style="background:#eef2ff;color:#2d3a8c;border-radius:4px;'
                         f'padding:2px 8px;font-size:11px;font-weight:700;">'
                         f'{sm_icon} {job["site_move_type"]}</span>')
            if job.get("install_dismantle"):
                tags += f' <span style="background:{K_GREEN};color:white;border-radius:4px;padding:2px 8px;font-size:11px;font-weight:700;">I/D</span>'
            if haulage != "None":
                haul_bg   = K_GREEN_PALE if haulage == "Internal Haulage" else "#fdecea"
                haul_fg   = K_GREEN_DARK if haulage == "Internal Haulage" else "#7b1a1a"
                haul_icon = "🚛" if haulage == "Internal Haulage" else "🚚"
                haul_who  = job.get("haulage_who", "")
                haul_label = f"{haul_icon} {haulage}" + (f" — {haul_who}" if haul_who else "")
                tags += (f' <span style="background:{haul_bg};color:{haul_fg};border-radius:4px;'
                         f'padding:2px 8px;font-size:11px;font-weight:700;">{haul_label}</span>')
            livery = job.get("livery", "Standard Livery")
            if livery == "Customer Livery — Specify":
                livery_note = job.get("livery_note", "")
                livery_label = f"🎨 {livery_note}" if livery_note else "🎨 Customer Livery"
                tags += (f' <span style="background:#f3e8ff;color:#5b21b6;border-radius:4px;'
                         f'padding:2px 8px;font-size:11px;font-weight:700;">{livery_label}</span>')
            else:
                tags += (f' <span style="background:#f0f0f0;color:{K_GREY};border-radius:4px;'
                         f'padding:2px 8px;font-size:11px;font-weight:700;">🏭 Standard Livery</span>')

            ts_line = ""
            if job.get("added_by") or job.get("timestamp"):
                ts_line = (f'<div style="font-size:10px;opacity:.5;margin-top:6px;">'
                           f'🕐 {job.get("added_by","")} · {job.get("timestamp","")}</div>')
            if job.get("edited_at"):
                ts_line += (f'<div style="font-size:10px;opacity:.5;">'
                            f'✏️ {job.get("edited_by","")} · {job["edited_at"]}</div>')

            # MCS key — unique per date + job index
            mcs_key      = f"{date_key}_{ji}"
            mcs_status   = mcs.get(mcs_key, "")
            job_type_val = job["type"]

            # Per-job fulfilment checks
            JOB_CHECK_LABELS = {
                "On Hire":  [("pod", "📦 POD Attached?"), ("contract", "📄 Contract Posted?")],
                "Off Hire": [("poc", "📎 POC Attached?"), ("returns",  "🔄 Lines Returned?")],
            }
            job_checks   = JOB_CHECK_LABELS.get(job_type_val, [])
            base_ck      = f"job_{date_key}_{ji}"
            checks_done  = bool(job_checks) and all(
                checklist.get(f"{base_ck}_{ck}", False) for ck, _ in job_checks
            )
            # On Hire: fully done = both checks + MCS picked
            # Off Hire: fully done = both checks (replaces MCS)
            if job_type_val == "On Hire":
                all_job_done = checks_done and (mcs.get(f"{date_key}_{ji}", "") == "picked")
            else:
                all_job_done = checks_done
            # Shiny gold border when all checks done
            card_border = (
                "border:2px solid #f0b429;box-shadow:0 0 10px rgba(240,180,41,.35);"
                if all_job_done else f"border-left:5px solid {border_col};"
            )
            done_badge = (
                ' <span style="font-size:10px;font-weight:700;background:#f0b429;'
                'color:#7a5c00;border-radius:3px;padding:1px 6px;margin-left:4px;">✨ Done</span>'
                if all_job_done else ""
            )

            rc1, rc2, rc3 = st.columns([5, 1, 1])
            with rc1:
                # MCS status badge (On Hire only — shown in card)
                mcs_badge = ""
                if mcs_status == "picked" and job_type_val == "On Hire":
                    mcs_badge = (f'<div class="mcs-done" style="margin-top:8px;">'
                                 f'✅ Picked on MCS</div>')

                contract_num = job.get("contract_number", "")
                contract_html = ""
                if contract_num and contract_num != "00000":
                    contract_html = (
                        f'<span style="font-size:14px;font-weight:500;opacity:.6;'
                        f'margin-left:8px;background:rgba(0,0,0,.07);border-radius:4px;'
                        f'padding:1px 7px;">{contract_num}</span>'
                    )
                st.markdown(f"""
                <div style="background:{bg};color:{fg};border-radius:10px;
                            {card_border}padding:12px 14px;margin-bottom:4px;">
                  <div style="font-size:17px;font-weight:800;margin-bottom:2px;">
                    {job.get("customer","")}{contract_html}{done_badge}</div>
                  <div style="font-size:12px;opacity:.65;margin-bottom:6px;">{job.get("postcode","")}</div>
                  <div>{tags}</div>
                  {units_html}
                  {av_cfg_html}
                  {ts_line}
                  {mcs_badge}
                </div>
                """, unsafe_allow_html=True)

                # ── Per-job checks ──────────────────────────────────────────
                if job_checks:
                    st.markdown(
                        "<div style='margin-top:2px;margin-bottom:4px;'></div>",
                        unsafe_allow_html=True)
                    jc_cols = st.columns(len(job_checks))
                    job_ck_changed = False
                    for ci_jc, (ck, label) in enumerate(job_checks):
                        with jc_cols[ci_jc]:
                            key    = f"{base_ck}_{ck}"
                            cur    = checklist.get(key, False)
                            newval = st.checkbox(label, value=cur, key=f"jchk_{key}")
                            if newval != cur:
                                checklist[key] = newval
                                job_ck_changed = True
                    if job_ck_changed:
                        save_data(jobs, mcs, site_visits, svr_confirmed, checklist, live_hire)
                        st.rerun()

                # ── MCS button — On Hire only, below the checks ─────────────
                if job_type_val == "On Hire":
                    if mcs_status != "picked":
                        if st.button("☐  Picked on MCS", key=f"mcs_{mcs_key}",
                                     use_container_width=True):
                            mcs[mcs_key] = "picked"
                            save_data(jobs, mcs, site_visits, svr_confirmed, checklist, live_hire)
                            st.rerun()
                    else:
                        if st.button("✅ Picked on MCS — undo", key=f"mcs_{mcs_key}",
                                     use_container_width=True):
                            mcs.pop(mcs_key, None)
                            save_data(jobs, mcs, site_visits, svr_confirmed, checklist, live_hire)
                            st.rerun()
                # Off Hire — no MCS button, POC/Returns IS the confirmation
            with rc2:
                if st.button("✏️", key=f"dv_edit_{date_key}_{ji}",
                             use_container_width=True, help="Edit this job"):
                    st.session_state["modal_date"]     = date_key
                    st.session_state["modal_edit_idx"] = ji
                    st.session_state["day_view_date"]  = None
                    st.rerun()
            with rc3:
                if st.button("📅", key=f"dv_move_{date_key}_{ji}",
                             use_container_width=True, help="Move to another day"):
                    st.session_state["move_from_date"] = date_key
                    st.session_state["move_job_idx"]   = ji
                    st.session_state["day_view_date"]  = None
                    st.rerun()

    st.markdown("<hr style='margin:1rem 0;'>", unsafe_allow_html=True)

    # ── Daily fulfilment checklist ────────────────────────────────────────────
    d_key   = f"daily_{date_key}"
    ds      = checklist.get(d_key, {})

    # Auto-detect if live hire was uploaded today
    today_str_dt = datetime.now().strftime("%Y-%m-%d")
    lh_today_auto = (live_hire.get("latest", {}).get("date", "") == today_str_dt) if live_hire else False

    DAILY_ITEMS = [
        ("partial_contracts", "📋 Partially Live Contracts Posted?"),
        ("oneoff_contracts",  "📄 One Off / Sale Contracts Posted?"),
    ]
    mcs_check_count = int(ds.get("mcs_check", 0))
    live_ok = lh_today_auto or ds.get("live_hire_uploaded", False)

    all_daily_done = (
        all(ds.get(k, False) for k, _ in DAILY_ITEMS)
        and live_ok
        and mcs_check_count >= 1
    )

    st.markdown(
        f"<div style='font-size:13px;font-weight:700;color:{K_GREY};"
        f"margin-bottom:.6rem;'>📋 Daily Fulfilment Checklist</div>",
        unsafe_allow_html=True)

    if all_daily_done:
        st.markdown("""
        <div class="day-complete-banner">
          <div class="day-complete-title">🎉 Dailys Complete!</div>
          <div class="day-complete-sub">All daily fulfilment tasks done for this day.</div>
        </div>
        """, unsafe_allow_html=True)

    daily_changed = False
    dc_cols = st.columns(len(DAILY_ITEMS))
    for ci, (ck, label) in enumerate(DAILY_ITEMS):
        with dc_cols[ci]:
            cur    = ds.get(ck, False)
            newval = st.checkbox(label, value=cur, key=f"dcl_{date_key}_{ck}")
            if newval != cur:
                ds[ck] = newval
                daily_changed = True

    # Live hire uploaded row — auto or manual
    lh_c1, lh_c2 = st.columns([5, 1])
    with lh_c1:
        if lh_today_auto:
            st.markdown(
                f"<div style='background:{K_GREEN_PALE};color:{K_GREEN_DARK};"
                f"border-radius:6px;padding:5px 10px;font-size:12px;font-weight:600;'>"
                f"☁️ New Live Hire Report Uploaded? &nbsp; ✅ Auto-detected — uploaded today</div>",
                unsafe_allow_html=True)
        else:
            cur_lh = ds.get("live_hire_uploaded", False)
            new_lh = st.checkbox("☁️ New Live Hire Report Uploaded?",
                                  value=cur_lh, key=f"dcl_{date_key}_lh")
            if new_lh != cur_lh:
                ds["live_hire_uploaded"] = new_lh
                daily_changed = True

    # MCS match counter
    st.markdown("<div style='margin-top:.5rem'></div>", unsafe_allow_html=True)
    mcs_c1, mcs_c2 = st.columns([5, 1])
    with mcs_c1:
        count_colour = K_GREEN_DARK if mcs_check_count >= 2 else ("#b45309" if mcs_check_count == 1 else "#9ca3af")
        count_bg     = K_GREEN_PALE if mcs_check_count >= 2 else ("#fef3c7" if mcs_check_count == 1 else "#f3f4f6")
        count_label  = f"✅ Checked {mcs_check_count}×" if mcs_check_count > 0 else "☐  Not yet checked"
        st.markdown(
            f"<div style='display:flex;align-items:center;gap:10px;padding:6px 10px;"
            f"background:{count_bg};border-radius:8px;'>"
            f"<span style='font-size:13px;font-weight:600;color:{K_GREY};flex:1;'>"
            f"🔍 Prep Schedule Matches MCS?</span>"
            f"<span style='font-size:12px;font-weight:700;color:{count_colour};"
            f"background:white;border-radius:5px;padding:2px 10px;"
            f"border:1px solid {count_colour};white-space:nowrap;'>{count_label}</span>"
            f"</div>", unsafe_allow_html=True)
    with mcs_c2:
        if st.button("＋ Check", key=f"mcs_check_{date_key}", use_container_width=True):
            ds["mcs_check"] = mcs_check_count + 1
            daily_changed = True

    if daily_changed:
        checklist[d_key] = ds
        save_data(jobs, mcs, site_visits, svr_confirmed, checklist, live_hire)
        st.rerun()

    st.markdown("<hr style='margin:1rem 0;'>", unsafe_allow_html=True)

    # ── Site Visit Requests for this day ─────────────────────────────────────
    sv_list = site_visits.get(date_key, [])
    if sv_list:
        st.markdown(
            f"<div style='font-size:13px;font-weight:700;color:{K_PURPLE_DARK};"
            f"margin-bottom:.5rem;'>🔍 Site Visit Requests</div>",
            unsafe_allow_html=True)
        for svi, sv in enumerate(sv_list):
            svr_key       = f"{date_key}_{svi}"
            is_confirmed  = svr_confirmed.get(svr_key, False)
            conf_badge    = ""
            if is_confirmed:
                conf_badge = (f'<div style="margin-top:8px;display:inline-flex;'
                              f'align-items:center;gap:6px;background:#f3e8ff;'
                              f'color:{K_PURPLE_DARK};border-radius:6px;'
                              f'padding:4px 10px;font-size:11px;font-weight:700;">'
                              f'✅ Nathan Checked and Confirmed in Diary</div>')

            time_str = f" — {sv['time_on_site']}" if sv.get("time_on_site") else ""
            st.markdown(f"""
            <div style="background:{K_PURPLE_PALE};color:{K_PURPLE_DARK};
                        border-radius:10px;border-left:4px solid {K_PURPLE};
                        padding:12px 14px;margin-bottom:6px;">
              <div style="font-size:16px;font-weight:800;margin-bottom:2px;">
                {sv.get("customer","")}{time_str}</div>
              <div style="font-size:11px;opacity:.7;margin-bottom:4px;">
                {sv.get("site_contact","")}{"  ·  " if sv.get("site_contact") else ""}
                {sv.get("site_address","")}</div>
              <div style="font-size:12px;margin-bottom:4px;">{sv.get("description","")}</div>
              <div style="font-size:10px;opacity:.5;">
                🕐 Requested by {sv.get("requested_by","")} · {sv.get("timestamp","")}</div>
              {conf_badge}
            </div>
            """, unsafe_allow_html=True)

            sc1, sc2, sc3, sc4 = st.columns([3, 2, 1, 1])
            with sc1:
                if not is_confirmed:
                    if st.button("✅ Nathan Checked and Confirmed in Diary",
                                 key=f"svr_confirm_{svr_key}", use_container_width=True):
                        svr_confirmed[svr_key] = True
                        save_data(jobs, mcs, site_visits, svr_confirmed, checklist, live_hire)
                        st.rerun()
                else:
                    if st.button("↩ Unconfirm", key=f"svr_unconfirm_{svr_key}",
                                 use_container_width=True):
                        svr_confirmed.pop(svr_key, None)
                        save_data(jobs, mcs, site_visits, svr_confirmed, checklist, live_hire)
                        st.rerun()
            with sc2:
                if st.button("✏️ Edit request", key=f"svr_edit_{svr_key}",
                             use_container_width=True):
                    st.session_state["svr_modal_date"] = date_key
                    st.session_state["svr_modal_idx"]  = svi
                    st.session_state["day_view_date"]  = None
                    st.rerun()
            with sc3:
                if st.button("📅", key=f"svr_move_{svr_key}",
                             use_container_width=True, help="Move to another day"):
                    st.session_state["msv_from_date"]  = date_key
                    st.session_state["msv_idx"]        = svi
                    st.session_state["day_view_date"]  = None
                    st.rerun()

        st.markdown("<div style='margin-top:.5rem'></div>", unsafe_allow_html=True)

    st.markdown("<hr style='margin:.75rem 0;'>", unsafe_allow_html=True)
    ac1, ac2, ac3 = st.columns(3)
    with ac1:
        if st.button("＋ Add job to this day", use_container_width=True, type="primary"):
            st.session_state["modal_date"]     = date_key
            st.session_state["modal_edit_idx"] = None
            st.session_state.dialog_open = False
            st.session_state["day_view_date"]  = None
            st.rerun()
    with ac2:
        if st.button("🔍 Request Site Visit", use_container_width=True):
            st.session_state["svr_modal_date"] = date_key
            st.session_state["svr_modal_idx"]  = None
            st.session_state["day_view_date"]  = None
            st.rerun()
    with ac3:
        if st.button("Close", use_container_width=True):
            close_dialog(day_view_date=None)
            st.rerun()

# ── SITE VISIT REQUEST DIALOG (add/edit) ─────────────────────────────────────
@st.dialog("Site Visit Request", width="large")
def site_visit_dialog(date_key, edit_svr_idx=None):
    edit_sv = None
    if edit_svr_idx is not None:
        sv_list = site_visits.get(date_key, [])
        if edit_svr_idx < len(sv_list):
            edit_sv = sv_list[edit_svr_idx]

    day_label = datetime.strptime(date_key, "%Y-%m-%d").strftime("%A %-d %B %Y")
    st.markdown(
        f"<div style='font-size:13px;color:{K_PURPLE_DARK};font-weight:700;"
        f"background:{K_PURPLE_PALE};border-radius:6px;padding:6px 12px;"
        f"margin-bottom:1rem;'>🔍 Site Visit Request — 📅 {day_label}</div>",
        unsafe_allow_html=True)

    if edit_sv and edit_sv.get("requested_by"):
        st.markdown(
            f"<div style='font-size:11px;color:{K_GREY};opacity:.55;"
            f"background:#f5f5f5;border-radius:5px;padding:4px 8px;"
            f"margin-bottom:.75rem;display:inline-block;'>"
            f"🕐 Requested by <b>{edit_sv['requested_by']}</b>"
            f"{' at ' + edit_sv.get('timestamp','') if edit_sv.get('timestamp') else ''}</div>",
            unsafe_allow_html=True)

    sv1, sv2 = st.columns(2)
    with sv1:
        customer = st.text_input("Customer *",
                                 value=edit_sv.get("customer", "") if edit_sv else "")
    with sv2:
        site_contact = st.text_input("Site Contact",
                                     value=edit_sv.get("site_contact", "") if edit_sv else "")

    site_address = st.text_input("Site Address *",
                                 value=edit_sv.get("site_address", "") if edit_sv else "")

    ta1, ta2 = st.columns([3, 1])
    with ta1:
        description = st.text_area("Description / Purpose of Visit",
                                   value=edit_sv.get("description", "") if edit_sv else "",
                                   height=100)
    with ta2:
        time_on_site = st.text_input("Time on Site",
                                     value=edit_sv.get("time_on_site", "") if edit_sv else "",
                                     placeholder="e.g. 10:30")

    name_opts = ["— Select your name *"] + TEAM_MEMBERS
    def_name  = edit_sv.get("requested_by", "—") if edit_sv else "—"
    name_idx  = name_opts.index(def_name) if def_name in name_opts else 0
    requested_by = st.selectbox("Requested by *", name_opts, index=name_idx)

    st.markdown("<div style='margin-top:1rem'></div>", unsafe_allow_html=True)
    sb1, sb2, sb3 = st.columns([2, 2, 2])
    with sb1:
        if st.button("✅ Save Request", type="primary", use_container_width=True):
            errors = []
            if not customer.strip():
                errors.append("Please enter a customer name.")
            if not site_address.strip():
                errors.append("Please enter a site address.")
            if requested_by == "— Select your name *":
                errors.append("Please select who is making this request.")
            if errors:
                for e in errors:
                    st.warning(e)
            else:
                new_sv = {
                    "customer":     customer.strip(),
                    "site_contact": site_contact.strip(),
                    "site_address": site_address.strip(),
                    "description":  description.strip(),
                    "time_on_site": time_on_site.strip(),
                    "requested_by": requested_by,
                    "timestamp":    edit_sv.get("timestamp", datetime.now().strftime("%d/%m/%Y %H:%M")) if edit_sv else datetime.now().strftime("%d/%m/%Y %H:%M"),
                }
                if date_key not in site_visits:
                    site_visits[date_key] = []
                if edit_svr_idx is not None:
                    site_visits[date_key][edit_svr_idx] = new_sv
                else:
                    site_visits[date_key].append(new_sv)
                save_data(jobs, mcs, site_visits, svr_confirmed, checklist, live_hire)
                st.session_state["day_view_date"]    = None
                st.session_state["svr_modal_date"]   = None
                st.session_state["svr_modal_idx"]    = None
                st.rerun()
    with sb2:
        if st.button("Cancel", use_container_width=True):
            st.session_state["svr_modal_date"] = None
            st.session_state.dialog_open = False
            st.session_state["svr_modal_idx"]  = None
            st.rerun()
    with sb3:
        if edit_sv is not None:
            if st.button("🗑 Delete", use_container_width=True):
                site_visits[date_key].pop(edit_svr_idx)
                if not site_visits[date_key]:
                    del site_visits[date_key]
                save_data(jobs, mcs, site_visits, svr_confirmed, checklist, live_hire)
                st.session_state["svr_modal_date"] = None
                st.session_state.dialog_open = False
                st.session_state["svr_modal_idx"]  = None
                st.rerun()

# ── MOVE SITE VISIT DIALOG ────────────────────────────────────────────────────
@st.dialog("Move Site Visit to Another Day", width="small")
def move_site_visit_dialog(from_date, sv_idx):
    sv_list = site_visits.get(from_date, [])
    if sv_idx >= len(sv_list):
        st.warning("Site visit not found."); return

    sv       = sv_list[sv_idx]
    from_dt  = datetime.strptime(from_date, "%Y-%m-%d").date()

    st.markdown(
        f"<div style='background:{K_PURPLE_PALE};color:{K_PURPLE_DARK};border-radius:8px;"
        f"padding:10px 14px;margin-bottom:1rem;font-weight:700;font-size:14px;"
        f"border-left:4px solid {K_PURPLE};'>"
        f"🔍 {sv.get('customer','')} &nbsp;·&nbsp; "
        f"<span style='font-weight:400;font-size:12px;'>"
        f"{from_dt.strftime('%A %-d %B %Y')}</span></div>",
        unsafe_allow_html=True)

    st.markdown("**Move to:**")
    to_date = st.date_input("New date", value=from_dt, key="msv_to_date",
                            label_visibility="collapsed")

    if to_date == from_dt:
        st.info("Pick a different date to move this visit.")

    mc1, mc2 = st.columns(2)
    with mc1:
        if st.button("✅ Confirm Move", type="primary", use_container_width=True,
                     disabled=(to_date == from_dt)):
            to_key = fmt_key(to_date)
            # Move the visit
            sv_to_move = site_visits[from_date].pop(sv_idx)
            if not site_visits[from_date]:
                del site_visits[from_date]
            site_visits.setdefault(to_key, []).append(sv_to_move)
            # Move any confirmation status
            old_svr_key = f"{from_date}_{sv_idx}"
            new_svr_key = f"{to_key}_{len(site_visits[to_key]) - 1}"
            if old_svr_key in svr_confirmed:
                svr_confirmed[new_svr_key] = svr_confirmed.pop(old_svr_key)
            save_data(jobs, mcs, site_visits, svr_confirmed, checklist, live_hire)
            st.session_state["msv_from_date"] = None
            st.session_state.dialog_open = False
            st.session_state["msv_idx"]       = None
            st.session_state["day_view_date"] = None
            st.session_state.dialog_open = False
            st.success(f"Moved to {to_date.strftime('%a %-d %b')}.")
            st.rerun()
    with mc2:
        if st.button("Cancel", use_container_width=True):
            st.session_state["msv_from_date"] = None
            st.session_state.dialog_open = False
            st.session_state["msv_idx"]       = None
            st.rerun()

# ── MOVE JOB DIALOG ──────────────────────────────────────────────────────────
@st.dialog("Move Job to Another Day", width="small")
def move_job_dialog(from_date, job_idx):
    if from_date not in jobs or job_idx >= len(jobs[from_date]):
        st.warning("Job not found."); return

    job       = jobs[from_date][job_idx]
    from_dt   = datetime.strptime(from_date, "%Y-%m-%d").date()
    from_label = from_dt.strftime("%A %-d %B %Y")
    bg, fg, _ = TYPE_STYLE[job["type"]]

    st.markdown(
        f"<div style='background:{bg};color:{fg};border-radius:8px;"
        f"padding:10px 14px;margin-bottom:1rem;font-weight:700;font-size:14px;'>"
        f"{job.get('customer','')} &nbsp;·&nbsp; "
        f"<span style='font-weight:400;font-size:12px;'>{from_label}</span></div>",
        unsafe_allow_html=True)

    st.markdown("**Move to:**")
    to_date = st.date_input("New date", value=from_dt, key="move_to_date",
                            label_visibility="collapsed")

    if to_date == from_dt:
        st.info("Pick a different date to move this job.")

    mc1, mc2 = st.columns(2)
    with mc1:
        if st.button("✅ Confirm Move", type="primary", use_container_width=True,
                     disabled=(to_date == from_dt)):
            to_key = fmt_key(to_date)
            # Remove from source
            job_to_move = jobs[from_date].pop(job_idx)
            if not jobs[from_date]:
                del jobs[from_date]
            # Stamp the move
            job_to_move["moved_by"]   = "—"   # no user context here
            job_to_move["moved_from"] = from_date
            job_to_move["edited_at"]  = datetime.now().strftime("%d/%m/%Y %H:%M")
            # Add to destination
            jobs.setdefault(to_key, []).append(job_to_move)
            save_jobs(jobs)
            st.session_state["day_view_date"]  = None
            st.session_state["move_from_date"] = None
            st.session_state.dialog_open = False
            st.session_state["move_job_idx"]   = None
            st.success(f"Moved to {to_date.strftime('%a %-d %b')}.")
            st.rerun()
    with mc2:
        if st.button("Cancel", use_container_width=True):
            st.session_state["move_from_date"] = None
            st.session_state.dialog_open = False
            st.session_state["move_job_idx"]   = None
            st.rerun()

# ── EXPAND CHIP DIALOG (view details + open edit) ────────────────────────────
@st.dialog("Job Details", width="small")
def expand_chip_dialog(date_key, job_idx):
    if date_key not in jobs or job_idx >= len(jobs[date_key]):
        st.warning("Job not found."); return
    job = jobs[date_key][job_idx]
    bg, fg, _ = TYPE_STYLE[job["type"]]

    haulage = job.get("haulage", "None")
    border_col = K_GREEN if haulage == "Internal Haulage" else ("#c0392b" if haulage == "External Haulage" else K_LGREY)

    day_label = datetime.strptime(date_key, "%Y-%m-%d").strftime("%A %-d %B %Y")
    st.markdown(f"<div style='font-size:12px;color:{K_GREY};opacity:.5;margin-bottom:.5rem;'>📅 {day_label}</div>", unsafe_allow_html=True)

    # Big detail card
    units_html = ""
    if job.get("units"):
        unit_items = "".join(
            f'<span style="display:inline-block;background:{bg};color:{fg};'
            f'border-radius:4px;padding:2px 8px;font-size:11px;font-weight:600;'
            f'margin:2px;">{u} ×{q}</span>'
            for u, q in job["units"].items() if q
        )
        units_html = f"<div style='margin-top:8px;'>{unit_items}</div>"

    tags = f'<span style="background:rgba(0,0,0,.08);border-radius:4px;padding:2px 8px;font-size:11px;font-weight:700;">{job["type"]}</span>'
    if job.get("install_dismantle"):
        tags += f' <span style="background:{K_GREEN};color:white;border-radius:4px;padding:2px 8px;font-size:11px;font-weight:700;">I/D</span>'
    if haulage != "None":
        haul_bg = K_GREEN_PALE if haulage == "Internal Haulage" else "#fdecea"
        haul_fg = K_GREEN_DARK if haulage == "Internal Haulage" else "#7b1a1a"
        haul_icon = "🚛" if haulage == "Internal Haulage" else "🚚"
        tags += f' <span style="background:{haul_bg};color:{haul_fg};border-radius:4px;padding:2px 8px;font-size:11px;font-weight:700;">{haul_icon} {haulage}</span>'

    st.markdown(f"""
    <div style="background:{bg};color:{fg};border-radius:10px;
                border-left:5px solid {border_col};padding:14px 16px;">
      <div style="font-size:20px;font-weight:800;margin-bottom:4px;">{job.get("customer","")}</div>
      <div style="font-size:13px;opacity:.7;margin-bottom:10px;">{job.get("postcode","")}</div>
      <div style="margin-bottom:8px;">{tags}</div>
      {units_html}
    </div>
    """, unsafe_allow_html=True)

    if job.get("added_by") or job.get("timestamp"):
        who = job.get("added_by","")
        ts  = job.get("timestamp","")
        st.markdown(f"<div style='font-size:11px;color:{K_GREY};opacity:.5;margin-top:8px;'>🕐 Added by <b>{who}</b> · {ts}</div>", unsafe_allow_html=True)
    if job.get("edited_at"):
        st.markdown(f"<div style='font-size:11px;color:{K_GREY};opacity:.5;'>✏️ Edited by <b>{job.get('edited_by','')}</b> · {job['edited_at']}</div>", unsafe_allow_html=True)

    st.markdown("<div style='margin-top:1rem'></div>", unsafe_allow_html=True)
    ec1, ec2 = st.columns(2)
    with ec1:
        if st.button("✏️ Edit this job", use_container_width=True, type="primary"):
            st.session_state["modal_date"]     = date_key
            st.session_state["modal_edit_idx"] = job_idx
            st.session_state["expand_date"]    = None
            st.session_state["expand_idx"]     = None
            st.rerun()
    with ec2:
        if st.button("Close", use_container_width=True):
            st.session_state["expand_date"] = None
            st.session_state.dialog_open = False
            st.session_state["expand_idx"]  = None
            st.rerun()

# ── MODAL DIALOG ──────────────────────────────────────────────────────────────
@st.dialog("Add / Edit Job", width="large")
def job_modal(date_key, edit_idx=None):
    edit_job = None
    if edit_idx is not None and date_key in jobs and edit_idx < len(jobs[date_key]):
        edit_job = jobs[date_key][edit_idx]

    day_label = datetime.strptime(date_key, "%Y-%m-%d").strftime("%A %-d %B %Y")
    st.markdown(f"<div style='font-size:13px;color:{K_GREY};opacity:.6;"
                f"margin-bottom:1rem;'>📅 {day_label}</div>", unsafe_allow_html=True)

    # Show existing timestamp if editing
    if edit_job and edit_job.get("added_by"):
        ts  = edit_job.get("timestamp", "")
        who = edit_job.get("added_by", "")
        ts_str = f" at {ts}" if ts else ""
        st.markdown(
            f"<div style='font-size:11px;color:{K_GREY};opacity:.55;"
            f"background:#f5f5f5;border-radius:5px;padding:4px 8px;"
            f"margin-bottom:.75rem;display:inline-block;'>"
            f"🕐 Added by <b>{who}</b>{ts_str}</div>",
            unsafe_allow_html=True)

    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        customer = st.text_input("Customer *",
                                 value=edit_job.get("customer", "") if edit_job else "")
    with fc2:
        postcode = st.text_input("Postcode",
                                 value=edit_job.get("postcode", "") if edit_job else "")
    with fc3:
        def_type = edit_job.get("type", "On Hire") if edit_job else "On Hire"
        job_type = st.selectbox("Type *", JOB_TYPES, index=JOB_TYPES.index(def_type))

    contract_number = st.text_input(
        "Contract Number",
        value=edit_job.get("contract_number", "00000") if edit_job else "00000",
        placeholder="00000"
    )

    # Site Move sub-type
    site_move_type = None
    if job_type == "Site Move":
        sm_opts = ["Movement on Same Site", "Movement to New Site"]
        def_sm  = edit_job.get("site_move_type", sm_opts[0]) if edit_job else sm_opts[0]
        if def_sm not in sm_opts:
            def_sm = sm_opts[0]
        site_move_type = st.radio(
            "Movement type",
            sm_opts,
            index=sm_opts.index(def_sm),
            horizontal=True,
        )

    # Mandatory Added By — always shown, pre-selected if editing
    name_opts = ["— Select your name *"] + TEAM_MEMBERS
    if edit_job and edit_job.get("added_by") in TEAM_MEMBERS:
        name_default = name_opts.index(edit_job["added_by"])
    else:
        name_default = 0
    added_by = st.selectbox("Added by *", name_opts, index=name_default)

    st.markdown(f"<div style='font-size:13px;font-weight:700;color:{K_GREY};"
                f"margin:1rem 0 .5rem;'>Units</div>", unsafe_allow_html=True)

    unit_vals = {}
    av_configs = {}   # { "32ft AV": {"Office": 2, "Canteen": 1}, ... }

    u_cols = st.columns(4)
    for i, u in enumerate(UNIT_TYPES):
        with u_cols[i % 4]:
            def_qty = int(edit_job.get("units", {}).get(u, 0)) if edit_job else 0
            unit_vals[u] = st.number_input(u, min_value=0, max_value=99,
                                           value=def_qty, step=1, key=f"mu_{u}")

    # AV configuration breakdown — shown for any AV unit with qty > 0
    av_units_with_qty = [u for u in AV_UNITS if unit_vals.get(u, 0) > 0]
    if av_units_with_qty:
        st.markdown(
            f"<div style='font-size:12px;font-weight:700;color:{K_GREEN};"
            f"background:{K_GREEN_PALE};border-radius:6px;padding:6px 10px;"
            f"margin:.75rem 0 .5rem;'>AV Unit Configuration</div>",
            unsafe_allow_html=True)

        for u in av_units_with_qty:
            qty = unit_vals[u]
            st.markdown(
                f"<div style='font-size:12px;font-weight:600;color:{K_GREY};"
                f"margin:.5rem 0 .25rem;'>{u} — {qty} unit{'s' if qty > 1 else ''}"
                f" <span style='font-weight:400;opacity:.6;'>(assign configurations below)</span></div>",
                unsafe_allow_html=True)

            saved_cfg = (edit_job.get("av_configs", {}).get(u, {}) if edit_job else {})
            cfg_vals  = {}
            cfg_cols  = st.columns(4)
            for j, cfg in enumerate(AV_CONFIGS):
                with cfg_cols[j % 4]:
                    def_cfg = int(saved_cfg.get(cfg, 0))
                    cfg_vals[cfg] = st.number_input(
                        cfg, min_value=0, max_value=int(qty),
                        value=def_cfg, step=1, key=f"cfg_{u}_{cfg}")

            # Validation hint
            cfg_total = sum(cfg_vals.values())
            if cfg_total > 0:
                if cfg_total == qty:
                    st.markdown(
                        f"<div style='font-size:10px;color:{K_GREEN};margin-top:2px;'>"
                        f"✓ {cfg_total}/{qty} assigned</div>", unsafe_allow_html=True)
                else:
                    st.markdown(
                        f"<div style='font-size:10px;color:#c0392b;margin-top:2px;'>"
                        f"⚠ {cfg_total}/{qty} assigned — totals don't match</div>",
                        unsafe_allow_html=True)

            av_configs[u] = {cfg: v for cfg, v in cfg_vals.items() if v > 0}

    def_id = edit_job.get("install_dismantle", False) if edit_job else False
    install_dismantle = st.checkbox("Install / Dismantle", value=def_id)

    haulage_opts = ["None", "Internal Haulage", "External Haulage"]
    def_haulage  = edit_job.get("haulage", "None") if edit_job else "None"
    if def_haulage not in haulage_opts:
        def_haulage = "None"
    haulage = st.radio("Haulage", haulage_opts,
                       index=haulage_opts.index(def_haulage),
                       horizontal=True)
    haulage_who = ""
    if haulage == "External Haulage":
        haulage_who = st.text_input(
            "Who is the haulage contractor? *",
            value=edit_job.get("haulage_who", "") if edit_job else "",
            placeholder="e.g. Stobbarts, Eddie Stobart, XYZ Haulage..."
        )

    st.markdown(f"<div style='font-size:13px;font-weight:700;color:{K_GREY};"
                f"margin:1rem 0 .5rem;'>Cabin Livery</div>", unsafe_allow_html=True)
    livery_opts = ["Standard Livery", "Customer Livery — Specify"]
    def_livery  = edit_job.get("livery", "Standard Livery") if edit_job else "Standard Livery"
    if def_livery not in livery_opts:
        def_livery = "Standard Livery"
    livery = st.radio("Cabin livery", livery_opts,
                      index=livery_opts.index(def_livery),
                      horizontal=True,
                      label_visibility="collapsed")
    livery_note = ""
    if livery == "Customer Livery — Specify":
        livery_note = st.text_input(
            "Paint colour or RAL code",
            value=edit_job.get("livery_note", "") if edit_job else "",
            placeholder="e.g. RAL 5010, British Racing Green, #1A2B3C…"
        )

    st.markdown("<div style='margin-top:1rem'></div>", unsafe_allow_html=True)
    ba1, ba2, ba3 = st.columns([2, 2, 2])

    with ba1:
        if st.button("✅ Save Job", type="primary", use_container_width=True):
            errors = []
            if not customer.strip():
                errors.append("Please enter a customer name.")
            if added_by == "— Select your name *":
                errors.append("Please select who is adding this entry.")
            if haulage == "External Haulage" and not haulage_who.strip():
                errors.append("Please specify who the external haulage contractor is.")
            # AV config validation — configs must equal unit qty if any configs entered
            for av_u in av_units_with_qty:
                qty       = unit_vals[av_u]
                cfg_total = sum(av_configs.get(av_u, {}).values())
                if cfg_total > 0 and cfg_total != qty:
                    errors.append(
                        f"{av_u}: {cfg_total} layout{'s' if cfg_total != 1 else ''} assigned "
                        f"but {qty} unit{'s' if qty != 1 else ''} selected — please make them match."
                    )
                elif cfg_total == 0 and qty > 0:
                    errors.append(
                        f"{av_u}: please assign a layout configuration for "
                        f"{'all' if qty > 1 else 'this'} {qty} unit{'s' if qty != 1 else ''}."
                    )
            if errors:
                for e in errors:
                    st.warning(e)
            else:
                # Preserve original timestamp/added_by if editing, otherwise stamp now
                if edit_job and edit_idx is not None:
                    orig_ts      = edit_job.get("timestamp", "")
                    orig_by      = edit_job.get("added_by", added_by)
                    edited_ts    = datetime.now().strftime("%d/%m/%Y %H:%M")
                    edited_by    = added_by
                else:
                    orig_ts   = datetime.now().strftime("%d/%m/%Y %H:%M")
                    orig_by   = added_by
                    edited_ts = None
                    edited_by = None

                new_job = {
                    "customer":          customer.strip(),
                    "postcode":          postcode.strip().upper(),
                    "contract_number":   contract_number.strip(),
                    "type":              job_type,
                    "site_move_type":    site_move_type or "",
                    "units":             {u: v for u, v in unit_vals.items() if v > 0},
                    "av_configs":        av_configs,
                    "install_dismantle": install_dismantle,
                    "haulage":           haulage,
                    "haulage_who":       haulage_who.strip() if haulage == "External Haulage" else "",
                    "livery":            livery,
                    "livery_note":       livery_note.strip() if livery == "Customer Livery — Specify" else "",
                    "added_by":          orig_by,
                    "timestamp":         orig_ts,
                }
                if edited_ts:
                    new_job["edited_by"] = edited_by
                    new_job["edited_at"] = edited_ts

                if date_key not in jobs:
                    jobs[date_key] = []
                if edit_idx is not None:
                    jobs[date_key][edit_idx] = new_job
                else:
                    jobs[date_key].append(new_job)
                save_jobs(jobs)
                st.session_state["modal_date"]     = None
                st.session_state["modal_edit_idx"] = None
                st.session_state.dialog_open = False
                st.rerun()

    with ba2:
        if st.button("Cancel", use_container_width=True):
            st.session_state["modal_date"]     = None
            st.session_state["modal_edit_idx"] = None
            st.session_state.dialog_open = False
            st.rerun()

    with ba3:
        if edit_job is not None:
            if st.button("🗑 Delete", use_container_width=True):
                jobs[date_key].pop(edit_idx)
                if not jobs[date_key]:
                    del jobs[date_key]
                save_jobs(jobs)
                st.session_state["modal_date"]     = None
                st.session_state["modal_edit_idx"] = None
                st.session_state.dialog_open = False
                st.rerun()

# ── Trigger dialogs ───────────────────────────────────────────────────────────
# dialog_open flag prevents auto-refresh from re-opening dialogs after they close
if st.session_state.dialog_open:
    if st.session_state.svr_modal_date:
        site_visit_dialog(st.session_state.svr_modal_date, st.session_state.svr_modal_idx)
    elif st.session_state.msv_from_date is not None and st.session_state.msv_idx is not None:
        move_site_visit_dialog(st.session_state.msv_from_date, st.session_state.msv_idx)
    elif st.session_state.move_from_date is not None and st.session_state.move_job_idx is not None:
        move_job_dialog(st.session_state.move_from_date, st.session_state.move_job_idx)
    elif st.session_state.day_view_date:
        day_view_dialog(st.session_state.day_view_date)
    elif st.session_state.expand_date is not None and st.session_state.expand_idx is not None:
        expand_chip_dialog(st.session_state.expand_date, st.session_state.expand_idx)
    elif st.session_state.modal_date:
        job_modal(st.session_state.modal_date, st.session_state.modal_edit_idx)
    else:
        # All state cleared — mark dialog as closed
        st.session_state.dialog_open = False

# ── LIVE HIRE UPLOAD (sidebar) ───────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"""
    <div style='font-family:Figtree,sans-serif;'>
      {KENSITE_LOGO_HTML}
      <div style='font-size:14px;font-weight:700;color:{K_GREEN};margin:10px 0 4px;'>
        Live Hire Report
      </div>
      <div style='font-size:11px;color:{K_GREY};opacity:.7;margin-bottom:10px;'>
        Upload today's MCSrm Equipment on Hire export (.xlsx) to update the live revenue counter.
      </div>
    </div>
    """, unsafe_allow_html=True)

    uploaded_file = st.file_uploader(
        "Upload MCSrm export",
        type=["xlsx"],
        label_visibility="collapsed",
        key="lh_uploader"
    )

    if uploaded_file is not None:
        # Use filename as a key to avoid re-processing the same file on every rerun
        last_processed = st.session_state.get("lh_last_processed", "")
        if uploaded_file.name != last_processed:
            try:
                import pandas as pd
                df_lh = pd.read_excel(uploaded_file)
                if "WeekChg" not in df_lh.columns:
                    st.error("Could not find 'WeekChg' column — is this the right report?")
                else:
                    total_rev  = round(float(df_lh["WeekChg"].sum()), 2)
                    row_count  = int(df_lh["WeekChg"].notna().sum())
                    upload_ts  = datetime.now().strftime("%d/%m/%Y %H:%M")
                    upload_dt  = datetime.now().strftime("%Y-%m-%d")

                    history = live_hire.get("history", []) if isinstance(live_hire, dict) else []
                    history.append({
                        "date":     upload_dt,
                        "revenue":  total_rev,
                        "lines":    row_count,
                        "at":       upload_ts,
                        "filename": uploaded_file.name,
                    })
                    history = history[-60:]
                    new_lh = {
                        "latest":  {"revenue": total_rev, "lines": row_count,
                                    "at": upload_ts, "filename": uploaded_file.name,
                                    "date": upload_dt},
                        "history": history,
                    }
                    save_data(jobs, mcs, site_visits, svr_confirmed, checklist, new_lh)
                    st.session_state["lh_last_processed"] = uploaded_file.name
                    st.success(f"✅ Updated — £{total_rev:,.2f}/wk across {row_count} lines")
            except Exception as e:
                st.error(f"Error reading file: {e}")
        else:
            st.success(f"✅ Already processed — £{live_hire['latest']['revenue']:,.2f}/wk")

    # Show current snapshot in sidebar
    if live_hire and live_hire.get("latest"):
        latest = live_hire["latest"]
        rev    = latest.get("revenue", 0)
        lines  = latest.get("lines", 0)
        ts     = latest.get("at", "")
        fname  = latest.get("filename", "")
        st.markdown(f"""
        <div style='background:{K_GREEN_PALE};border-radius:8px;padding:10px 12px;margin-top:8px;'>
          <div style='font-size:18px;font-weight:800;color:{K_GREEN_DARK};'>
            £{rev:,.2f}<span style='font-size:11px;font-weight:500;'> / week</span>
          </div>
          <div style='font-size:10px;color:{K_GREEN_DARK};opacity:.75;margin-top:2px;'>
            {lines} lines · {fname}
          </div>
          <div style='font-size:10px;color:{K_GREEN_DARK};opacity:.55;margin-top:1px;'>
            Uploaded {ts}
          </div>
        </div>
        """, unsafe_allow_html=True)

        # History table
        history = live_hire.get("history", [])
        if len(history) > 1:
            st.markdown("<div style='margin-top:12px;font-size:11px;font-weight:700;"
                        "color:#888;'>Upload history</div>", unsafe_allow_html=True)
            for entry in reversed(history[-7:]):
                st.markdown(
                    f"<div style='font-size:10px;color:{K_GREY};padding:2px 0;"
                    f"border-bottom:0.5px solid #eee;'>"
                    f"{entry.get('date','')} — "
                    f"<b>£{entry.get('revenue',0):,.2f}</b> "
                    f"({entry.get('lines',0)} lines)</div>",
                    unsafe_allow_html=True)
    else:
        st.markdown(
            f"<div style='font-size:11px;color:{K_GREY};opacity:.5;"
            f"padding:8px;background:#f5f5f5;border-radius:6px;'>No report uploaded yet.</div>",
            unsafe_allow_html=True)

# ── HEADER ────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="ks-header">
  {KENSITE_LOGO_HTML}
  <span class="ks-title">Prep Schedule</span>
</div>
""", unsafe_allow_html=True)

# ── NAV ROW ───────────────────────────────────────────────────────────────────
n1, n2, n3, n4, n5, n6 = st.columns([1.2, 0.8, 1.2, 0.8, 2, 1])
with n1:
    if st.button("◀ Prev Week", use_container_width=True):
        st.session_state.week_offset -= 1; st.rerun()
with n2:
    if st.button("Today", use_container_width=True):
        st.session_state.week_offset = 0; st.rerun()
with n3:
    if st.button("Next Week ▶", use_container_width=True):
        st.session_state.week_offset += 1; st.rerun()
with n4:
    week_opts = [1, 2, 3, 4, 5, 6]
    nw = st.selectbox("", week_opts,
                      index=week_opts.index(st.session_state.n_weeks)
                            if st.session_state.n_weeks in week_opts else 3,
                      label_visibility="collapsed",
                      format_func=lambda x: f"{x} {'week' if x == 1 else 'weeks'}")
    if nw != st.session_state.n_weeks:
        st.session_state.n_weeks = nw; st.rerun()
with n6:
    if st.button("🔒 Log out", use_container_width=True):
        st.session_state["authenticated"] = False; st.rerun()

# ── DATE RANGE ────────────────────────────────────────────────────────────────
today      = date.today()
start_date = get_monday(today) + timedelta(weeks=st.session_state.week_offset)
n_weeks    = st.session_state.n_weeks
end_date   = start_date + timedelta(days=n_weeks * 7 - 1)
st.caption(f"**{start_date.strftime('%d %b')} – {end_date.strftime('%d %b %Y')}**"
           f"  ·  Week {week_num(start_date)}–{week_num(end_date)}")

# ── SUMMARY PILLS ─────────────────────────────────────────────────────────────
all_flat = [j for jl in jobs.values() for j in jl]
counts   = {t: sum(1 for j in all_flat if j["type"] == t) for t in JOB_TYPES}
pills    = "".join(
    f'<span class="pill" style="background:{TYPE_STYLE[t][0]};color:{TYPE_STYLE[t][1]}">'
    f'{TYPE_STYLE[t][2]} {counts[t]} {t}</span>'
    for t in JOB_TYPES
)
pills += (f'<span class="pill" style="background:#f0f0f0;color:{K_GREY}">'
          f'📦 {sum(counts.values())} Total</span>')

# Outstanding PODs / POCs — only for days STRICTLY before today
def job_per_checks_done(dk, ji, job_type):
    """Return dict of per-job check states for a given job."""
    base = f"job_{dk}_{ji}"
    if job_type == "On Hire":
        return {
            "pod":      checklist.get(f"{base}_pod", False),
            "contract": checklist.get(f"{base}_contract", False),
        }
    elif job_type == "Off Hire":
        return {
            "poc":     checklist.get(f"{base}_poc", False),
            "returns": checklist.get(f"{base}_returns", False),
        }
    return {}

def daily_checklist_done(dk):
    """Return True if all 4 daily items + mcs_check ≥ 1 for a given day."""
    d_key = f"daily_{dk}"
    ds    = checklist.get(d_key, {})
    today_dt = datetime.now().strftime("%Y-%m-%d")
    lh_today = (live_hire.get("latest", {}).get("date", "") == today_dt) if live_hire else False
    live_ok  = lh_today or ds.get("live_hire_uploaded", False)
    return (
        ds.get("partial_contracts", False) and
        ds.get("oneoff_contracts",  False) and
        live_ok and
        int(ds.get("mcs_check", 0)) >= 1
    )

def day_jobs_fulfilment_complete(dk):
    """All per-job checks done for all On/Off Hire jobs on this day."""
    day_job_list = jobs.get(dk, [])
    if not day_job_list:
        return True
    for ji, job in enumerate(day_job_list):
        jtype = job["type"]
        base  = f"job_{dk}_{ji}"
        if jtype == "On Hire":
            pod_ok      = checklist.get(f"{base}_pod", False)
            contract_ok = checklist.get(f"{base}_contract", False)
            mcs_ok      = mcs.get(f"{dk}_{ji}", "") == "picked"
            if not (pod_ok and contract_ok and mcs_ok):
                return False
        elif jtype == "Off Hire":
            poc_ok     = checklist.get(f"{base}_poc", False)
            returns_ok = checklist.get(f"{base}_returns", False)
            if not (poc_ok and returns_ok):
                return False
    return True

outstanding_pods  = 0
outstanding_pocs  = 0
today_str = fmt_key(today)
for dk, jlist in jobs.items():
    if dk >= today_str:
        continue  # only past days
    for ji, job in enumerate(jlist):
        if job["type"] == "On Hire":
            checks = job_per_checks_done(dk, ji, "On Hire")
            if not checks.get("pod", False) or not checks.get("contract", False):
                outstanding_pods += 1
        elif job["type"] == "Off Hire":
            checks = job_per_checks_done(dk, ji, "Off Hire")
            if not checks.get("poc", False) or not checks.get("returns", False):
                outstanding_pocs += 1

if outstanding_pods > 0:
    pills += (f'<span class="pill" style="background:#fff3cd;color:#7a5c00;'
              f'border:1px solid #e6c200;">'
              f'⚠ {outstanding_pods} Outstanding POD{"s" if outstanding_pods != 1 else ""}/Contract{"s" if outstanding_pods != 1 else ""}</span>')
else:
    pills += (f'<span class="pill" style="background:{K_GREEN_PALE};color:{K_GREEN_DARK};">'
              f'✅ All PODs and Contracts clear</span>')

if outstanding_pocs > 0:
    pills += (f'<span class="pill" style="background:#fff3cd;color:#7a5c00;'
              f'border:1px solid #e6c200;">'
              f'⚠ {outstanding_pocs} Outstanding POC{"s" if outstanding_pocs != 1 else ""}/Return{"s" if outstanding_pocs != 1 else ""}</span>')
else:
    pills += (f'<span class="pill" style="background:#fdecea;color:#7b1a1a;">'
              f'✅ All POCs and Returns clear</span>')

st.markdown(pills, unsafe_allow_html=True)
st.markdown("<div style='margin-bottom:.5rem'></div>", unsafe_allow_html=True)

# ── LIVE HIRE REVENUE BANNER ──────────────────────────────────────────────────
if live_hire and live_hire.get("latest"):
    latest  = live_hire["latest"]
    rev     = latest.get("revenue", 0)
    rev_ts  = latest.get("at", "")
    history = live_hire.get("history", [])

    # Find a reading from ~7 days ago
    today_dt = datetime.now().date()
    prev_rev = None
    for entry in reversed(history[:-1]):  # exclude the latest
        try:
            entry_dt = datetime.strptime(entry["date"], "%Y-%m-%d").date()
            days_ago = (today_dt - entry_dt).days
            if days_ago >= 7:
                prev_rev = entry["revenue"]
                prev_date = entry_dt.strftime("%-d %b")
                break
        except Exception:
            continue

    # % change
    if prev_rev and prev_rev > 0:
        pct       = ((rev - prev_rev) / prev_rev) * 100
        pct_str   = f"{pct:+.1f}%"
        arrow     = "▲" if pct > 0 else ("▼" if pct < 0 else "—")
        chg_col   = K_GREEN_DARK if pct > 0 else ("#7b1a1a" if pct < 0 else K_GREY)
        chg_bg    = K_GREEN_PALE if pct > 0 else ("#fdecea" if pct < 0 else "#f0f0f0")
        chg_html  = (
            f'<span style="background:{chg_bg};color:{chg_col};border-radius:5px;'
            f'padding:3px 10px;font-size:13px;font-weight:700;margin-left:10px;">'
            f'{arrow} {pct_str} vs {prev_date}</span>'
        )
    else:
        chg_html = (
            f'<span style="font-size:11px;color:{K_GREY};opacity:.5;margin-left:10px;">'
            f'No 7-day comparison yet</span>'
        )

    st.markdown(f"""
    <div style="background:{K_GREEN};border-radius:10px;padding:14px 20px;
                margin-bottom:1rem;display:flex;align-items:center;flex-wrap:wrap;gap:8px;">
      <div>
        <div style="font-size:11px;color:rgba(255,255,255,.75);font-weight:600;
                    letter-spacing:.05em;text-transform:uppercase;">Live Hire — Weekly Revenue</div>
        <div style="display:flex;align-items:baseline;gap:8px;margin-top:2px;">
          <span style="font-size:28px;font-weight:800;color:white;">
            £{rev:,.2f}
          </span>
          <span style="font-size:13px;color:rgba(255,255,255,.7);">/ week</span>
          {chg_html}
        </div>
      </div>
      <div style="margin-left:auto;text-align:right;">
        <div style="font-size:10px;color:rgba(255,255,255,.6);">As at {rev_ts}</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

# ── HELPERS ───────────────────────────────────────────────────────────────────
def week_unit_summary(ws):
    on_u, off_u = {}, {}
    on_total = off_total = 0
    internal_dels = external_dels = 0
    for d in range(7):
        dk = fmt_key(ws + timedelta(days=d))
        for job in jobs.get(dk, []):
            is_off = job["type"] == "Off Hire"
            target = off_u if is_off else on_u
            for u, q in job.get("units", {}).items():
                if q:
                    target[u] = target.get(u, 0) + q
                    if is_off:
                        off_total += q
                    else:
                        on_total += q
            h = job.get("haulage", "None")
            if h == "Internal Haulage":
                internal_dels += 1
            elif h == "External Haulage":
                external_dels += 1
    return on_u, off_u, on_total, off_total, internal_dels, external_dels

def render_week_bar(on_u, off_u, on_total, off_total, internal_dels, external_dels, lh_snapshot=None):
    if not on_u and not off_u and not internal_dels and not external_dels:
        return ""
    html = "<div class='wk-bar'><div style='display:flex;align-items:flex-start;gap:12px;flex-wrap:wrap;'>"
    # Left — unit breakdown
    html += "<div style='flex:1;min-width:0;'><div class='wk-bar-title'>Week totals</div><div class='wk-unit-row'>"
    if on_u:
        html += (f"<span style='font-size:10px;font-weight:700;color:{K_GREEN_DARK};"
                 f"margin-right:3px;'>ON:</span>")
        html += "".join(f'<span class="wku">{u} ×{q}</span>' for u, q in on_u.items())
    if off_u:
        html += (f"<span style='font-size:10px;font-weight:700;color:#7a3a00;"
                 f"margin:0 3px;'>OFF:</span>")
        html += "".join(f'<span class="wku off">{u} ×{q}</span>' for u, q in off_u.items())
    html += "</div></div>"
    # Middle — delivery counters
    html += (
        f"<div style='flex-shrink:0;border-left:1px solid #c3dfc9;padding-left:10px;'>"
        f"<div class='wk-bar-title'>Deliveries</div>"
        f"<div style='display:flex;gap:6px;margin-top:2px;'>"
        f"<span style='background:{K_GREEN};color:white;border-radius:4px;"
        f"padding:2px 8px;font-size:10.5px;font-weight:600;'>🚛 {internal_dels} Internal</span>"
        f"<span style='background:#c0392b;color:white;border-radius:4px;"
        f"padding:2px 8px;font-size:10.5px;font-weight:600;'>🚚 {external_dels} External</span>"
        f"</div></div>"
    )
    # Right — asset totals + live hire revenue
    rev_html = ""
    if lh_snapshot and lh_snapshot.get("latest"):
        rev   = lh_snapshot["latest"].get("revenue", 0)
        ts    = lh_snapshot["latest"].get("at", "")
        rev_html = (
            f"<div style='font-size:11px;font-weight:800;color:{K_GREEN_DARK};"
            f"margin-top:4px;padding-top:4px;border-top:1px solid #c3dfc9;'>"
            f"💰 £{rev:,.2f}/wk live</div>"
            f"<div style='font-size:9px;color:{K_GREEN_DARK};opacity:.6;'>as at {ts}</div>"
        )
    html += (
        f"<div style='text-align:right;flex-shrink:0;white-space:nowrap;'>"
        f"<div style='font-size:10px;font-weight:700;color:{K_GREEN_DARK};margin-bottom:2px;'>"
        f"📦 {on_total} assets on hire</div>"
        f"<div style='font-size:10px;font-weight:700;color:#7b1a1a;'>"
        f"📦 {off_total} assets off hire</div>"
        f"{rev_html}"
        f"</div>"
    )
    html += "</div></div>"
    return html

def render_chip(job, chip_id=""):
    bg, fg, dot = TYPE_STYLE[job["type"]]
    name     = job.get("customer", "(no name)")
    postcode = job.get("postcode", "")
    unit_str = "  ".join(f'{u}×{q}' for u, q in job.get("units", {}).items() if q)
    type_tag = f'<span class="jchip-idtag">{job["type"]}</span>'
    if job.get("site_move_type"):
        sm_icon = "🔄" if job["site_move_type"] == "Movement on Same Site" else "🚛"
        type_tag += (f'<span class="jchip-idtag" style="margin-left:3px;">'
                     f'{sm_icon} {job["site_move_type"]}</span>')
    id_tag   = ""
    if job.get("install_dismantle"):
        id_tag = (f'<span class="jchip-idtag" style="background:{K_GREEN};'
                  f'color:white;margin-left:3px;">I/D</span>')

    # Haulage border
    haulage = job.get("haulage", "None")
    if haulage == "Internal Haulage":
        border_style = f"border-left:4px solid {K_GREEN};"
        haul_tag = f'<span class="jchip-idtag" style="background:{K_GREEN_PALE};color:{K_GREEN_DARK};margin-left:3px;">🚛 Internal</span>'
    elif haulage == "External Haulage":
        border_style = "border-left:4px solid #c0392b;"
        haul_who = job.get("haulage_who", "")
        haul_label = f"🚚 {haul_who}" if haul_who else "🚚 External"
        haul_tag = f'<span class="jchip-idtag" style="background:#fdecea;color:#7b1a1a;margin-left:3px;">{haul_label}</span>'
    else:
        border_style = ""
        haul_tag = ""

    # Timestamp line
    ts_parts = []
    if job.get("added_by"):
        ts_parts.append(job["added_by"])
    if job.get("timestamp"):
        ts_parts.append(job["timestamp"])
    ts_html = ""
    if ts_parts:
        ts_html = f'<span class="jchip-ts">🕐 {" · ".join(ts_parts)}</span>'
    if job.get("edited_at"):
        ts_html += f'<span class="jchip-ts">✏️ {job.get("edited_by","")} · {job["edited_at"]}</span>'

    return (
        f'<div class="jchip" id="{chip_id}" style="background:{bg};color:{fg};{border_style}">'
        f'<span class="jchip-name">{name}</span>'
        + (f'<span class="jchip-sub">{postcode}</span>' if postcode else "")
        + (f'<span class="jchip-units">{unit_str}</span>' if unit_str else "")
        + f'<div style="margin-top:2px;">{type_tag}{id_tag}{haul_tag}</div>'
        + ts_html
        + "</div>"
    )

# ── CALENDAR ──────────────────────────────────────────────────────────────────
DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Day name headers
hcols = st.columns(7)
for i, col in enumerate(hcols):
    with col:
        st.markdown(
            f"<div style='text-align:center;font-size:11px;font-weight:700;"
            f"color:{K_GREY};opacity:.45;letter-spacing:.07em;text-transform:uppercase;"
            f"padding-bottom:3px;'>{DAY_NAMES[i]}</div>",
            unsafe_allow_html=True)

for w in range(n_weeks):
    ws = start_date + timedelta(weeks=w)
    on_u, off_u, on_total, off_total, internal_dels, external_dels = week_unit_summary(ws)
    st.markdown(render_week_bar(on_u, off_u, on_total, off_total, internal_dels, external_dels, live_hire), unsafe_allow_html=True)
    cols = st.columns(7)

    for d in range(7):
        day        = ws + timedelta(days=d)
        dk         = fmt_key(day)
        is_today   = day == today
        is_weekend = day.weekday() >= 5
        is_bh      = dk in bank_holidays
        bh_name    = bank_holidays.get(dk, "")

        card_cls = "is-today" if is_today else ("is-bh" if is_bh else ("is-weekend" if is_weekend else ""))

        # Gold glow — all per-job checks done AND daily checklist complete
        if not is_today and not is_bh:
            if day_jobs_fulfilment_complete(dk) and daily_checklist_done(dk) and jobs.get(dk):
                card_cls = "is-complete"
        date_cls = "is-today" if is_today else ""

        with cols[d]:
            # Build day summary HTML
            day_jobs = jobs.get(dk, [])
            summary_html = ""
            if day_jobs:
                type_counts = {}
                for job in day_jobs:
                    t = job.get("type", "On Hire")
                    type_counts[t] = type_counts.get(t, 0) + 1
                for t, cnt in type_counts.items():
                    bg, fg, _ = TYPE_STYLE[t]
                    label = f"{cnt} × {t}"
                    summary_html += (
                        f'<div class="day-sum-pill" style="background:{bg};color:{fg};">'
                        f'<div class="day-sum-dot" style="background:{fg};opacity:.5;"></div>'
                        f'<span class="day-sum-label">{label}</span>'
                        f'</div>'
                    )
                # MCS progress
                on_hire_jobs  = [j for j in day_jobs if j.get("type") == "On Hire"]
                off_hire_jobs = [j for j in day_jobs if j.get("type") == "Off Hire"]
                picked  = sum(1 for ji, j in enumerate(on_hire_jobs)
                              if mcs.get(f"{dk}_{jobs.get(dk,[]).index(j) if j in jobs.get(dk,[]) else ji}", "") == "picked")
                checked = sum(1 for ji, j in enumerate(off_hire_jobs)
                              if mcs.get(f"{dk}_{jobs.get(dk,[]).index(j) if j in jobs.get(dk,[]) else ji}", "") == "checked")
                if on_hire_jobs and picked == len(on_hire_jobs):
                    summary_html += f'<div style="font-size:9px;color:{K_GREEN_DARK};font-weight:700;padding:1px 5px;">✅ All picked on MCS</div>'
                elif picked > 0:
                    summary_html += f'<div style="font-size:9px;color:{K_GREEN_DARK};padding:1px 5px;">✅ {picked}/{len(on_hire_jobs)} picked MCS</div>'
                if off_hire_jobs and checked == len(off_hire_jobs):
                    summary_html += f'<div style="font-size:9px;color:#7b1a1a;font-weight:700;padding:1px 5px;">✅ All checked in MCS</div>'
                elif checked > 0:
                    summary_html += f'<div style="font-size:9px;color:#7b1a1a;padding:1px 5px;">✅ {checked}/{len(off_hire_jobs)} checked MCS</div>'
                haul_icons = []
                for job in day_jobs:
                    h = job.get("haulage", "None")
                    if h == "Internal Haulage" and "🚛" not in haul_icons:
                        haul_icons.append("🚛")
                    elif h == "External Haulage" and "🚚" not in haul_icons:
                        haul_icons.append("🚚")
                if haul_icons:
                    summary_html += (
                        f'<div style="font-size:10px;padding:2px 5px;opacity:.6;">'
                        f'{" ".join(haul_icons)}</div>'
                    )
            else:
                summary_html = "<div class='day-empty'>No jobs</div>"

            # Fulfilment / Daily checklist indicator
            jobs_done   = day_jobs_fulfilment_complete(dk)
            dailys_done = daily_checklist_done(dk)
            if day_jobs and jobs_done and dailys_done:
                summary_html += (
                    f'<div style="font-size:9px;font-weight:700;color:#7a5c00;'
                    f'background:#fff3b0;border-radius:3px;padding:1px 5px;margin-top:1px;'
                    f'display:inline-block;">✨ Daily\'s Complete</div>'
                )
            elif day_jobs and dailys_done:
                summary_html += (
                    f'<div style="font-size:9px;color:{K_GREEN_DARK};padding:1px 5px;">'
                    f'✅ Dailys done</div>'
                )
            elif day_jobs and jobs_done:
                summary_html += (
                    f'<div style="font-size:9px;color:{K_GREEN_DARK};padding:1px 5px;">'
                    f'✅ Jobs complete</div>'
                )
            sv_count = len(site_visits.get(dk, []))
            if sv_count:
                summary_html += (
                    f'<div style="font-size:10px;font-weight:700;'
                    f'color:{K_PURPLE_DARK};padding:2px 5px;margin-top:1px;">'
                    f'🔍 {sv_count} Site Visit{"s" if sv_count > 1 else ""}</div>'
                )

            bh_tag = (f"<div class='bh-label'>🏴󠁧󠁢󠁥󠁮󠁧󠁿 {bh_name}</div>" if is_bh else "")
            st.markdown(
                f"<div class='day-card {card_cls}'>"
                f"<div class='day-head'>"
                f"<div class='day-name'>{day.strftime('%a')}</div>"
                f"<div class='day-date {date_cls}'>{day.strftime('%-d %b')}</div>"
                f"{bh_tag}</div>"
                f"<div class='day-body'>{summary_html}</div>"
                f"</div>",
                unsafe_allow_html=True)

    # ── Button row — always flat, one per day, outside the card columns ──────
    btn_cols = st.columns(7)
    for d in range(7):
        day      = ws + timedelta(days=d)
        dk       = fmt_key(day)
        day_jobs = jobs.get(dk, [])
        with btn_cols[d]:
            st.markdown("<div class='ks-add-btn'>", unsafe_allow_html=True)
            if st.button("＋ Add / View", key=f"day_{dk}", use_container_width=True):
                if day_jobs:
                    open_dialog(day_view_date=dk)
                else:
                    open_dialog(modal_date=dk, modal_edit_idx=None)
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

# ── SNAPSHOT ─────────────────────────────────────────────────────────────────
st.markdown("---")
with st.expander("📸 Snapshot — export current view"):
    snap_html = f"""
    <div class="snap-outer">
      <div class="snap-header">
        <div class="snap-title">Kensite Prep Schedule</div>
        <div class="snap-period">{start_date.strftime('%d %b')} – {end_date.strftime('%d %b %Y')}
          &nbsp;·&nbsp; Generated {datetime.now().strftime('%d %b %Y %H:%M')}</div>
      </div>
    """
    for w in range(n_weeks):
        ws = start_date + timedelta(weeks=w)
        on_u, off_u, on_total, off_total, internal_dels, external_dels = week_unit_summary(ws)
        parts = []
        if on_u:
            parts.append("ON: " + ", ".join(f"{u}×{q}" for u, q in on_u.items()))
        if off_u:
            parts.append("OFF: " + ", ".join(f"{u}×{q}" for u, q in off_u.items()))
        wk_sum = " | ".join(parts)
        snap_html += (
            f'<div style="background:{K_GREEN_PALE};border:1px solid #c3dfc9;'
            f'border-top:none;padding:5px 10px;font-size:10px;font-weight:700;'
            f'color:{K_GREEN_DARK};">Week {week_num(ws)}'
            + (f' &nbsp;·&nbsp; {wk_sum}' if wk_sum else "")
            + '</div><div class="snap-grid">'
        )
        for d in range(7):
            day  = ws + timedelta(days=d)
            is_t = day == today
            snap_html += (
                f'<div class="snap-dh">'
                f'<div class="snap-dname">{day.strftime("%a")}</div>'
                f'<div class="snap-ddate {"snap-today" if is_t else ""}">'
                f'{day.strftime("%-d %b")}</div></div>'
            )
        for d in range(7):
            day = ws + timedelta(days=d)
            dk  = fmt_key(day)
            snap_html += "<div class='snap-body'>"
            for job in jobs.get(dk, []):
                bg, fg, _ = TYPE_STYLE[job["type"]]
                name  = job.get("customer", "")
                pc    = job.get("postcode", "")
                units = "  ".join(f'{u}×{q}' for u, q
                                  in job.get("units", {}).items() if q)
                type_tag = (f'<span style="font-size:8px;background:rgba(0,0,0,.1);'
                            f'border-radius:3px;padding:1px 4px;margin-right:3px;">'
                            f'{job["type"]}</span>')
                id_tag = ""
                if job.get("install_dismantle"):
                    id_tag = (f'<span style="font-size:8px;background:{K_GREEN};'
                              f'color:white;border-radius:3px;padding:1px 4px;">I/D</span>')
                snap_html += (
                    f'<div class="snap-chip" style="background:{bg};color:{fg}">'
                    f'<span class="snap-name">{name}</span>'
                    + (f'<span class="snap-sub">{pc}</span>' if pc else "")
                    + (f'<span class="snap-sub">{units}</span>' if units else "")
                    + f'<div style="margin-top:2px;">{type_tag}{id_tag}</div>'
                    + "</div>"
                )
            snap_html += "</div>"
        snap_html += "</div>"

    snap_html += (
        f'<div class="snap-footer">kensite.co.uk &nbsp;·&nbsp; 01942 878 747'
        f' &nbsp;·&nbsp; enquiries@kensite.co.uk</div></div>'
    )

    st.markdown(snap_html, unsafe_allow_html=True)

    full_html = (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<style>"
        "@import url('https://fonts.googleapis.com/css2?family=Figtree:wght@400;600;800&display=swap');"
        f"body{{font-family:Figtree,Calibri,sans-serif;padding:20px;background:#fff;color:{K_GREY};}}"
        f".snap-outer{{max-width:1100px;margin:0 auto;}}"
        f".snap-header{{background:{K_GREEN};color:white;padding:14px 20px;border-radius:10px 10px 0 0;}}"
        f".snap-title{{font-size:18px;font-weight:800;}}"
        f".snap-period{{font-size:12px;opacity:.8;margin-top:2px;}}"
        f".snap-grid{{display:grid;grid-template-columns:repeat(7,1fr);"
        f"border:1px solid {K_LGREY};border-top:none;}}"
        f".snap-dh{{background:#f5f5f5;padding:6px 8px;border-right:1px solid {K_LGREY};"
        f"border-bottom:1px solid {K_LGREY};}}"
        f".snap-dname{{font-size:9px;font-weight:700;text-transform:uppercase;"
        f"color:{K_GREY};opacity:.5;letter-spacing:.06em;}}"
        f".snap-ddate{{font-size:14px;font-weight:800;color:{K_GREY};}}"
        f".snap-today{{color:{K_GREEN};}}"
        f".snap-body{{padding:5px;border-right:1px solid {K_LGREY};"
        f"border-bottom:1px solid {K_LGREY};min-height:80px;}}"
        f".snap-chip{{border-radius:4px;padding:3px 6px;margin-bottom:2px;"
        f"font-size:10px;line-height:1.3;}}"
        f".snap-name{{font-weight:700;display:block;}}"
        f".snap-sub{{font-size:9px;opacity:.7;}}"
        f".snap-footer{{background:#f9f9f9;padding:8px 16px;border:1px solid {K_LGREY};"
        f"border-top:none;border-radius:0 0 10px 10px;"
        f"font-size:10px;color:{K_GREY};opacity:.6;text-align:right;}}"
        "</style></head><body>"
        + snap_html +
        "</body></html>"
    )

    st.download_button(
        "⬇ Download Snapshot (HTML)",
        data=full_html,
        file_name=f"kensite_prep_schedule_{today}.html",
        mime="text/html",
        use_container_width=True
    )

# ── EXPORT ────────────────────────────────────────────────────────────────────
st.markdown("---")
with st.expander("📥 Export to Excel / CSV"):
    rows = []
    for dk, jlist in sorted(jobs.items()):
        d = datetime.strptime(dk, "%Y-%m-%d").date()
        for j in jlist:
            unit_str = ", ".join(f'{u}×{q}' for u, q in j.get("units", {}).items() if q)
            av_cfg_str = " | ".join(
                f'{u}: {", ".join(f"{c}×{n}" for c,n in cfgs.items())}'
                for u, cfgs in j.get("av_configs", {}).items() if cfgs
            )
            rows.append({
                "Date":              d.strftime("%d/%m/%Y"),
                "Day":               d.strftime("%A"),
                "Customer":          j.get("customer", ""),
                "Contract No.":      j.get("contract_number", ""),
                "Postcode":          j.get("postcode", ""),
                "Type":              j["type"],
                "Site Move Type":    j.get("site_move_type", ""),
                "Units":             unit_str,
                "AV Configs":        av_cfg_str,
                "Install/Dismantle": "Yes" if j.get("install_dismantle") else "",
                "Haulage":           j.get("haulage", ""),
                "Livery":            j.get("livery", "Standard Livery"),
                "Livery Note":       j.get("livery_note", ""),
                "Added By":          j.get("added_by", ""),
                "Added At":          j.get("timestamp", ""),
                "Edited By":         j.get("edited_by", ""),
                "Edited At":         j.get("edited_at", ""),
            })
    if rows:
        df = pd.DataFrame(rows)
        ec1, ec2 = st.columns(2)
        with ec1:
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name="Prep Schedule")
            st.download_button(
                "⬇ Download Excel", data=buf.getvalue(),
                file_name=f"kensite_prep_{today}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True)
        with ec2:
            st.download_button(
                "⬇ Download CSV", data=df.to_csv(index=False),
                file_name=f"kensite_prep_{today}.csv",
                mime="text/csv", use_container_width=True)
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No jobs in the schedule yet.")
