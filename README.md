# DDS Creations
**Career answers from people who actually hire.**
A personal venture founded and owned by **Mathesh V**. © 2026 Mathesh V. All rights reserved (see `LICENSE`).

```
ddscreations/
├── docs/                  → company website (GitHub Pages)  → ddscreations.com
│   ├── index.html
│   ├── CNAME              → your domain name
│   └── mathesh/index.html → Mathesh V's personal portfolio  → ddscreations.com/mathesh/
├── forum/                 → working community forum (Python + Flask + SQLite)
│   ├── app.py             → backend: accounts, categories, threads, answers, votes,
│   │                        accepted answers, HR Pro badges, admin moderation, search
│   ├── static/            → frontend (HTML/CSS/JavaScript)
│   ├── requirements.txt
│   └── wsgi_pythonanywhere.py
├── DEPLOY.md              → step-by-step: GitHub, domain, PythonAnywhere
├── BUSINESS_PLAN.md       → the idea, revenue model, go-to-market, milestones
└── LICENSE                → proprietary, all rights reserved by Mathesh V
```

Quick local run: `cd forum && pip install flask && python app.py`, then open http://127.0.0.1:5000

The first account registered (or the one named in `VV_ADMIN`) is the admin.
