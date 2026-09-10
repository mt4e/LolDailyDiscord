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

`RUN_HOUR` / `RUN_MINUTE` are no longer used: the GitHub workflow schedules the run itself (08:20 UTC) and always executes once via `IMMEDIATE_RUN`.

## Step 3: Verify GitHub Actions

1. Go to your repo → **Actions** tab
2. You should see a workflow called "Daily LoL Summary Bot"
3. It will run automatically at **08:20 UTC** every day (09:20 Europe/Paris in winter, 10:20 in summer)
4. You can also click **Run workflow** → **Run workflow** to test it manually

## Step 4: Persistent state (LP diff memory)

The bot stores its memory in `lol_daily.sqlite3` (LP snapshots + the date/time of each successful run). This file is tracked in git and is committed back to the repository by the workflow after every run, so the LP diff stays consistent day after day.

- ❗ The state file is shared: run the bot **either here on GitHub Actions or locally on your machine — not both**. Running both would overwrite each other's snapshots and post duplicate summaries.

## Step 5: Monitor Execution

- Go to **Actions** tab to see past runs
- Click on a workflow run to see logs
- Look for "Run bot (execute once and exit)" to see whether the summary was posted
- Look for "Persist bot state" to confirm the daily snapshot was committed back

## Troubleshooting

- **The manual "Run workflow" button works, but the schedule never fires on its own?** The usual cause is that the `schedule` was never re-registered on the default branch (a frequent side effect of renaming/deleting workflow files). Push a new commit that modifies `.github/workflows/daily-bot.yml` — GitHub re-registers the cron a few minutes after the push. Then check the workflow page: the "schedule" line under the workflow name should list the cron. If it still doesn't fire after 24h, check **Settings → Actions → General** (Actions must be enabled) and that the workflow file exists on the default branch (`main`).
- **The workflow commits to the repo but does not trigger new runs?** That is expected since September 2023: pushes made with `GITHUB_TOKEN` do not create new workflow runs. The daily cron still fires normally.
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
