# Putting DDS Creations live on the web

Owner of every account below: **Mathesh V**. Create each account in your own name and email so that you own the code, the hosting and the domain.

What ends up where:

| Part | Address | Host | Cost |
|---|---|---|---|
| Company website | `https://ddscreations.com` | GitHub Pages | Free |
| Your portfolio | `https://ddscreations.com/mathesh/` | GitHub Pages | Free |
| Forum (Python) | `https://ddscreations.pythonanywhere.com` | PythonAnywhere (Beginner plan) | Free |
| Domain name | `ddscreations.com` (or `.in`) | Any registrar (GoDaddy, Hostinger, Namecheap, Cloudflare) | Small yearly fee, the only cost |

> **Without a domain:** skip step 3. The site still works for free at `https://<your-github-username>.github.io/ddscreations/`.

---

## 1. Put the code on GitHub (10 minutes)

1. Create a free account at github.com. Using the username `ddscreations` gives you the cleanest URLs.
2. Click **New repository**, name it `ddscreations`, and choose **Public**. GitHub Pages is free only for public repos; the LICENSE file keeps the work legally yours either way.
3. Click **Upload files** and drag in everything from this folder (`docs/`, `forum/`, `LICENSE`, `README.md`, and the rest). Commit.

## 2. Publish the website and portfolio (5 minutes)

1. In the repo, open **Settings → Pages**.
2. Under Source, choose **Deploy from a branch**. Set Branch to `main` and Folder to `/docs`.
3. Save. After 1–2 minutes the site is live at `https://<username>.github.io/ddscreations/`.

## 3. Connect your own domain

1. Buy `ddscreations.com` (or `ddscreations.in`) from a registrar. Check availability first; the name isn't guaranteed to be free.
2. At the registrar, open the DNS settings and add:
   - Four **A** records for `@`: `185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153`
   - One **CNAME** record: `www` → `<username>.github.io`
3. In GitHub **Settings → Pages → Custom domain**, enter `ddscreations.com` and tick **Enforce HTTPS** once it's available. The `docs/CNAME` file already contains `ddscreations.com`; edit it if you buy a different name.
4. DNS can take a few minutes to a few hours to update.

## 4. Put the forum live (15 minutes)

1. Create a free **Beginner** account at pythonanywhere.com. The username becomes your forum address; `ddscreations` gives you `ddscreations.pythonanywhere.com`.
2. Open a **Bash console** and run:
   ```bash
   git clone https://github.com/<github-username>/ddscreations.git
   pip3 install --user flask
   ```
3. Go to the **Web** tab → **Add a new web app** → **Manual configuration** → pick the newest Python version.
4. Open the **WSGI configuration file** link, delete everything in it, and paste in the contents of `forum/wsgi_pythonanywhere.py`, replacing `YOUR_PA_USERNAME` with your username.
5. In the Web tab under **Static files**, add URL `/static/` with directory `/home/<pa-username>/ddscreations/forum/static`.
6. Click **Reload**, then open your forum and **register the username `mathesh` first**. That account becomes the admin, who can pin, lock, delete and give the "HR Pro" badge.

Free-plan notes: one web app, a pythonanywhere.com address only (a custom domain such as `forum.ddscreations.com` needs their paid plan), and a daily CPU allowance. Log in about every 3 months and click "Run until 3 months from today" to keep the app running. The database is a file that stays put; download `ddscreations.db` now and then as a backup.

## 5. Link the pieces together

- In `docs/index.html`, set `FORUM_URL` near the bottom to your forum address.
- In `forum/static/config.js`, set the website and portfolio addresses.
- In `docs/index.html` and `docs/mathesh/index.html`, replace every place marked `EDIT:` (email, LinkedIn, college, years).
- To update the forum after editing on GitHub, run `cd ddscreations && git pull` in a PythonAnywhere console, then click **Reload**.

## 6. Run the forum privately on your laptop (optional)

```bash
cd forum
pip install flask
python app.py
```
Open http://127.0.0.1:5000. Only your computer can see it.

## Making HR Pros
Have the person register, then as admin run (in the browser console on the forum, while logged in):
```js
fetch("/api/users/THEIR_USERNAME/role", {method:"POST", headers:{"Content-Type":"application/json", Authorization:"Bearer "+localStorage.vv_token}, body: JSON.stringify({role:"pro"})})
```

## Branding and ownership checklist
- [ ] GitHub, PythonAnywhere and domain accounts are all in your own name and email
- [ ] Domain WHOIS registrant: Mathesh V (turn privacy protection on)
- [ ] Set up a business email such as hello@ddscreations.com; Zoho Mail has a free plan for custom domains
- [ ] Consider filing a trademark for "DDS Creations" (class 35/42) at ipindia.gov.in once you're sure of the name
