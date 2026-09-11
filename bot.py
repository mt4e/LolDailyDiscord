from __future__ import annotations

import json
import logging
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from urllib.parse import quote
from zoneinfo import ZoneInfo

import aiohttp
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("lol-daily-bot")


@dataclass(frozen=True)
class Player:
    name: str
    tag: str


@dataclass(frozen=True)
class RankedSnapshot:
    tier: str
    rank: str
    lp: int


@dataclass(frozen=True)
class GameSummary:
    champion: str
    kills: int
    deaths: int
    assists: int
    won: bool
    queue: str
    duration_minutes: int


TIER_ORDER = {
    "IRON": 0,
    "BRONZE": 1,
    "SILVER": 2,
    "GOLD": 3,
    "PLATINUM": 4,
    "EMERALD": 5,
    "DIAMOND": 6,
    "MASTER": 7,
    "GRANDMASTER": 8,
    "CHALLENGER": 9,
}

DIVISION_ORDER = {"IV": 0, "III": 1, "II": 2, "I": 3}

ANSI_RESET = "\u001b[0m"

# Fixed text color per player, aligned with the order of PLAYERS_JSON.
# Bright ANSI palette available on Discord: red, green, yellow, blue, magenta, cyan.
PLAYER_COLORS = ["1;31", "1;32", "1;33", "1;34", "1;35", "1;36"]

# LoL-like colors for ranked tiers (limited to Discord's ANSI palette).
TIER_ANSI = {
    "IRON": "90",
    "BRONZE": "33",
    "SILVER": "1;37",
    "GOLD": "1;33",
    "PLATINUM": "36",
    "EMERALD": "1;32",
    "DIAMOND": "1;34",
    "MASTER": "1;35",
    "GRANDMASTER": "1;31",
    "CHALLENGER": "1;31",
}

# Colors for the embed accent bar, close to the in-client tier colors.
TIER_EMBED_COLOR = {
    "IRON": 0x51484A,
    "BRONZE": 0xCD7F32,
    "SILVER": 0x8E8E93,
    "GOLD": 0xC9A227,
    "PLATINUM": 0x27AAE1,
    "EMERALD": 0x12B981,
    "DIAMOND": 0xB785FC,
    "MASTER": 0xC937D0,
    "GRANDMASTER": 0xE13C3C,
    "CHALLENGER": 0xE13C3C,
}

UNRANKED_EMBED_COLOR = 0x5865F2


def ansi(style: str, text: str) -> str:
    """Return text wrapped in ANSI codes so it renders colored in ```ansi``` blocks."""
    return f"\u001b[{style}m{text}{ANSI_RESET}"


def tier_ansi(tier: str) -> str:
    return TIER_ANSI.get(tier.upper(), "37")


def absolute_lp(snapshot: RankedSnapshot) -> int:
    """Map a tier/division/LP snapshot onto a continuous LP scale.

    Each tier spans 400 LP (four divisions of 100), so promotions and
    demotions across divisions are reflected in the difference. For example
    Gold II (13 LP) -> 1413 and Gold III (88 LP) -> 1388, a delta of -25.
    """
    tier = snapshot.tier.upper()
    division = DIVISION_ORDER.get(snapshot.rank.upper(), 0)  # Master+ has no division
    return TIER_ORDER.get(tier, 0) * 400 + division * 100 + snapshot.lp


class RiotApiError(Exception):
    pass


