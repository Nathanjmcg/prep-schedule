import streamlit as st
import json
import base64
import requests
import pandas as pd
from datetime import date, timedelta, datetime
import io

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
]

JOB_TYPES = ["On Hire", "Off Hire", "Site Move"]
TEAM_MEMBERS = ["Jake", "Ewa", "Klaudia", "Chris", "Nick", "Chloe", "Peter", "Callum", "Nathan"]
TYPE_STYLE = {
    "On Hire":   (K_GREEN_PALE, K_GREEN_DARK, "●"),
    "Off Hire":  ("#fff3e8",    "#7a3a00",    "●"),
    "Site Move": ("#eef2ff",    "#2d3a8c",    "●"),
}

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
def load_jobs():
    data, sha = gh_get(DATA_FILE)
    if data is None:
        return {}, None
    return data.get("jobs", {}), sha

def save_jobs(jobs_dict, sha):
    gh_put(DATA_FILE, {"jobs": jobs_dict}, sha=sha)
    st.cache_data.clear()

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
             ("modal_date", None), ("modal_edit_idx", None)]:
    if k not in st.session_state:
        st.session_state[k] = v

jobs, sha = load_jobs()
bank_holidays = get_bank_holidays()

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
           min-height:170px;background:{K_WHITE};margin:2px;}}
