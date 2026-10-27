"""Настройки из .env и окружения."""
import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env(ROOT / ".env")


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


@dataclass
class Prices:
    spread3: int = field(default_factory=lambda: _int("PRICE_SPREAD3", 50))
    spread5: int = field(default_factory=lambda: _int("PRICE_SPREAD5", 100))
    followups: int = field(default_factory=lambda: _int("PRICE_FOLLOWUPS", 20))
    bundle3: int = field(default_factory=lambda: _int("PRICE_BUNDLE3", 120))
    gift: int = field(default_factory=lambda: _int("PRICE_GIFT", 50))
    full: int = field(default_factory=lambda: _int("PRICE_FULL", 350))
    full_returning: int = field(default_factory=lambda: _int("PRICE_FULL_RETURNING", 250))


@dataclass
class Config:
    bot_token: str = field(default_factory=lambda: os.environ.get("BOT_TOKEN", ""))
    admin_ids: list = field(default_factory=lambda: [
        int(x) for x in os.environ.get("ADMIN_CHAT_IDS", "").replace(" ", "").split(",") if x
    ])
    persona: str = field(default_factory=lambda: os.environ.get("PERSONA_NAME", "Рада"))
    llm_provider: str = field(default_factory=lambda: os.environ.get("LLM_PROVIDER", "stub"))
    gemini_key: str = field(default_factory=lambda: os.environ.get("GEMINI_API_KEY", ""))
    gemini_model: str = field(default_factory=lambda: os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"))
    anthropic_key: str = field(default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY", ""))
    anthropic_model: str = field(default_factory=lambda: os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5"))
    telegraph_token: str = field(default_factory=lambda: os.environ.get("TELEGRAPH_TOKEN", ""))
    db_path: str = field(default_factory=lambda: os.environ.get("DB_PATH", str(ROOT / "state" / "rada.sqlite3")))
    cards_dir: str = field(default_factory=lambda: os.environ.get("CARDS_DIR", str(ROOT / "assets" / "cards")))
    video_note_id: str = field(default_factory=lambda: os.environ.get("VIDEO_NOTE_FILE_ID", ""))
    tz_offset_hours: int = field(default_factory=lambda: _int("TZ_OFFSET_HOURS", 3))
    morning_hour: int = field(default_factory=lambda: _int("MORNING_HOUR", 9))
    followup_questions: int = field(default_factory=lambda: _int("FOLLOWUPS_PER_SPREAD", 3))
    prices: Prices = field(default_factory=Prices)
