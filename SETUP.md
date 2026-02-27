# 📰 Daily Brief — Complete Setup Guide

Everything you need to go from zero to a working personalised news digest, delivered to your phone every morning.

---

## What You'll Set Up

| Component | Purpose | Cost |
|---|---|---|
| GitHub repo + Actions | Runs the pipeline daily | Free |
| GitHub Pages | Hosts the website | Free |
| Telegram API | Downloads newspaper PDFs | Free |
| Gemini API | AI summarisation | Free |
| Notification Bot | Sends you a Telegram message when site is ready | Free |
| Cloudflare Access | Password-protects your website | Free |
| Android Widget | One-tap trigger from your home screen | Free |

**Total cost: ₹0**

---

## Overview of the Flow

```
You tap widget on phone
        ↓
GitHub Actions wakes up (~15 mins)
        ↓
Downloads 7 newspaper PDFs from Telegram channel
        ↓
Gemini reads each full newspaper (1 API call each)
Extracts every article with page number
        ↓
Deduplicates cross-newspaper stories (1 API call)
Merges into richer summaries
        ↓
Builds category-based website
Deploys to GitHub Pages (PDFs served via CDN)
        ↓
Sends you a Telegram notification with summary + link
        ↓
You tap the link → read today's digest
```

---

## PART 1 — GitHub Setup

### 1.1 Create the Repository

