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

KENSITE_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 40" height="32">
  <rect width="120" height="40" rx="4" fill="#0d823b"/>
  <text x="10" y="27" font-family="Figtree,Calibri,sans-serif" font-weight="800"
        font-size="18" fill="white" letter-spacing="1">KENSITE</text>
</svg>"""

# ── Unit types ────────────────────────────────────────────────────────────────
UNIT_TYPES = [
    "32ft AV", "24ft AV", "20ft AV", "10ft AV",
    "Mobile Welfare", "Static Welfare",
    "Stairs", "2+1", "3+1", "4+2",
    "Tank", "Steps", "IBC",
]

# ── Job types ─────────────────────────────────────────────────────────────────
JOB_TYPES = ["On Hire", "Off Hire", "Site Move"]
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
        <div style="margin-bottom:12px;">{KENSITE_SVG}</div>
        <h2>Prep Schedule</h2>
        <p>Enter your password to continue</p>
      </div>
    </div>
    """, unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1,2,1])
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
    if r.status_code == 404: return None, None
    r.raise_for_status()
    d = r.json()
    return json.loads(base64.b64decode(d["content"]).decode()), d["sha"]

def gh_put(path, obj, sha=None, msg="Update schedule"):
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    payload = {"message": msg,
               "content": base64.b64encode(json.dumps(obj,indent=2).encode()).decode(),
               "branch": GITHUB_BRANCH}
    if sha: payload["sha"] = sha
    requests.put(url, headers=HEADERS, json=payload).raise_for_status()

@st.cache_data(ttl=30)
def load_jobs():
    data, sha = gh_get(DATA_FILE)
    if data is None: return {}, None
    return data.get("jobs", {}), sha

def save_jobs(jobs_dict, sha):
    gh_put(DATA_FILE, {"jobs": jobs_dict}, sha=sha)
    st.cache_data.clear()

# ── Date helpers ──────────────────────────────────────────────────────────────
def get_monday(d): return d - timedelta(days=d.weekday())
def fmt_key(d):    return d.strftime("%Y-%m-%d")
def week_num(d):   return d.isocalendar()[1]

# ── Session state ─────────────────────────────────────────────────────────────
DEFAULTS = {"week_offset":0,"n_weeks":3,"show_add":False,
            "add_date":None,"edit_key":None}
for k,v in DEFAULTS.items():
    if k not in st.session_state: st.session_state[k] = v

jobs, sha = load_jobs()

# ── Global CSS ────────────────────────────────────────────────────────────────
st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Figtree:wght@400;500;600;700;800&display=swap');
html,body,[class*="css"]{{font-family:'Figtree',Calibri,sans-serif;color:{K_GREY};}}
.main .block-container{{padding-top:0.75rem;padding-bottom:2rem;max-width:100%;}}

/* Header bar */
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
.jchip{{border-radius:6px;padding:5px 8px;margin-bottom:3px;font-size:11.5px;line-height:1.4;}}
.jchip-name{{font-weight:700;display:block;font-size:12px;}}
.jchip-sub{{font-size:10px;opacity:.75;display:block;}}
.jchip-units{{font-size:10px;opacity:.6;display:block;margin-top:1px;}}
.jchip-idtag{{display:inline-block;font-size:9.5px;font-weight:700;
              background:rgba(0,0,0,.08);border-radius:3px;
              padding:1px 5px;margin-top:2px;}}

/* Week summary bar */
.wk-bar{{background:{K_GREEN_PALE};border:1px solid #c3dfc9;border-radius:8px;
         padding:6px 10px;margin-bottom:6px;font-size:11px;color:{K_GREEN_DARK};}}
.wk-bar-title{{font-weight:700;font-size:11px;margin-bottom:3px;}}
.wk-unit-row{{display:flex;flex-wrap:wrap;gap:4px;}}
.wku{{background:{K_GREEN};color:white;border-radius:4px;padding:2px 7px;
      font-size:10.5px;font-weight:600;}}
