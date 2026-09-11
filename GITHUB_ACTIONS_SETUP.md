# GitHub Actions Setup Guide

## Step 1: Push Code to GitHub

In PowerShell, run these commands from your project folder:

```powershell
cd C:\dev\LolDailyDiscord

# Initialize git (if not already done)
git init

# Add your GitHub repo as remote
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git

# Add all files
git add .

# Commit
git commit -m "Initial commit: LoL Daily Discord Bot"

# Push to GitHub
git branch -M main
git push -u origin main
```

## Step 2: Add GitHub Secrets and Variables

Your `.env` variables need to be added to the repository so they're available to GitHub Actions but stay private.

1. Go to your GitHub repo → **Settings** → **Secrets and variables** → **Actions**
2. Add each **Secret** (Settings → Secrets and variables → Actions → **New repository secret**):

| Secret Name | Value |
|------------|-------|
| `DISCORD_TOKEN` | Your bot token from `.env` |
| `RIOT_API_KEY` | Your Riot API key from `.env` |
| `PLAYERS_JSON` | Your players JSON array from `.env` (e.g. `[{"name":"Cimo","tag":"EUW25"},...]`) |

3. Add each **Variable** (same page, **Variables** tab → **New repository variable**):

| Variable Name | Value |
|--------------|-------|
| `DISCORD_CHANNEL_ID` | Your channel ID (number) from `.env` |
| `RIOT_PLATFORM` | `EUW1` (from `.env`) |
| `RIOT_REGION` | `europe` (from `.env`) |
| `TIMEZONE` | `Europe/Paris` (from `.env`) |

`RUN_HOUR` / `RUN_MINUTE` are no longer used: the workflow always executes once via `IMMEDIATE_RUN`. The daily 08:20 UTC trigger comes from an **external cron service** (see Step 3) calling the GitHub `workflow_dispatch` API.

## Step 3: Set up the daily trigger (external cron → GitHub API)

GitHub's built-in `schedule` (cron) is NOT used, because it never fired on this repo after the workflow file had been renamed (0 scheduled runs — see Troubleshooting). GitHub also openly warns that scheduled workflows are best-effort (delays of 10+ minutes, sometimes skipped). The reliable, free replacement: a cron-job.org job that POSTs to the GitHub API to trigger the workflow, which GitHub then queues immediately.

1. **Create a fine-grained Personal Access Token (PAT)**
   - GitHub → your avatar → **Settings** → **Developer settings** → **Personal access tokens** → **Fine-grained tokens** → **Generate new token**
   - Repository access: **Only select repositories** → `LolDailyDiscord`
   - Permissions → **Actions**: **Read and write**
   - Generate and **copy the token now** (shown only once). Treat it like a password.

2. **Create a free cron-job.org account and job**
   - Go to https://cron-job.org and sign up (free, no credit card).
   - **Create a new cronjob**:
     - Name: `trigger-lol-bot`
     - Schedule: custom cron expression `20 8 * * *` (08:20 UTC daily). cron-job.org schedules in **UTC** by default — verify the timezone dropdown shows UTC (or use Europe/Paris if you prefer 08:20 local).
     - Method: `POST`
     - URL: `https://api.github.com/repos/mt4e/LolDailyDiscord/actions/workflows/daily-bot.yml/dispatches`
     - Headers:
       - `Authorization: Bearer <your_fine_grained_PAT>`
       - `Accept: application/vnd.github+json`
       - `Content-Type: application/json`
     - Body: `{"ref":"main"}`
     - Save.

3. **Test it immediately**
   - cron-job.org → your job → **Execute/Test run**. Within ~30 seconds a `workflow_dispatch` run appears in your repo's **Actions** tab.
   - The dispatcher returns HTTP 204 on success (errors: 401 = bad/expired token, 422 = wrong ref or missing permissions).

## Step 4: Verify GitHub Actions

1. Go to your repo → **Actions** tab
2. You should see a workflow called "Daily LoL Summary Bot"
3. It will be triggered daily at **08:20 UTC** by cron-job.org (09:20 Europe/Paris in winter, 10:20 in summer)
4. You can also click **Run workflow** → **Run workflow** to test it manually

## Step 5: Persistent state (LP diff memory)

The bot stores its memory in `lol_daily.sqlite3` (LP snapshots + the date/time of each successful run). This file is tracked in git and is committed back to the repository by the workflow after every run, so the LP diff stays consistent day after day.

- ❗ The state file is shared: run the bot **either here on GitHub Actions or locally on your machine — not both**. Running both would overwrite each other's snapshots and post duplicate summaries.

## Step 6: Monitor Execution

- Go to **Actions** tab to see past runs
- Click on a workflow run to see logs
- Look for "Run bot (execute once and exit)" to see whether the summary was posted
- Look for "Persist bot state" to confirm the daily snapshot was committed back

## Troubleshooting

- **Why isn't GitHub's own `schedule` cron used?** This repo's workflow file was renamed/deleted several times (Sep 2026), which caused GitHub to silently drop the schedule registration: the repo had **0 scheduled runs ever**, even after pushing changes to re-register and after creating a brand-new workflow file. GitHub also makes no guarantee that scheduled workflows run on time (delays of 10+ minutes or more, occasionally skipped entirely). The external dispatcher below is reliable because `workflow_dispatch` is queued immediately.
- **The bot never runs at 08:20 UTC?** Check, in order: ① cron-job.org → your job → **Logs/History** (did it fire? status 204?), ② the fine-grained PAT hasn't expired or been revoked (401 = bad token) and has **Actions: Read and write** permission on this repo (403/422 otherwise), ③ click **Execute** on the cron-job.org job as a live test.
- **The workflow commits to the repo but does not trigger new runs?** That is expected since September 2023: pushes made with `GITHUB_TOKEN` do not create new workflow runs. The external dispatcher is unaffected.
- **API errors?** Check the workflow logs under the failed run.
- **Bot never posts because the Riot dev key expired?** Development keys expire every 24h; renew it in **Settings → Secrets**.

---

## Important Notes

⚠️ **GitHub Actions has limitations for Discord bots:**
- Jobs are ephemeral (no persistent process), so the bot starts, runs once, and exits
- This is perfect for your use case: you only need to post the summary once per day
- Memory (LP snapshots + last-check times) survives because `lol_daily.sqlite3` is committed back to the repository after every run
- Since the workflow commits every day, the repository never goes inactive, which also prevents GitHub from pausing scheduled workflows after 60 days without activity

The bot will:
1. Start
2. Connect to Discord
3. Fetch player stats
4. Post the summary to your channel
5. Save its state and exit

If in the future you want the bot to stay online 24/7 (for commands, real-time updates, etc.), consider moving to a service like **Railway**, **Render**, or **Heroku** — but that would cost money, whereas GitHub Actions remains free.

---

**That's it!** Your bot will now run completely in the cloud, no machine required. ☁️

---

**That's it!** Your bot will now run completely in the cloud, no machine required. ☁️