class RiotClient:
    # Hardcoded summoner IDs for testing (when API doesn't return them)
    SUMMONER_ID_MAP = {}
    
    def __init__(self, api_key: str, platform: str, region: str) -> None:
        self.api_key = api_key
        self.platform = platform.lower()
        self.region = region.lower()
        self.session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> "RiotClient":
        self.session = aiohttp.ClientSession(headers={"X-Riot-Token": self.api_key})
        return self

    async def __aexit__(self, *_: object) -> None:
        if self.session:
            await self.session.close()

    async def get(self, base_url: str, path: str, **params: object) -> object:
        if self.session is None:
            raise RuntimeError("RiotClient must be used as an async context manager")
        url = f"{base_url}{path}"
        async with self.session.get(url, params=params) as response:
            if response.status != 200:
                body = await response.text()
                raise RiotApiError(f"{response.status} from {path}: {body[:200]}")
            return await response.json()

    async def account(self, player: Player) -> dict:
        return await self.get(
            f"https://{self.region}.api.riotgames.com",
            f"/riot/account/v1/accounts/by-riot-id/{player.name}/{player.tag}",
        )

    async def get_summoner_id(self, puuid: str, player: Player = None) -> str | None:
        """Try to get summoner ID from PUUID using multiple API versions.
        Falls back to hardcoded summoner IDs for known players."""
        logger.debug("Getting summoner ID for player: %s", player)
        # Try v4 endpoint
        try:
            summoner = await self.get(
                f"https://{self.platform}.api.riotgames.com",
                f"/lol/summoner/v4/summoners/by-puuid/{puuid}",
            )
            if summoner.get("id"):
                return summoner["id"]
        except RiotApiError:
            pass
        
        # Try v1 endpoint as fallback
        try:
            summoner = await self.get(
                f"https://{self.platform}.api.riotgames.com",
                f"/lol/summoner/v1/summoners/by-puuid/{puuid}",
            )
            if summoner.get("id"):
                return summoner["id"]
        except RiotApiError:
            pass
        
        # Use hardcoded summoner ID if available for this player
        if player:
            player_key = f"{player.name}#{player.tag}"
            if player_key in self.SUMMONER_ID_MAP:
                summoner_id = self.SUMMONER_ID_MAP[player_key]
                logger.info("Using hardcoded summoner ID for %s: %s", player_key, summoner_id)
                return summoner_id
        
        return None

    async def ranked_snapshot(self, puuid: str) -> RankedSnapshot | None:
        if not puuid:
            logger.debug("No PUUID provided, returning None")
            return None
        try:
            logger.debug("Fetching ranked snapshot for PUUID: %s", puuid)
            entries = await self.get(
                f"https://{self.platform}.api.riotgames.com",
                f"/lol/league/v4/entries/by-puuid/{puuid}",
            )
            logger.debug("Got entries: %s", entries)
            solo = next((entry for entry in entries if entry["queueType"] == "RANKED_SOLO_5x5"), None)
            if solo is None:
                logger.debug("No RANKED_SOLO_5x5 entry found for PUUID: %s", puuid)
                return None
            logger.info("Found ranked snapshot: %s %s %s LP", solo["tier"], solo["rank"], solo["leaguePoints"])
            return RankedSnapshot(solo["tier"], solo["rank"], solo["leaguePoints"])
        except (RiotApiError, StopIteration) as e:
            logger.error("Failed to fetch ranked snapshot for PUUID %s: %s", puuid, e)
            return None

    async def games_between(self, puuid: str, start: datetime, end: datetime) -> list[GameSummary]:
        """List games played between two UTC-aware datetimes."""
        matches = await self.get(
            f"https://{self.region}.api.riotgames.com",
            f"/lol/match/v5/matches/by-puuid/{puuid}/ids",
            startTime=int(start.timestamp()),
            endTime=int(end.timestamp()),
            start=0,
            count=100,
        )
        summaries: list[GameSummary] = []
        for match_id in matches:
            details = await self.get(
                f"https://{self.region}.api.riotgames.com",
                f"/lol/match/v5/matches/{match_id}",
            )
            participant = next(
                participant
                for participant in details["info"]["participants"]
                if participant["puuid"] == puuid
            )
            summaries.append(
                GameSummary(
                    champion=participant["championName"],
                    kills=participant["kills"],
                    deaths=participant["deaths"],
                    assists=participant["assists"],
                    won=participant["win"],
                    queue=queue_name(details["info"]["queueId"]),
                    duration_minutes=round(details["info"]["gameDuration"] / 60),
                )
            )
        return summaries


def queue_name(queue_id: int) -> str:
    return {420: "Ranked Solo", 440: "Ranked Flex", 450: "ARAM", 490: "Swiftplay"}.get(
        queue_id, f"Queue {queue_id}"
    )


def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def load_players() -> list[Player]:
    try:
        players_json_str = required_env("PLAYERS_JSON")
        logger.info("PLAYERS_JSON raw value: %s", players_json_str)
        raw_players = json.loads(players_json_str)
        logger.info("Parsed PLAYERS_JSON: %s", raw_players)
        players = [Player(item["name"], item["tag"]) for item in raw_players]
        logger.info("Loaded %d players: %s", len(players), [f"{p.name}#{p.tag}" for p in players])
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        logger.error("Failed to load players: %s", error)
        raise RuntimeError("PLAYERS_JSON must be a JSON array of objects with name and tag") from error
    if len(players) != 6:
        raise RuntimeError("PLAYERS_JSON must contain exactly six players")
    return players


