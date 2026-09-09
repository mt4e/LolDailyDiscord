from __future__ import annotations

import json
import logging
import os
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
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

    async def games_for_day(self, puuid: str, day: date, local_timezone: ZoneInfo) -> list[GameSummary]:
        start = datetime.combine(day, time.min, tzinfo=local_timezone).astimezone(timezone.utc)
        end = start + timedelta(days=1)
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
        yesterday = datetime.now(self.timezone).date() - timedelta(days=1)
        lines = [f"**League summary for {yesterday.isoformat()}**"]
        async with RiotClient(required_env("RIOT_API_KEY"), required_env("RIOT_PLATFORM"), required_env("RIOT_REGION")) as riot:
            for player in self.players:
                try:
                    account = await riot.account(player)
                    snapshot = await riot.ranked_snapshot(account["puuid"])
                    games = await riot.games_for_day(account["puuid"], yesterday, self.timezone)
                    lines.append(format_player(player, games, snapshot, self.database.previous_snapshot(player)))
                    if snapshot:
                        self.database.save_snapshot(player, snapshot)
                except (RiotApiError, KeyError, StopIteration) as error:
                    logger.exception("Could not load %s#%s", player.name, player.tag)
                    lines.append(f"**{player.name}#{player.tag}**: unavailable ({error})")
        await channel.send("\n\n".join(lines))


def format_player(
    player: Player,
    games: list[GameSummary],
    current: RankedSnapshot | None,
    previous: RankedSnapshot | None,
) -> str:
    header = f"**{player.name}#{player.tag}**: {len(games)} game(s)"
    if current is None:
        lp_line = "Ranked: unranked"
    else:
        rank = f"{current.tier.title()} {current.rank} ({current.lp} LP)"
        if previous is None:
            lp_line = f"Ranked: {rank} | LP baseline"
        else:
            delta = current.lp - previous.lp
            lp_line = f"Ranked: {rank} | LP {'+' if delta >= 0 else ''}{delta}"
    if not games:
        return f"{header}\n{lp_line}\nNo games found."
    game_lines = [
        f"{'W' if game.won else 'L'} {game.champion} {game.kills}/{game.deaths}/{game.assists} | {game.queue} | {game.duration_minutes}m"
        for game in games
    ]
    return f"{header}\n{lp_line}\n" + "\n".join(game_lines)


if __name__ == "__main__":
    bot = DailyBot()
    bot.run(required_env("DISCORD_TOKEN"))
