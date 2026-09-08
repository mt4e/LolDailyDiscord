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

## Step 2: Add GitHub Secrets

Your `.env` variables need to be added as GitHub Secrets so they're available to GitHub Actions but stay private.

1. Go to your GitHub repo → **Settings** → **Secrets and variables** → **Actions**
2. Click **New repository secret**
3. Add each of these secrets:

| Secret Name | Value |
|------------|-------|
| `DISCORD_TOKEN` | Your bot token from `.env` |
| `RIOT_API_KEY` | Your Riot API key from `.env` |
| `DISCORD_CHANNEL_ID` | Your channel ID from `.env` |
| `RIOT_PLATFORM` | `EUW1` (from `.env`) |
| `RIOT_REGION` | `europe` (from `.env`) |
| `TIMEZONE` | `Europe/Paris` (from `.env`) |
| `RUN_HOUR` | `22` (from `.env`) |
| `RUN_MINUTE` | `24` (from `.env`) |
| `PLAYERS_JSON` | Your players JSON array (from `.env`) |

## Step 3: Verify GitHub Actions

1. Go to your repo → **Actions** tab
2. You should see a workflow called "Daily LoL Summary Bot"
3. It will run automatically at **22:24 UTC** every day
4. You can also click **Run workflow** → **Run workflow** to test it manually

## Step 4: Monitor Execution

- Go to **Actions** tab to see past runs
- Click on a workflow run to see logs
- Look for "Run bot (execute once and exit)" step to see the output

## Troubleshooting

- **Bot doesn't run at scheduled time?** GitHub Actions might have a slight delay. Check the Actions tab.
- **"Secrets not found" error?** Make sure secret names match exactly (case-sensitive)
- **API errors?** Check the workflow logs under the failed run

---

## Important Notes

⚠️ **GitHub Actions has limitations for Discord bots:**
- Workflows timeout after 6 hours of inactivity
- Jobs are ephemeral (don't keep persistent connections)
- Your bot will start, run the daily summary, then exit

This works perfectly for your use case since you only need to post the summary once per day at a scheduled time. The bot will:
1. Start
2. Connect to Discord
3. Fetch player stats
4. Post the summary to your channel
5. Exit

If in the future you want the bot to stay online 24/7 (for commands, real-time updates, etc.), consider moving to a service like **Railway**, **Render**, or **Heroku**.

---

**That's it!** Your bot will now run completely in the cloud, no machine required. ☁️