.wku.off{{background:#c05500;}}

/* Overlay modal */
.modal-overlay{{position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:9999;
                display:flex;align-items:center;justify-content:center;}}
.modal-box{{background:white;border-radius:14px;padding:1.75rem;
            width:520px;max-width:95vw;max-height:90vh;overflow-y:auto;
            box-shadow:0 20px 60px rgba(0,0,0,.25);}}
.modal-title{{font-size:17px;font-weight:800;color:{K_GREEN};margin-bottom:1rem;}}

/* Snapshot */
.snap-outer{{font-family:'Figtree',Calibri,sans-serif;}}
.snap-header{{background:{K_GREEN};color:white;padding:14px 20px;
              border-radius:10px 10px 0 0;display:flex;align-items:center;gap:12px;}}
.snap-title{{font-size:18px;font-weight:800;letter-spacing:-.2px;}}
.snap-period{{font-size:12px;opacity:.8;margin-top:2px;}}
.snap-grid{{display:grid;grid-template-columns:repeat(7,1fr);border:1px solid {K_LGREY};
            border-top:none;border-radius:0 0 10px 10px;overflow:hidden;}}
.snap-dh{{background:#f5f5f5;padding:6px 8px;border-right:1px solid {K_LGREY};
          border-bottom:1px solid {K_LGREY};}}
.snap-dname{{font-size:9px;font-weight:700;text-transform:uppercase;
             color:{K_GREY};opacity:.5;letter-spacing:.06em;}}
.snap-ddate{{font-size:14px;font-weight:800;color:{K_GREY};}}
.snap-ddate.today{{color:{K_GREEN};}}
.snap-body{{padding:5px;border-right:1px solid {K_LGREY};
            border-bottom:1px solid {K_LGREY};min-height:80px;vertical-align:top;}}
.snap-chip{{border-radius:4px;padding:3px 6px;margin-bottom:2px;font-size:10px;line-height:1.3;}}
.snap-name{{font-weight:700;display:block;}}
.snap-sub{{font-size:9px;opacity:.7;}}
.snap-footer{{background:#f9f9f9;padding:8px 16px;border:1px solid {K_LGREY};
              border-top:none;border-radius:0 0 10px 10px;
              font-size:10px;color:{K_GREY};opacity:.6;text-align:right;}}

/* Pill summary */
.pill{{display:inline-block;border-radius:20px;padding:4px 12px;
       font-size:12px;font-weight:600;margin-right:5px;margin-bottom:5px;}}

/* Nav buttons */
div[data-testid="column"] button{{border-radius:7px!important;}}
</style>
""", unsafe_allow_html=True)

# ── TOP HEADER ────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="ks-header">
  {KENSITE_SVG}
  <span class="ks-title">Prep Schedule</span>
  <span class="ks-sub">Complete Site Solutions</span>
</div>
""", unsafe_allow_html=True)

# ── NAV ROW ───────────────────────────────────────────────────────────────────
n1,n2,n3,n4,n5,n6 = st.columns([1,1,1,1,2,1])
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
    nw = st.selectbox("", [3,4], index=[3,4].index(st.session_state.n_weeks),
                      label_visibility="collapsed",
                      format_func=lambda x: f"{x} weeks")
    if nw != st.session_state.n_weeks:
        st.session_state.n_weeks = nw; st.rerun()
with n5:
    st.markdown("")  # spacer
with n6:
    if st.button("🔒 Log out", use_container_width=True):
        st.session_state["authenticated"] = False; st.rerun()

# ── DATE RANGE ────────────────────────────────────────────────────────────────
today      = date.today()
start_date = get_monday(today) + timedelta(weeks=st.session_state.week_offset)
n_weeks    = st.session_state.n_weeks
end_date   = start_date + timedelta(days=n_weeks * 7 - 1)
st.caption(f"**{start_date.strftime('%d %b')} – {end_date.strftime('%d %b %Y')}**  ·  Week {week_num(start_date)}–{week_num(end_date)}")

# ── SUMMARY PILLS ─────────────────────────────────────────────────────────────
all_jobs_flat = [j for jl in jobs.values() for j in jl]
counts = {t: sum(1 for j in all_jobs_flat if j["type"]==t) for t in JOB_TYPES}
pill_html = "".join(
    f'<span class="pill" style="background:{TYPE_STYLE[t][0]};color:{TYPE_STYLE[t][1]}">'
    f'{TYPE_STYLE[t][2]} {counts[t]} {t}</span>'
    for t in JOB_TYPES
)
pill_html += f'<span class="pill" style="background:#f0f0f0;color:{K_GREY}">📦 {sum(counts.values())} Total</span>'
st.markdown(pill_html, unsafe_allow_html=True)
st.markdown("<div style='margin-bottom:.5rem'></div>", unsafe_allow_html=True)

# ── HELPER: render unit summary ───────────────────────────────────────────────
def week_unit_summary(week_start):
    on_units  = {}
    off_units = {}
    for d in range(7):
        dk = fmt_key(week_start + timedelta(days=d))
        for job in jobs.get(dk, []):
            target = off_units if job["type"] == "Off Hire" else on_units
            for u in UNIT_TYPES:
                qty = job.get("units", {}).get(u, 0)
                if qty:
                    target[u] = target.get(u, 0) + qty
    return on_units, off_units

def render_unit_bar(on_units, off_units):
    if not on_units and not off_units:
        return ""
    parts_on  = "".join(f'<span class="wku">{u} ×{q}</span>' for u,q in on_units.items())
    parts_off = "".join(f'<span class="wku off">{u} ×{q}</span>' for u,q in off_units.items())
    html = "<div class='wk-bar'><div class='wk-bar-title'>Week totals</div><div class='wk-unit-row'>"
    if parts_on:  html += f"<span style='font-size:10px;font-weight:600;color:{K_GREEN_DARK};margin-right:3px;'>ON:</span>" + parts_on
    if parts_off: html += f"<span style='font-size:10px;font-weight:600;color:#7a3a00;margin:0 3px;'>OFF:</span>" + parts_off
    html += "</div></div>"
    return html

# ── HELPER: render a single job chip ─────────────────────────────────────────
def render_chip(job):
    bg, fg, dot = TYPE_STYLE[job["type"]]
    name = job.get("customer","(no name)")
    sub_parts = []
    if job.get("postcode"):  sub_parts.append(job["postcode"])
    if job.get("type"):      pass  # already shown by colour
    sub = "  ".join(sub_parts)
    unit_str = "  ".join(f'{u}×{q}' for u,q in job.get("units",{}).items() if q)
    id_tag = f'<span class="jchip-idtag">{job["type"]}</span>'
    inst = ""
    if job.get("install_dismantle"):
        inst = f'<span class="jchip-idtag" style="background:{K_GREEN};color:white;margin-left:3px;">I/D</span>'
    html = (
        f'<div class="jchip" style="background:{bg};color:{fg}">'
        f'<span class="jchip-name">{name}</span>'
        + (f'<span class="jchip-sub">{sub}</span>' if sub else "")
        + (f'<span class="jchip-units">{unit_str}</span>' if unit_str else "")
        + f'<div style="margin-top:2px;">{id_tag}{inst}</div>'
        + "</div>"
    )
    return html

# ── CALENDAR ──────────────────────────────────────────────────────────────────
DAY_NAMES = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
hcols = st.columns(7)
for i,col in enumerate(hcols):
    with col:
        st.markdown(
            f"<div style='text-align:center;font-size:11px;font-weight:700;"
            f"color:{K_GREY};opacity:.45;letter-spacing:.07em;text-transform:uppercase;"
            f"padding-bottom:3px;'>{DAY_NAMES[i]}</div>",
            unsafe_allow_html=True)

for w in range(n_weeks):
    ws = start_date + timedelta(weeks=w)
    on_u, off_u = week_unit_summary(ws)
    st.markdown(render_unit_bar(on_u, off_u), unsafe_allow_html=True)
    cols = st.columns(7)
    for d in range(7):
        day = ws + timedelta(days=d)
        dk  = fmt_key(day)
        is_today   = day == today
        is_weekend = day.weekday() >= 5
        dc  = "is-today" if is_today else ("is-weekend" if is_weekend else "")

        with cols[d]:
            st.markdown(
                f"<div class='day-card {dc}'>"
                f"<div class='day-head'>"
                f"<div class='day-name'>{day.strftime('%a')}</div>"
                f"<div class='day-date {'is-today' if is_today else ''}'>"
                f"{day.strftime('%-d %b')}</div></div>"
                f"<div class='day-body'>",
                unsafe_allow_html=True)

            for job in jobs.get(dk, []):
                st.markdown(render_chip(job), unsafe_allow_html=True)

            st.markdown("</div></div>", unsafe_allow_html=True)

            if st.button("＋ Add", key=f"add_{dk}", use_container_width=True):
                st.session_state["show_add"] = True
                st.session_state["add_date"] = dk
                st.session_state["edit_key"] = None
                st.rerun()

# ── ADD / EDIT MODAL ──────────────────────────────────────────────────────────
if st.session_state.get("show_add"):
    add_date = st.session_state.get("add_date", fmt_key(today))
    edit_key = st.session_state.get("edit_key")
    edit_job = jobs.get(add_date, [])[edit_key] if (edit_key is not None and jobs.get(add_date)) else None

    st.markdown("---")
    st.markdown(f"<div style='font-size:16px;font-weight:800;color:{K_GREEN};margin-bottom:.75rem;'>"
                f"{'Edit' if edit_job else 'Add'} Job — {datetime.strptime(add_date,'%Y-%m-%d').strftime('%A %-d %B %Y')}"
                f"</div>", unsafe_allow_html=True)

    with st.form("job_form", clear_on_submit=True):
        fc1, fc2, fc3 = st.columns(3)
        with fc1:
            def_customer = edit_job.get("customer","") if edit_job else ""
            customer = st.text_input("Customer *", value=def_customer)
        with fc2:
            def_postcode = edit_job.get("postcode","") if edit_job else ""
            postcode = st.text_input("Postcode", value=def_postcode)
        with fc3:
            def_type = edit_job.get("type","On Hire") if edit_job else "On Hire"
            job_type = st.selectbox("Type *", JOB_TYPES,
                                    index=JOB_TYPES.index(def_type))

        st.markdown(f"**Units** — enter quantities (leave blank or 0 to omit)")
        unit_vals = {}
        u_cols = st.columns(4)
        for i, u in enumerate(UNIT_TYPES):
            with u_cols[i % 4]:
                def_qty = (edit_job.get("units",{}).get(u,0) if edit_job else 0)
                qty = st.number_input(u, min_value=0, max_value=99,
                                      value=int(def_qty), step=1, key=f"u_{u}")
                unit_vals[u] = qty

        def_id = edit_job.get("install_dismantle", False) if edit_job else False
        install_dismantle = st.checkbox("Install / Dismantle", value=def_id)

        fa1, fa2, fa3 = st.columns([2,2,4])
        with fa1:
            submitted = st.form_submit_button("✅ Save Job", type="primary",
                                               use_container_width=True)
        with fa2:
            cancelled = st.form_submit_button("Cancel", use_container_width=True)
        with fa3:
            if edit_job:
                deleted = st.form_submit_button("🗑 Delete this job",
                                                use_container_width=True)
            else:
                deleted = False

        if submitted:
            if not customer.strip():
                st.warning("Please enter a customer name.")
            else:
                new_job = {
                    "customer": customer.strip(),
                    "postcode": postcode.strip().upper(),
                    "type":     job_type,
                    "units":    {u:v for u,v in unit_vals.items() if v > 0},
                    "install_dismantle": install_dismantle,
                }
                if add_date not in jobs: jobs[add_date] = []
                if edit_key is not None:
                    jobs[add_date][edit_key] = new_job
                else:
                    jobs[add_date].append(new_job)
                save_jobs(jobs, sha)
                st.session_state["show_add"] = False
                st.session_state["add_date"] = None
                st.session_state["edit_key"] = None
                st.rerun()

        if cancelled:
            st.session_state["show_add"] = False
            st.rerun()

        if deleted and edit_key is not None:
            jobs[add_date].pop(edit_key)
            if not jobs[add_date]: del jobs[add_date]
            save_jobs(jobs, sha)
            st.session_state["show_add"] = False
            st.session_state["edit_key"] = None
            st.rerun()

# ── EDIT existing jobs ────────────────────────────────────────────────────────
st.markdown("---")
with st.expander("✏️ Edit or delete existing jobs"):
    sel_date = st.date_input("Select date", value=today, key="edit_date_sel")
    sel_dk   = fmt_key(sel_date)
    day_jobs = jobs.get(sel_dk, [])
    if not day_jobs:
        st.info("No jobs on this day.")
    else:
        for ji, job in enumerate(day_jobs):
            ec1, ec2 = st.columns([5,1])
            with ec1:
                st.markdown(render_chip(job), unsafe_allow_html=True)
            with ec2:
                if st.button("Edit", key=f"edt_{sel_dk}_{ji}"):
                    st.session_state["show_add"] = True
                    st.session_state["add_date"] = sel_dk
                    st.session_state["edit_key"] = ji
                    st.rerun()

# ── SNAPSHOT ─────────────────────────────────────────────────────────────────
st.markdown("---")
with st.expander("📸 Snapshot — export current view"):
    snap_html = f"""
    <div class="snap-outer">
      <div class="snap-header">
        <div>
          <div class="snap-title">Kensite Prep Schedule</div>
          <div class="snap-period">{start_date.strftime('%d %b')} – {end_date.strftime('%d %b %Y')} &nbsp;·&nbsp; Generated {datetime.now().strftime('%d %b %Y %H:%M')}</div>
        </div>
      </div>
    """
    for w in range(n_weeks):
        ws = start_date + timedelta(weeks=w)
        on_u, off_u = week_unit_summary(ws)
        wk_sum = " | ".join(
            [f"ON: {', '.join(f'{u}×{q}' for u,q in on_u.items())}"] if on_u else [] +
            [f"OFF: {', '.join(f'{u}×{q}' for u,q in off_u.items())}"] if off_u else []
        )
        snap_html += f"""
        <div style="background:{K_GREEN_PALE};border:1px solid #c3dfc9;border-top:none;
                    padding:5px 10px;font-size:10px;font-weight:700;color:{K_GREEN_DARK};">
          Week {week_num(ws)}{(' &nbsp;·&nbsp; ' + wk_sum) if wk_sum else ''}
        </div>
        <div class="snap-grid">
        """
        for d in range(7):
            day = ws + timedelta(days=d)
            dk  = fmt_key(day)
            is_t = day == today
            snap_html += f"""
            <div class="snap-dh">
              <div class="snap-dname">{day.strftime('%a')}</div>
              <div class="snap-ddate {'today' if is_t else ''}">{day.strftime('%-d %b')}</div>
            </div>
            """
        for d in range(7):
            day = ws + timedelta(days=d)
            dk  = fmt_key(day)
            snap_html += "<div class='snap-body'>"
            for job in jobs.get(dk, []):
                bg, fg, _ = TYPE_STYLE[job["type"]]
                name  = job.get("customer","")
                pc    = job.get("postcode","")
                units = "  ".join(f'{u}×{q}' for u,q in job.get("units",{}).items() if q)
                id_tag = f'<span style="font-size:8px;background:rgba(0,0,0,.1);border-radius:3px;padding:1px 4px;margin-right:3px;">{job["type"]}</span>'
                if job.get("install_dismantle"):
                    id_tag += f'<span style="font-size:8px;background:{K_GREEN};color:white;border-radius:3px;padding:1px 4px;">I/D</span>'
                snap_html += (
                    f'<div class="snap-chip" style="background:{bg};color:{fg}">'
                    f'<span class="snap-name">{name}</span>'
                    + (f'<span class="snap-sub">{pc}</span>' if pc else "")
                    + (f'<span class="snap-sub">{units}</span>' if units else "")
                    + f'<div style="margin-top:2px;">{id_tag}</div>'
                    + "</div>"
                )
            snap_html += "</div>"
        snap_html += "</div>"

    snap_html += f"""
      <div class="snap-footer">kensite.co.uk &nbsp;·&nbsp; 01942 878 747 &nbsp;·&nbsp; enquiries@kensite.co.uk</div>
    </div>
    """
    st.markdown(snap_html, unsafe_allow_html=True)
    st.download_button(
        "⬇ Download Snapshot (HTML)",
        data=f"<!DOCTYPE html><html><head><meta charset='utf-8'>"
             f"<style>body{{font-family:Figtree,Calibri,sans-serif;padding:20px;background:#fff;}}"
             f"@import url('https://fonts.googleapis.com/css2?family=Figtree:wght@400;600;800&display=swap');"
             f".snap-grid{{display:grid;grid-template-columns:repeat(7,1fr);}}"
             f"</style></head><body>{snap_html}</body></html>",
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
            unit_str = ", ".join(f'{u}×{q}' for u,q in j.get("units",{}).items() if q)
            rows.append({
                "Date":               d.strftime("%d/%m/%Y"),
                "Day":                d.strftime("%A"),
                "Customer":           j.get("customer",""),
                "Postcode":           j.get("postcode",""),
                "Type":               j["type"],
                "Units":              unit_str,
                "Install/Dismantle":  "Yes" if j.get("install_dismantle") else "",
            })
    if rows:
        df = pd.DataFrame(rows)
        ec1, ec2 = st.columns(2)
        with ec1:
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as w:
                df.to_excel(w, index=False, sheet_name="Prep Schedule")
            st.download_button("⬇ Download Excel", data=buf.getvalue(),
                               file_name=f"kensite_prep_{today}.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               use_container_width=True)
        with ec2:
            st.download_button("⬇ Download CSV", data=df.to_csv(index=False),
                               file_name=f"kensite_prep_{today}.csv",
                               mime="text/csv", use_container_width=True)
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No jobs in the schedule yet.")
