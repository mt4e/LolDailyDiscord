# LoL Daily Discord Bot

A free-to-run Discord bot that posts a daily League of Legends summary for five Riot IDs.

## What it reports

- Games played since the previous daily run (the first run reports the whole previous local calendar day, so matches played after midnight are not missed)
- Champion, KDA, win/loss, queue, and duration
- Ranked LP change since the previous successful daily check
- Current rank and LP

Riot's public API does not provide historical LP per match. The bot therefore stores the ranked LP returned at each daily run and compares it with the previous stored snapshot. The first run establishes a baseline and reports `LP baseline`. The comparison is division-aware: a demotion from Gold II (13 LP) to Gold III (88 LP) is reported as -25 LP, and promotions are handled the same way.

## Setup

1. Create a Discord application and bot at the Discord Developer Portal. Enable the `Message Content Intent` only if you later add message commands; this bot does not need it.
2. Create a Riot Games API key at the Riot Developer Portal. Development keys normally expire every 24 hours and must be renewed; a production key is still free to use but requires Riot approval.
3. Invite the bot with the `bot` scope and the `View Channel` and `Send Messages` permissions for the target channel.
4. Install Python 3.11 or newer.
5. Create a virtual environment and install dependencies:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

6. Copy `.env.example` to `.env` and fill in the values. `DISCORD_CHANNEL_ID` is the numeric channel ID. Set `RIOT_PLATFORM` and `RIOT_REGION` for the players' server.
7. Start the bot:

```powershell
python bot.py
```

The bot runs once when it starts, then daily at `RUN_HOUR:RUN_MINUTE` in `TIMEZONE`. If you do not want the startup report, remove the `await post_daily_summary()` call in `on_ready`.

## Riot routing examples

- EUW: `RIOT_PLATFORM=EUW1`, `RIOT_REGION=europe`
- EUNE: `RIOT_PLATFORM=EUN1`, `RIOT_REGION=europe`
- NA: `RIOT_PLATFORM=NA1`, `RIOT_REGION=americas`
- KR: `RIOT_PLATFORM=KR`, `RIOT_REGION=asia`

## Free hosting without a machine

The recommended way to run this bot for free with no always-on machine is **GitHub Actions** (see `GITHUB_ACTIONS_SETUP.md`):

- The workflow runs daily at **08:20 UTC** (09:20 Europe/Paris in winter, 10:20 in summer) and posts the summary to your channel.
- The bot's memory (LP snapshots + last-check times) is kept in `lol_daily.sqlite3`, which the workflow commits back to the repository after every run. That is what makes the LP diff consistent between runs.
- Because the workflow commits to the repo every day, the repository never becomes inactive, so GitHub never pauses the scheduled workflow.

> ⚠️ Run the bot **either locally or on GitHub Actions, not both**: the state file lives inside the git checkout, so a local run and a cloud run would overwrite each other's snapshots and post duplicate summaries.

Running the bot locally on a small always-on machine (Raspberry Pi, an old PC) still works and is the most dependable option if you prefer it. Free PaaS providers often sleep or limit background workers, which makes daily schedulers unreliable.