class Database:
    def __init__(self, path: str = "lol_daily.sqlite3") -> None:
        self.connection = sqlite3.connect(path)
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS lp_snapshots (player TEXT PRIMARY KEY, tier TEXT, rank TEXT, lp INTEGER, checked_at TEXT NOT NULL)"
        )
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS last_checks (player TEXT PRIMARY KEY, checked_at TEXT NOT NULL)"
        )
        self.connection.commit()

    def previous_snapshot(self, player: Player) -> RankedSnapshot | None:
        row = self.connection.execute(
            "SELECT tier, rank, lp FROM lp_snapshots WHERE player = ?", (f"{player.name}#{player.tag}",)
        ).fetchone()
        return RankedSnapshot(*row) if row else None

    def save_snapshot(self, player: Player, snapshot: RankedSnapshot) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO lp_snapshots VALUES (?, ?, ?, ?, ?)",
            (f"{player.name}#{player.tag}", snapshot.tier, snapshot.rank, snapshot.lp, datetime.now(timezone.utc).isoformat()),
        )
        self.connection.commit()

    def last_check(self, player: Player) -> datetime | None:
        row = self.connection.execute(
            "SELECT checked_at FROM last_checks WHERE player = ?", (f"{player.name}#{player.tag}",)
        ).fetchone()
        return datetime.fromisoformat(row[0]) if row else None

    def save_check(self, player: Player, checked_at: datetime) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO last_checks VALUES (?, ?)",
            (f"{player.name}#{player.tag}", checked_at.isoformat()),
        )
        self.connection.commit()


class DailyBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.none()
        intents.guilds = True
        super().__init__(command_prefix="!", intents=intents)
        self.players = load_players()
        self.channel_id = int(required_env("DISCORD_CHANNEL_ID"))
        self.timezone = ZoneInfo(os.getenv("TIMEZONE", "UTC"))
        self.run_time = time(int(os.getenv("RUN_HOUR", "9")), int(os.getenv("RUN_MINUTE", "0")))
        self.database = Database()
        self.immediate_run = os.getenv("IMMEDIATE_RUN", "false").lower() == "true"  # For GitHub Actions
        self.daily_loop.change_interval(time=self.run_time.replace(tzinfo=self.timezone))

    async def on_ready(self) -> None:
        logger.info("Logged in as %s", self.user)
        if self.immediate_run:
            logger.info("IMMEDIATE_RUN mode: executing immediately")
            await self.post_daily_summary()
            await self.close()
        elif not self.daily_loop.is_running():
            self.daily_loop.start()

    @tasks.loop(time=time(9, 0))
    async def daily_loop(self) -> None:
        await self.post_daily_summary()

    @daily_loop.before_loop
    async def before_daily_loop(self) -> None:
        await self.wait_until_ready()

    async def post_daily_summary(self) -> None:
        channel = self.get_channel(self.channel_id)
        if not isinstance(channel, discord.TextChannel):
            logger.error("Channel %s was not found or is not a text channel", self.channel_id)
            return
        now = datetime.now(timezone.utc)
        yesterday = datetime.now(self.timezone).date() - timedelta(days=1)
        embeds: list[discord.Embed] = []
        records: list[tuple[str, int, int]] = []
        windows: list[datetime] = []
        async with RiotClient(required_env("RIOT_API_KEY"), required_env("RIOT_PLATFORM"), required_env("RIOT_REGION")) as riot:
            for index, player in enumerate(self.players):
                try:
                    account = await riot.account(player)
                    puuid = account["puuid"]
                    snapshot = await riot.ranked_snapshot(puuid)
                    last_run = self.database.last_check(player)
                    if last_run is None:
                        # First run: report the whole previous local calendar day.
                        start = datetime.combine(yesterday, time.min, tzinfo=self.timezone)
                    else:
                        # Later runs: everything since the last successful run,
                        # so games played after midnight are not missed.
                        start = last_run
                    windows.append(start)
                    games = await riot.games_between(puuid, start, now)
                    embeds.append(player_embed(player, games, snapshot, self.database.previous_snapshot(player), index))
                    wins = sum(1 for game in games if game.won)
                    records.append((f"{player.name}#{player.tag}", wins, len(games) - wins))
                    if snapshot:
                        self.database.save_snapshot(player, snapshot)
                    self.database.save_check(player, now)
                except (RiotApiError, KeyError, StopIteration) as error:
                    logger.exception("Could not load %s#%s", player.name, player.tag)
                    embeds.append(error_embed(player, error, index))
        if windows:
            header = f"**League summary since {min(windows).astimezone(self.timezone):%Y-%m-%d %H:%M} ({self.timezone})**"
        else:
            header = f"**League summary for {yesterday.isoformat()}**"
        embeds.insert(0, summary_embed(header, records))
        await channel.send(embeds=embeds)