.day-card.is-today{{border-color:{K_GREEN};border-width:2px;}}
.day-card.is-weekend{{background:#fafafa;}}
.day-head{{padding:7px 9px 5px;border-bottom:1px solid {K_LGREY};}}
.day-name{{font-size:10px;font-weight:700;color:{K_GREY};opacity:.5;
           text-transform:uppercase;letter-spacing:.07em;}}
.day-date{{font-size:17px;font-weight:800;color:{K_GREY};}}
.day-date.is-today{{color:{K_GREEN};}}
.day-body{{padding:5px;}}

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

/* Edit buttons — small and subtle */
.ks-edit-btn button {{
  background-color: transparent !important;
  color: {K_GREY} !important;
  border: 1px solid {K_LGREY} !important;
  font-size: 11px !important;
  padding: 2px 6px !important;
  border-radius: 4px !important;
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

/* Day card bank holiday highlight */
.day-card.is-bh {{ background: #fffbea !important; border-color: #e6c200 !important; }}
.bh-label {{ font-size: 9px; font-weight: 700; color: #7a6000;
             background: #fff3b0; border-radius: 3px; padding: 1px 5px;
             display: inline-block; margin-top: 2px; }}
</style>
""", unsafe_allow_html=True)

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
    u_cols = st.columns(4)
    for i, u in enumerate(UNIT_TYPES):
        with u_cols[i % 4]:
            def_qty = int(edit_job.get("units", {}).get(u, 0)) if edit_job else 0
            unit_vals[u] = st.number_input(u, min_value=0, max_value=99,
                                           value=def_qty, step=1, key=f"mu_{u}")

    def_id = edit_job.get("install_dismantle", False) if edit_job else False
    install_dismantle = st.checkbox("Install / Dismantle", value=def_id)

    st.markdown("<div style='margin-top:1rem'></div>", unsafe_allow_html=True)
    ba1, ba2, ba3 = st.columns([2, 2, 2])

    with ba1:
        if st.button("✅ Save Job", type="primary", use_container_width=True):
            errors = []
            if not customer.strip():
                errors.append("Please enter a customer name.")
            if added_by == "— Select your name *":
                errors.append("Please select who is adding this entry.")
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
                    "type":              job_type,
                    "units":             {u: v for u, v in unit_vals.items() if v > 0},
                    "install_dismantle": install_dismantle,
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
                save_jobs(jobs, sha)
                st.session_state["modal_date"]     = None
                st.session_state["modal_edit_idx"] = None
                st.rerun()

    with ba2:
        if st.button("Cancel", use_container_width=True):
            st.session_state["modal_date"]     = None
            st.session_state["modal_edit_idx"] = None
            st.rerun()

    with ba3:
        if edit_job is not None:
            if st.button("🗑 Delete", use_container_width=True):
                jobs[date_key].pop(edit_idx)
                if not jobs[date_key]:
                    del jobs[date_key]
                save_jobs(jobs, sha)
                st.session_state["modal_date"]     = None
                st.session_state["modal_edit_idx"] = None
                st.rerun()

# ── Trigger modal if state is set ────────────────────────────────────────────
if st.session_state.modal_date:
    job_modal(st.session_state.modal_date,
              st.session_state.modal_edit_idx)

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
st.markdown(pills, unsafe_allow_html=True)
st.markdown("<div style='margin-bottom:.5rem'></div>", unsafe_allow_html=True)

# ── HELPERS ───────────────────────────────────────────────────────────────────
def week_unit_summary(ws):
    on_u, off_u = {}, {}
    for d in range(7):
        dk = fmt_key(ws + timedelta(days=d))
        for job in jobs.get(dk, []):
            target = off_u if job["type"] == "Off Hire" else on_u
            for u, q in job.get("units", {}).items():
                if q: target[u] = target.get(u, 0) + q
    return on_u, off_u

def render_week_bar(on_u, off_u):
    if not on_u and not off_u:
        return ""
    html = "<div class='wk-bar'><div class='wk-bar-title'>Week totals</div><div class='wk-unit-row'>"
    if on_u:
        html += (f"<span style='font-size:10px;font-weight:700;color:{K_GREEN_DARK};"
                 f"margin-right:3px;'>ON:</span>")
        html += "".join(f'<span class="wku">{u} ×{q}</span>' for u, q in on_u.items())
    if off_u:
        html += (f"<span style='font-size:10px;font-weight:700;color:#7a3a00;"
                 f"margin:0 3px;'>OFF:</span>")
        html += "".join(f'<span class="wku off">{u} ×{q}</span>' for u, q in off_u.items())
    html += "</div></div>"
    return html

def render_chip(job):
    bg, fg, dot = TYPE_STYLE[job["type"]]
    name     = job.get("customer", "(no name)")
    postcode = job.get("postcode", "")
    unit_str = "  ".join(f'{u}×{q}' for u, q in job.get("units", {}).items() if q)
    type_tag = f'<span class="jchip-idtag">{job["type"]}</span>'
    id_tag   = ""
    if job.get("install_dismantle"):
        id_tag = (f'<span class="jchip-idtag" style="background:{K_GREEN};'
                  f'color:white;margin-left:3px;">I/D</span>')

    # Timestamp line
    ts_parts = []
    if job.get("added_by"):
        ts_parts.append(job["added_by"])
    if job.get("timestamp"):
        ts_parts.append(job["timestamp"])
    ts_html = ""
    if ts_parts:
        ts_html = (f'<span class="jchip-ts">🕐 {" · ".join(ts_parts)}</span>')
    if job.get("edited_at"):
        ts_html += (f'<span class="jchip-ts">✏️ {job.get("edited_by","")} · {job["edited_at"]}</span>')

    return (
        f'<div class="jchip" style="background:{bg};color:{fg}">'
        f'<span class="jchip-name">{name}</span>'
        + (f'<span class="jchip-sub">{postcode}</span>' if postcode else "")
        + (f'<span class="jchip-units">{unit_str}</span>' if unit_str else "")
        + f'<div style="margin-top:2px;">{type_tag}{id_tag}</div>'
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
    on_u, off_u = week_unit_summary(ws)
    st.markdown(render_week_bar(on_u, off_u), unsafe_allow_html=True)
    cols = st.columns(7)

    for d in range(7):
        day        = ws + timedelta(days=d)
        dk         = fmt_key(day)
        is_today   = day == today
        is_weekend = day.weekday() >= 5
        is_bh      = dk in bank_holidays
        bh_name    = bank_holidays.get(dk, "")

        card_cls = "is-today" if is_today else ("is-bh" if is_bh else ("is-weekend" if is_weekend else ""))
        date_cls = "is-today" if is_today else ""

        with cols[d]:
            # Day card header
            bh_tag = (f"<div class='bh-label'>🏴󠁧󠁢󠁥󠁮󠁧󠁿 {bh_name}</div>" if is_bh else "")
            st.markdown(
                f"<div class='day-card {card_cls}'>"
                f"<div class='day-head'>"
                f"<div class='day-name'>{day.strftime('%a')}</div>"
                f"<div class='day-date {date_cls}'>"
                f"{day.strftime('%-d %b')}</div>"
                f"{bh_tag}"
                f"</div>"
                f"<div class='day-body'>",
                unsafe_allow_html=True)

            # Job chips — clicking opens edit modal
            for ji, job in enumerate(jobs.get(dk, [])):
                st.markdown(render_chip(job), unsafe_allow_html=True)
                st.markdown("<div class='ks-edit-btn'>", unsafe_allow_html=True)
                if st.button("✏️ Edit", key=f"edit_{dk}_{ji}",
                             use_container_width=True):
                    st.session_state["modal_date"]     = dk
                    st.session_state["modal_edit_idx"] = ji
                    st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)

            st.markdown("</div></div>", unsafe_allow_html=True)

            # Green Add button
            st.markdown("<div class='ks-add-btn'>", unsafe_allow_html=True)
            if st.button("＋ Add", key=f"add_{dk}", use_container_width=True):
                st.session_state["modal_date"]     = dk
                st.session_state["modal_edit_idx"] = None
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
        on_u, off_u = week_unit_summary(ws)
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
            rows.append({
                "Date":              d.strftime("%d/%m/%Y"),
                "Day":               d.strftime("%A"),
                "Customer":          j.get("customer", ""),
                "Postcode":          j.get("postcode", ""),
                "Type":              j["type"],
                "Units":             unit_str,
                "Install/Dismantle": "Yes" if j.get("install_dismantle") else "",
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