1. Go to [github.com](https://github.com) → sign in → **New repository**
2. Name it `news-digest` (or anything you like)
3. Set visibility to **Public** (required for free GitHub Pages)
4. Do NOT initialise with README
5. Click **Create repository**

### 1.2 Push the Code

On your computer, open a terminal in the project folder:

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/news-digest.git
git push -u origin main
```

### 1.3 Enable GitHub Pages

1. Repo → **Settings** → **Pages** (left sidebar)
2. Under **Source**, select **GitHub Actions**
3. Save

Your site will be at: `https://YOUR_USERNAME.github.io/news-digest`

### 1.4 Create a Personal Access Token (for the Android widget)

1. github.com → click your avatar → **Settings**
2. Scroll to bottom → **Developer settings**
3. **Personal access tokens** → **Fine-grained tokens** → **Generate new token**
4. Name: `Daily Brief Widget`
5. Repository access: **Only select repositories** → choose `news-digest`
6. Permissions: **Actions** → **Read and Write**
7. Click **Generate token** → copy it (shown only once)

---

## PART 2 — Telegram API Setup (for downloading newspapers)

This gives the bot permission to read your Telegram channel.

### 2.1 Get API Credentials

1. Go to [my.telegram.org](https://my.telegram.org) on a browser
2. Log in with your phone number
3. Click **API Development Tools**
4. Fill in:
   - App title: `Daily Brief`
   - Short name: `dailybrief`
   - Platform: `Other`
5. Click **Create application**
6. Copy your **api_id** (a number) and **api_hash** (a string)

### 2.2 Find Your Channel Username

The channel where newspapers are posted daily. It should look like `@channelname`. If it's a private link like `t.me/+abc123`, you'll need to ask the admin for the public username, or use the channel's numeric ID.

---

## PART 3 — Gemini API Setup (free AI summarisation)

1. Go to [aistudio.google.com](https://aistudio.google.com)
2. Sign in with your Google account
3. Click **Get API Key** → **Create API Key**
4. Select **Create API key in new project**
5. Copy the key

**Free tier:** 20 requests/day, 5 requests/minute — sufficient for this project (we use 9/day).

---

## PART 4 — Notification Bot Setup

This is a separate Telegram bot that messages you personally when the digest is ready.

### 4.1 Create the Bot

1. Open Telegram → search for **@BotFather**
2. Send `/newbot`
3. Give it a name: `Daily Brief Notifier`
4. Give it a username: `yourdailybrief_bot` (must end in `_bot`)
5. BotFather gives you a **token** like `7123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`
6. Copy this token → this is your `NOTIFY_BOT_TOKEN`

### 4.2 Get Your Personal Chat ID

1. Search for **@userinfobot** on Telegram
2. Send it any message
3. It replies with your **Id** number (e.g. `123456789`)
4. Copy this → this is your `NOTIFY_CHAT_ID`

### 4.3 Start the Bot

Important: you must send your bot at least one message before it can message you.

1. Search for your bot by its username in Telegram
2. Tap **Start**
3. Send it any message (e.g. "hello")

---

## PART 5 — Add GitHub Secrets

All credentials are stored as GitHub Secrets — never in the code.

Repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

Add all 8 secrets:

| Secret Name | Where to get it | Example |
|---|---|---|
| `TELEGRAM_API_ID` | my.telegram.org → API Development Tools | `12345678` |
| `TELEGRAM_API_HASH` | my.telegram.org → API Development Tools | `abc123def456...` |
| `TELEGRAM_CHANNEL` | The newspaper Telegram channel | `@bengaluru_papers` |
| `GEMINI_API_KEY` | aistudio.google.com | `AIzaSy...` |
| `NOTIFY_BOT_TOKEN` | @BotFather on Telegram | `7123456789:AAE...` |
| `NOTIFY_CHAT_ID` | @userinfobot on Telegram | `123456789` |
| `SITE_URL` | Your GitHub Pages URL | `https://yourname.github.io/news-digest` |
| `GITHUB_PAT` | GitHub → Settings → Fine-grained tokens | `github_pat_...` |

---

## PART 6 — Test the Pipeline

1. Repo → **Actions** tab
2. Click **Daily News Digest** in the left panel
3. Click **Run workflow** → **Run workflow**
4. Watch the steps execute in real time
5. After ~15 minutes:
   - Your GitHub Pages site should be live with today's digest
   - You should receive a Telegram message from your bot

If anything fails, the workflow uploads `digest.log` as an artifact — download it to see what went wrong.

---

## PART 7 — Cloudflare Access (Password Protect Your Site)

Since the repo is public, the site URL is technically accessible to anyone who finds it. Cloudflare Access puts a login screen in front of it.

### 7.1 Requirements

- A free Cloudflare account at [cloudflare.com](https://cloudflare.com)
- A domain you own (even a cheap `.in` domain for ~₹800/year from GoDaddy/Namecheap)

> **Don't have a domain?** You can skip Cloudflare for now and use the site as-is. The URL is not easily guessable and the digest is not sensitive data.

### 7.2 Connect Your Domain to Cloudflare

1. Cloudflare dashboard → **Add a site** → enter your domain
2. Choose the **Free plan**
3. Cloudflare shows you two nameservers (e.g. `aiden.ns.cloudflare.com`)
4. Go to your domain registrar (GoDaddy/Namecheap) → DNS settings → replace nameservers with Cloudflare's
5. Wait up to 24 hours for propagation (usually under 1 hour)

### 7.3 Point Your Domain to GitHub Pages

In Cloudflare DNS → **Add record**:

```
Type:  CNAME
Name:  digest  (or whatever subdomain you want, e.g. "news")
Target: YOUR_USERNAME.github.io
Proxy: Enabled (orange cloud)
```

Then in GitHub repo → Settings → Pages → **Custom domain** → enter `digest.yourdomain.com` → Save.

### 7.4 Enable Cloudflare Zero Trust Access

1. Cloudflare dashboard → **Zero Trust** (left sidebar)
2. **Access** → **Applications** → **Add an Application**
3. Choose **Self-hosted**
4. Fill in:
   - Application name: `Daily Brief`
   - Application domain: `digest.yourdomain.com`
   - Session duration: `24 hours`
5. Click **Next**

### 7.5 Create Access Policy

1. Policy name: `Owner only`
2. Action: **Allow**
3. Include rule:
   - Selector: **Emails**
   - Value: `your@email.com`
4. Click **Save**

### 7.6 Set Login Method

1. Zero Trust → **Settings** → **Authentication**
2. Click **Add new** → choose **One-time PIN**
   (Cloudflare emails you a 6-digit code to log in — no password to remember)
   
   OR choose **Google** to log in with your Google account.

**Result:** Anyone visiting your site sees a Cloudflare login screen. Only your email can get through. Free for up to 50 users.

---

## PART 8 — Android Widget Setup

The widget is a PWA (Progressive Web App) — a web page that installs as a home screen app. No Play Store needed.

### 8.1 Host the Widget

The simplest option: add `daily_brief_widget.html` to your repo under `docs/` so it's served by GitHub Pages.

```bash
# It's already in docs/ after you push the code
# It will be live at:
https://YOUR_USERNAME.github.io/news-digest/daily_brief_widget.html
```

### 8.2 Install on Your Android Home Screen

1. Open **Chrome** on your Android phone
2. Navigate to `https://YOUR_USERNAME.github.io/news-digest/daily_brief_widget.html`
3. Tap the **3-dot menu** (top right) → **Add to Home screen**
4. Name it `Daily Brief` → tap **Add**
5. It now appears as an app icon on your home screen

### 8.3 One-Time Setup in the Widget

When you open it for the first time, fill in:

| Field | Value |
|---|---|
| GitHub Username | Your GitHub username |
| Repository Name | `news-digest` |
| GitHub Personal Access Token | The token from Part 1.4 |
| Digest Site URL | `https://YOUR_USERNAME.github.io/news-digest` |

Tap **Save & Continue**. You're done.

### 8.4 Daily Usage

1. Open Telegram in the morning
2. Confirm the newspapers have been posted in the channel
3. Switch to the Daily Brief widget on your home screen
4. Tap the big **📰 Run Digest** button
5. Wait ~15 minutes
6. Receive a Telegram notification from your bot
7. Tap the link in the notification → read today's digest

---

## GitHub Secrets — Complete Reference

| Secret | Description |
|---|---|
| `TELEGRAM_API_ID` | Telegram app API ID from my.telegram.org |
| `TELEGRAM_API_HASH` | Telegram app API hash from my.telegram.org |
| `TELEGRAM_CHANNEL` | Username of the channel with newspapers (e.g. `@channel`) |
| `GEMINI_API_KEY` | Google Gemini API key from aistudio.google.com |
| `NOTIFY_BOT_TOKEN` | Telegram bot token from @BotFather |
| `NOTIFY_CHAT_ID` | Your personal Telegram user ID from @userinfobot |
| `SITE_URL` | Full URL of your GitHub Pages site |
| `GITHUB_PAT` | Personal access token for the Android widget trigger |

---

## File Structure Reference

```
news-digest/
├── .github/
│   └── workflows/
│       └── news_digest.yml       ← GitHub Actions (manual trigger)
├── docs/
│   ├── index.html                ← Generated site (replaced each run)
│   ├── digest.json               ← Structured article data
│   ├── daily_brief_widget.html   ← Android home screen widget
│   └── pdfs/                     ← Today's PDFs (artifact only, not in git)
├── state/
│   └── .gitkeep                  ← Folder for first-detection state file
├── digest.py                     ← Main orchestration
├── telegram_downloader.py        ← Downloads PDFs + captures Telegram URLs
├── extractor.py                  ← Extracts all articles via Gemini
├── deduplicator.py               ← Merges cross-newspaper duplicates
├── generate_site.py              ← Builds the HTML website
├── notify.py                     ← Sends Telegram notification when done
├── requirements.txt              ← Python dependencies
└── SETUP.md                      ← This file
```

---

## Troubleshooting

**Workflow fails at Telegram download step**
- Verify `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_CHANNEL` are correct
- Make sure the channel is public or your Telegram account has access
- The first run requires interactive login — run locally once to generate `news_session.session`

**No notification received**
- Verify you sent your bot at least one message (tap Start in the bot's chat)
- Check `NOTIFY_BOT_TOKEN` and `NOTIFY_CHAT_ID` are set correctly
- Download `digest.log` from the failed workflow run for details

**Gemini extraction returns no articles**
- The PDF may be fully scanned (image-only) — OCR fallback will kick in but takes longer
- Check if Tesseract installed correctly in the workflow logs

**Widget shows "404" or "Not found"**
- Make sure GitHub Pages is enabled under Settings → Pages → Source: GitHub Actions
- Run the workflow once so `docs/index.html` exists

**Cloudflare login loop**
- Clear cookies for your domain
- Make sure the policy uses your exact email address
- Check that Cloudflare proxy (orange cloud) is enabled on the DNS record
