"""Environment variables se configuration load karta hai. Secrets kabhi print nahi hote."""
import os
from dataclasses import dataclass


class ConfigError(Exception):
    pass


@dataclass
class Config:
    bot_token: str
    admin_ids: frozenset
    database_url: str
    port: int
    force_join_channel: str
    force_join_link: str
    bot_username: str = ""


def parse_admin_ids(raw: str) -> frozenset:
    ids = set()
    for part in raw.replace(" ", "").split(","):
        if not part:
            continue
        if not part.isdigit() or int(part) <= 0:
            raise ConfigError(
                "ADMIN_IDS mein sirf numeric Telegram IDs comma se alag karke likho (jaise 111,222)."
            )
        ids.add(int(part))
    if not ids:
        raise ConfigError("ADMIN_IDS khaali hai. Kam se kam ek admin ID daalo.")
    return frozenset(ids)


def load_config() -> Config:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise ConfigError("BOT_TOKEN environment variable set nahi hai.")
    db_url = os.getenv("DATABASE_URL", "").strip()
    if not db_url:
        raise ConfigError("DATABASE_URL environment variable set nahi hai.")
    raw_port = os.getenv("PORT", "10000").strip()
    if not raw_port.isdigit() or not (0 < int(raw_port) < 65536):
        raise ConfigError("PORT galat hai.")
    return Config(
        bot_token=token,
        admin_ids=parse_admin_ids(os.getenv("ADMIN_IDS", "")),
        database_url=db_url,
        port=int(raw_port),
        force_join_channel=os.getenv("FORCE_JOIN_CHANNEL", "@snnetworkop8").strip(),
        force_join_link=os.getenv(
            "FORCE_JOIN_LINK", "https://t.me/+E2b5VIy1AAtmOGI1"
        ).strip(),
    )