def record_and_streak(games: list[GameSummary]) -> tuple[int, int, int]:
    """Return (wins, losses, current_streak).

    Streak is positive for consecutive wins and negative for consecutive
    losses, counting from the most recent game (first in the list).
    """
    wins = sum(1 for game in games if game.won)
    losses = len(games) - wins
    streak = 0
    for game in reversed(games):
        delta = 1 if game.won else -1
        if streak * delta >= 0:
            streak += delta
        else:
            break
    return wins, losses, streak


def win_loss_indicator(won: bool) -> str:
    return ansi("1;34" if won else "1;31", "W" if won else "L")


def format_game_line(game: GameSummary) -> str:
    indicator = win_loss_indicator(game.won)
    return f"{indicator} {game.champion} {game.kills}/{game.deaths}/{game.assists} | {game.queue} | {game.duration_minutes}m"


def format_rank_line(current: RankedSnapshot | None, previous: RankedSnapshot | None) -> str:
    if current is None:
        return "Ranked: unranked"
    rank = ansi(tier_ansi(current.tier), f"{current.tier.title()} {current.rank} ({current.lp} LP)")
    if previous is None:
        return f"Ranked: {rank} | LP baseline"
    delta = absolute_lp(current) - absolute_lp(previous)
    if delta > 0:
        lp = f"LP {delta:+d} ⬆️"
    elif delta < 0:
        lp = f"LP {delta:+d} ⬇️"
    else:
        lp = "LP ±0 ➖"
    return f"Ranked: {rank} | {lp}"


def champion_thumbnail_url(champion: str) -> str:
    """Version-free loading-screen art URL for a champion on Data Dragon."""
    return f"https://ddragon.leagueoflegends.com/cdn/img/champion/loading/{quote(champion, safe='')}_0.jpg"


def player_embed(
    player: Player,
    games: list[GameSummary],
    current: RankedSnapshot | None,
    previous: RankedSnapshot | None,
    color_index: int,
) -> discord.Embed:
    pseudo_color = PLAYER_COLORS[color_index % len(PLAYER_COLORS)]
    wins, losses, streak = record_and_streak(games)

    header = f"{ansi(pseudo_color, f'{player.name}#{player.tag}')} · {len(games)} game(s)"
    if games:
        header += f" · {wins}W {losses}L ({round(wins / len(games) * 100)}%)"
        if streak >= 2:
            header += f" 🔥 {streak}W streak"
        elif streak <= -2:
            header += f" 🧊 {-streak}L streak"

    embed_color = TIER_EMBED_COLOR.get(current.tier.upper(), UNRANKED_EMBED_COLOR) if current else UNRANKED_EMBED_COLOR
    embed = discord.Embed(
        title=f"{player.name}#{player.tag}",
        description=f"```ansi\n{header}\n```",
        color=embed_color,
    )
    embed.add_field(name="Rank", value=f"```ansi\n{format_rank_line(current, previous)}\n```", inline=False)
    if games:
        game_block = "\n".join(format_game_line(game) for game in games)
        if len(game_block) > 1000:
            game_block = game_block[:995] + "\n…"
        embed.add_field(name="Games", value=f"```ansi\n{game_block}\n```", inline=False)
        embed.set_thumbnail(url=champion_thumbnail_url(games[0].champion))
    return embed


def error_embed(player: Player, error: Exception, color_index: int) -> discord.Embed:
    pseudo_color = PLAYER_COLORS[color_index % len(PLAYER_COLORS)]
    pseudo = ansi(pseudo_color, f"{player.name}#{player.tag}")
    return discord.Embed(
        title=f"{player.name}#{player.tag}",
        description=f"```ansi\n{pseudo}\n```\nUnavailable ({error})",
        color=0x36393F,
    )


def summary_embed(header: str, records: list[tuple[str, int, int]]) -> discord.Embed:
    embed = discord.Embed(title="📊 Daily League Recap", description=header, color=0x5865F2)
    for name, wins, losses in records:
        total = wins + losses
        pct = round(wins / total * 100) if total else 0
        embed.add_field(name=name, value=f"{wins}W {losses}L ({pct}%)", inline=True)
    return embed


if __name__ == "__main__":
    bot = DailyBot()
    bot.run(required_env("DISCORD_TOKEN"))
