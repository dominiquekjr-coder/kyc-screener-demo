# KYC Name Screening — Vercel Demo

A Flask web app that runs two open-source screening queries against a client
name (adverse news + PEP & associations) and renders a numbered, classified
report styled to look like Google search results.

## What's in this repo

```
.
├── api/
│   └── index.py          # Flask app (Vercel entry point)
├── templates/
│   ├── index.html        # Landing page with input form
│   └── results.html      # Report page (Google-style numbered results)
├── static/
│   └── style.css         # Bank-grade styling
├── requirements.txt      # Python dependencies
├── vercel.json           # Vercel build config
├── .gitignore
└── README.md
```

## Two data modes

| Mode | When it's used | What you see |
|------|----------------|--------------|
| **Demo data** | No API key set | Realistic synthetic results — works out of the box |
| **Live data** | `SERPAPI_API_KEY` env var set in Vercel | Real Google results via [SerpAPI](https://serpapi.com) |

A small chip on the report page tells you which mode is active.

## Deploy to Vercel from GitHub — step by step

Detailed walkthrough is in the chat reply. Quick version:

1. Create a free GitHub account.
2. Upload these files to a new GitHub repository.
3. Create a free Vercel account, sign in with GitHub.
4. Click **Add New → Project**, pick the repo, click **Deploy**.
5. (Optional) Add `SERPAPI_API_KEY` under **Project → Settings → Environment Variables**, then redeploy.

## Run locally (optional)

```bash
pip install -r requirements.txt
python api/index.py
# open http://localhost:5000
```

## Notes

The original desktop script (`kyc_name_screening.py`) opens a real Chrome
window and captures full-page screenshots with Playwright. That approach
cannot run on Vercel's serverless platform — no display, no persistent
process, 10-second execution limit, and Chromium binaries exceed the 250 MB
function size cap on the Hobby tier. This version achieves the same visual
output by rendering Google-styled HTML server-side with numbered overlays
and category classifications.

For demonstration use only. Not a substitute for sanctions list checking,
ID verification, or analyst review.
