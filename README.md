# LoL Daily Discord Bot

A free-to-run Discord bot that posts a daily League of Legends summary for five Riot IDs.

## What it reports

- Games from the previous local calendar day
- Champion, KDA, win/loss, queue, and duration
- Ranked LP change since the previous successful daily check
- Current rank and LP

Riot's public API does not provide historical LP per match. The bot therefore stores the ranked LP returned at each daily run and compares it with the previous stored snapshot. The first run establishes a baseline and reports `LP baseline`.

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

## Free hosting

You can run this locally at no cost. Free hosting providers often sleep or limit background workers, which can make a daily scheduler unreliable. A small always-on machine, such as an existing computer or Raspberry Pi, is the most dependable free option.
