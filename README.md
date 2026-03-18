# 📋 Prep Schedule — Setup Guide

A live, shared prep schedule built with Streamlit. Supports On Hire / Off Hire / On & Off Hire jobs, team members, notes, filters, and Excel/CSV export.

---

## Files in this repo

```
prep-schedule/
├── app.py                        ← Main Streamlit app
├── requirements.txt              ← Python dependencies
├── data/
│   └── jobs.json                 ← Job data (auto-updated by the app)
├── .streamlit/
│   └── secrets.toml.example      ← Secrets template (do NOT commit the real one)
└── .gitignore
```

---

## Step 1 — Create a GitHub repo

1. Go to [github.com](https://github.com) and click **New repository**
2. Name it `prep-schedule` (or anything you like)
3. Set it to **Private** (recommended — keeps your job data private)
4. Click **Create repository**
5. Upload all the files from this folder into the repo (drag & drop works)

---

## Step 2 — Create a GitHub Personal Access Token

The app needs permission to read and write `data/jobs.json` when jobs are added.

1. Go to **GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)**
2. Click **Generate new token (classic)**
3. Give it a name like `prep-schedule-app`
4. Set expiration to **No expiration** (or 1 year)
5. Under **Scopes**, tick **`repo`** (full repo access)
6. Click **Generate token**
7. **Copy the token immediately** — you won't see it again

---

## Step 3 — Deploy on Streamlit Community Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io) and sign in
2. Click **New app**
3. Connect your GitHub account if prompted
4. Select your `prep-schedule` repo, branch `main`, and file `app.py`
5. Click **Advanced settings** before deploying
6. Under **Secrets**, paste the following (with your real values):

```toml
GITHUB_TOKEN  = "ghp_your_actual_token_here"
GITHUB_REPO   = "your-github-username/prep-schedule"
GITHUB_BRANCH = "main"
```

7. Click **Deploy**

---

## Step 4 — Share with your team

Once deployed, Streamlit gives you a URL like:
```
https://your-app-name.streamlit.app
```

Share this URL with your colleagues. Anyone with the link can view and edit the schedule. All changes are saved back to `data/jobs.json` in your GitHub repo automatically.

---

## How data is saved

Every time someone adds or deletes a job, the app:
1. Reads the current `data/jobs.json` from GitHub
2. Makes the change
3. Commits the updated file back to the repo

This means your job data is version-controlled — you can see the full history of changes in GitHub if needed.

---

## Refreshing

The app caches data for **30 seconds**. If a colleague adds a job, other users will see it within 30 seconds on their next interaction, or they can manually refresh the browser tab.

---

## Notes on the GitHub token

- Keep your token secret — never commit it to GitHub
- The token is stored securely in Streamlit's secrets manager (not in your code)
- If you ever need to revoke access, delete the token in GitHub settings
