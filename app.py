import streamlit as st
import json
import base64
import requests
import pandas as pd
from datetime import date, timedelta, datetime
import io

st.set_page_config(page_title="Prep Schedule", layout="wide", page_icon="📋")

# ── Password protection ───────────────────────────────────────────────────────
def check_password():
    if st.session_state.get("authenticated"):
        return True

    st.markdown("""
        <style>
        .login-wrap { max-width: 360px; margin: 100px auto 0; text-align: center; }
        .login-wrap h2 { font-weight: 600; margin-bottom: 4px; }
        .login-wrap p  { color: #888; font-size: 14px; margin-bottom: 24px; }
        </style>
        <div class="login-wrap">
            <div style="font-size:40px;margin-bottom:10px;">📋</div>
            <h2>Prep Schedule</h2>
            <p>Enter the password to continue</p>
        </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        pwd = st.text_input("Password", type="password",
                            placeholder="Enter password...",
                            label_visibility="collapsed")
        if st.button("Log in", use_container_width=True, type="primary"):
            if pwd == st.secrets["APP_PASSWORD"]:
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("Incorrect password. Please try again.")
    return False

if not check_password():
    st.stop()

# ── GitHub config ─────────────────────────────────────────────────────────────
GITHUB_TOKEN  = st.secrets["GITHUB_TOKEN"]
GITHUB_REPO   = st.secrets["GITHUB_REPO"]
GITHUB_BRANCH = st.secrets.get("GITHUB_BRANCH", "main")
DATA_FILE     = "data/jobs.json"

HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}

# ── Colour palette ────────────────────────────────────────────────────────────
TYPE_COLOURS = {
    "On Hire":       ("#E1F5EE", "#085041"),
    "Off Hire":      ("#FAECE7", "#4A1B0C"),
    "On & Off Hire": ("#E6F1FB", "#042C53"),
}
TYPE_BADGE = {
    "On Hire":       "🟢",
    "Off Hire":      "🔴",
    "On & Off Hire": "🔵",
}

# ── GitHub helpers ────────────────────────────────────────────────────────────
def gh_get(path):
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    r = requests.get(url, headers=HEADERS, params={"ref": GITHUB_BRANCH})
    if r.status_code == 404:
        return None, None
    r.raise_for_status()
    data = r.json()
    content = base64.b64decode(data["content"]).decode()
    return json.loads(content), data["sha"]

def gh_put(path, content_dict, sha=None, message="Update schedule data"):
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    payload = {
        "message": message,
        "content": base64.b64encode(
            json.dumps(content_dict, indent=2).encode()
        ).decode(),
        "branch": GITHUB_BRANCH,
    }
    if sha:
        payload["sha"] = sha
    r = requests.put(url, headers=HEADERS, json=payload)
    r.raise_for_status()

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
def get_monday(d):
    return d - timedelta(days=d.weekday())

def fmt_key(d):
    return d.strftime("%Y-%m-%d")

def week_number(d):
    return d.isocalendar()[1]

# ── Session state ─────────────────────────────────────────────────────────────
for k, v in [("week_offset", 0), ("n_weeks", 3),
             ("filter_type", "All"), ("filter_member", "All")]:
    if k not in st.session_state:
        st.session_state[k] = v

jobs, sha = load_jobs()

# ── Styles ────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
.main .block-container { padding-top: 1.5rem; padding-bottom: 2rem; max-width: 100%; }
.day-wrap { border: 1px solid #E8E6DF; border-radius: 10px; overflow: hidden; margin: 2px; min-height: 180px; }
.day-header { padding: 8px 10px 6px; border-bottom: 1px solid #E8E6DF; }
.day-name { font-size: 11px; font-weight: 600; color: #888; letter-spacing: .06em; text-transform: uppercase; }
.day-date { font-size: 18px; font-weight: 600; color: #1a1a1a; }
.day-date.today { color: #185FA5; }
.day-date.weekend { color: #aaa; }
.day-body { padding: 6px; }
.job-chip { border-radius: 6px; padding: 5px 8px; margin-bottom: 4px; font-size: 12px; line-height: 1.4; }
.job-name { font-weight: 600; display: block; }
.job-sub { font-size: 10.5px; opacity: .8; }
.pill { display: inline-block; border-radius: 20px; padding: 4px 14px; font-size: 13px; font-weight: 500; margin-right: 6px; margin-bottom: 6px; }
.wk-label { font-size: 11px; font-weight: 600; color: #aaa; letter-spacing: .05em; padding: 4px 0 8px; text-transform: uppercase; }
</style>
""", unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────────────────────────────
c1, c2, c3, c4, c5, c6 = st.columns([3, 1, 1, 1, 1, 1])
with c1:
    st.markdown("## 📋 Prep Schedule")
with c2:
    if st.button("◀ Prev", use_container_width=True):
        st.session_state.week_offset -= 1; st.rerun()
with c3:
    if st.button("Today", use_container_width=True):
        st.session_state.week_offset = 0; st.rerun()
with c4:
    if st.button("Next ▶", use_container_width=True):
        st.session_state.week_offset += 1; st.rerun()
with c5:
    nw = st.selectbox("Show", [3, 4], index=[3,4].index(st.session_state.n_weeks),
                      label_visibility="collapsed")
    if nw != st.session_state.n_weeks:
        st.session_state.n_weeks = nw; st.rerun()
with c6:
    if st.button("🔒 Log out", use_container_width=True):
        st.session_state["authenticated"] = False; st.rerun()

# ── Date range ────────────────────────────────────────────────────────────────
today      = date.today()
start_date = get_monday(today) + timedelta(weeks=st.session_state.week_offset)
end_date   = start_date + timedelta(days=st.session_state.n_weeks * 7 - 1)
st.caption(f"Showing **{start_date.strftime('%d %b')} – {end_date.strftime('%d %b %Y')}**")

# ── Filters ───────────────────────────────────────────────────────────────────
all_members = sorted({j["member"] for v in jobs.values() for j in v if j.get("member")})
fc1, fc2, _ = st.columns([2, 2, 4])
with fc1:
    opts = ["All"] + list(TYPE_COLOURS.keys())
    ft = st.selectbox("Filter by type", opts,
                      index=opts.index(st.session_state.filter_type) if st.session_state.filter_type in opts else 0)
    st.session_state.filter_type = ft
with fc2:
    mopts = ["All"] + all_members
    fm = st.selectbox("Filter by team member", mopts,
                      index=mopts.index(st.session_state.filter_member) if st.session_state.filter_member in mopts else 0)
    st.session_state.filter_member = fm

# ── Summary pills ─────────────────────────────────────────────────────────────
def job_visible(j):
    if ft != "All" and j["type"] != ft: return False
    if fm != "All" and j.get("member") != fm: return False
    return True

vis    = [j for jl in jobs.values() for j in jl if job_visible(j)]
counts = {t: sum(1 for j in vis if j["type"] == t) for t in TYPE_COLOURS}
pills  = "".join(f'<span class="pill" style="background:{bg};color:{fg}">{TYPE_BADGE[t]} {counts[t]} {t}</span>'
                 for t, (bg, fg) in TYPE_COLOURS.items())
pills += f'<span class="pill" style="background:#F1EFE8;color:#2C2C2A">📦 {sum(counts.values())} Total</span>'
st.markdown(pills, unsafe_allow_html=True)
st.markdown("<br>", unsafe_allow_html=True)

# ── Calendar ──────────────────────────────────────────────────────────────────
DAY_NAMES = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
hcols = st.columns(7)
for i, col in enumerate(hcols):
    with col:
        st.markdown(f"<div style='text-align:center;font-size:12px;font-weight:600;color:#888;"
                    f"letter-spacing:.06em;padding-bottom:4px;'>{DAY_NAMES[i]}</div>",
                    unsafe_allow_html=True)

for w in range(st.session_state.n_weeks):
    ws = start_date + timedelta(weeks=w)
    st.markdown(f"<div class='wk-label'>Week {week_number(ws)}</div>", unsafe_allow_html=True)
    cols = st.columns(7)
    for d in range(7):
        day = ws + timedelta(days=d)
        dk  = fmt_key(day)
        is_today   = day == today
        is_weekend = day.weekday() >= 5
        dc  = "today" if is_today else ("weekend" if is_weekend else "")
        bgs = "background:#EFF7FF;" if is_today else ("background:#FAFAF8;" if is_weekend else "background:#fff;")

        with cols[d]:
            st.markdown(
                f"<div class='day-wrap' style='{bgs}'>"
                f"<div class='day-header'><div class='day-name'>{day.strftime('%a')}</div>"
                f"<div class='day-date {dc}'>{day.strftime('%-d %b')}</div></div>"
                f"<div class='day-body'>",
                unsafe_allow_html=True
            )
            for job in jobs.get(dk, []):
                if not job_visible(job): continue
                bg, fg = TYPE_COLOURS[job["type"]]
                sub = " · ".join(p for p in [job.get("member",""), job.get("notes","")] if p)
                st.markdown(
                    f"<div class='job-chip' style='background:{bg};color:{fg}'>"
                    f"<span class='job-name'>{TYPE_BADGE[job['type']]} {job['name']}</span>"
                    + (f"<span class='job-sub'>{sub}</span>" if sub else "")
                    + "</div>", unsafe_allow_html=True
                )
            st.markdown("</div></div>", unsafe_allow_html=True)
            if st.button("＋ Add", key=f"add_{dk}", use_container_width=True):
                st.session_state["modal_date"] = dk; st.rerun()

# ── Add / Edit / Delete ───────────────────────────────────────────────────────
st.markdown("---")
with st.expander("➕ Add / Edit / Delete Jobs",
                 expanded=bool(st.session_state.get("modal_date"))):
    sel_date = st.date_input(
        "Date",
        value=datetime.strptime(
            st.session_state.get("modal_date", fmt_key(today)), "%Y-%m-%d"
        ).date(),
        key="sel_date_inp"
    )
    sel_dk   = fmt_key(sel_date)
    existing = jobs.get(sel_dk, [])

    if existing:
        st.markdown("**Jobs on this day:**")
        for ji, job in enumerate(existing):
            ec1, ec2 = st.columns([5, 1])
            with ec1:
                bg, fg = TYPE_COLOURS[job["type"]]
                sub = " · ".join(p for p in [job.get("member",""), job.get("notes","")] if p)
                st.markdown(
                    f"<div class='job-chip' style='background:{bg};color:{fg};margin-bottom:4px'>"
                    f"<span class='job-name'>{TYPE_BADGE[job['type']]} {job['name']}</span>"
                    + (f"<span class='job-sub'>{sub}</span>" if sub else "")
                    + "</div>", unsafe_allow_html=True
                )
            with ec2:
                if st.button("🗑 Del", key=f"del_{sel_dk}_{ji}"):
                    existing.pop(ji)
                    if existing:
                        jobs[sel_dk] = existing
                    elif sel_dk in jobs:
                        del jobs[sel_dk]
                    save_jobs(jobs, sha)
                    st.success("Deleted."); st.rerun()

    st.markdown("**Add a new job:**")
    f1, f2 = st.columns(2)
    with f1:
        new_name   = st.text_input("Job name / reference", key="new_name")
        new_type   = st.selectbox("Type", list(TYPE_COLOURS.keys()), key="new_type")
    with f2:
        new_member = st.text_input("Team member (optional)", key="new_member")
        new_notes  = st.text_input("Notes (optional)", key="new_notes",
                                   placeholder="Driver, time, details...")

    if st.button("✅ Save Job", type="primary"):
        if new_name.strip():
            jobs.setdefault(sel_dk, []).append({
                "name": new_name.strip(), "type": new_type,
                "member": new_member.strip(), "notes": new_notes.strip(),
            })
            save_jobs(jobs, sha)
            st.success(f"Job '{new_name}' added to {sel_date.strftime('%a %-d %b')}.")
            st.rerun()
        else:
            st.warning("Please enter a job name.")

# ── Export ────────────────────────────────────────────────────────────────────
st.markdown("---")
with st.expander("📥 Export to Excel / CSV"):
    rows = [
        {"Date": datetime.strptime(dk, "%Y-%m-%d").strftime("%d/%m/%Y"),
         "Day":  datetime.strptime(dk, "%Y-%m-%d").strftime("%A"),
         "Job": j["name"], "Type": j["type"],
         "Team Member": j.get("member",""), "Notes": j.get("notes","")}
        for dk, jl in sorted(jobs.items()) for j in jl
    ]
    if rows:
        df = pd.DataFrame(rows)
        ec1, ec2 = st.columns(2)
        with ec1:
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name="Prep Schedule")
            st.download_button("⬇ Download Excel", data=buf.getvalue(),
                               file_name=f"prep_schedule_{today}.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               use_container_width=True)
        with ec2:
            st.download_button("⬇ Download CSV", data=df.to_csv(index=False),
                               file_name=f"prep_schedule_{today}.csv",
                               mime="text/csv", use_container_width=True)
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No jobs in the schedule yet.")
