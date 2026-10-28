"""Файлы, которые меняют из админки: видео-кружки, картинки карт, аватар бота.

Всё лежит в MEDIA_DIR. Кружки при первом запуске копируются туда из assets/video,
дальше источник правды - MEDIA_DIR. Картинка карты из MEDIA_DIR/cards главнее assets/cards.
"""
import asyncio
import re
import shutil
import time
from pathlib import Path

from .config import ROOT

SCENARIOS = [
    ("greeting", "Приветствие при первом /start"),
    ("card", "Карта дня"),
    ("yesno", "Ответ да/нет"),
    ("spread", "Перед раскладом (коллаж и счёт)"),
    ("paid", "После оплаты расклада"),
    ("arcana", "Мой аркан"),
    ("year", "Мой год"),
    ("compat", "Совместимость"),
    ("full", "Полный разбор"),
    ("followup", "Вопрос «сбылось?»"),
]
SCENARIO = dict(SCENARIOS)
SEED_VIDEO = ROOT / "assets" / "video"
MAX_VIDEO_SECONDS = 60


class Media:
    def __init__(self, media_dir: str, cards_dir: str):
        self.root = Path(media_dir)
        self.video = self.root / "video"
        self.cards = self.root / "cards"
        self.avatar = self.root / "avatar"
        self.base_cards = Path(cards_dir)

    def ensure(self):
        if not self.video.exists():
            self.video.mkdir(parents=True)
            for f in sorted(SEED_VIDEO.glob("*.mp4")):
                shutil.copy2(f, self.video / f.name)
        self.cards.mkdir(parents=True, exist_ok=True)
        self.avatar.mkdir(parents=True, exist_ok=True)
        return self

    # кружки
    def videos(self, scenario: str) -> list:
        pat = re.compile(rf"^{re.escape(scenario)}(_[\w-]+)?\.mp4$")
        if not self.video.exists():
            return []
        return sorted(p for p in self.video.iterdir() if pat.match(p.name))

    def video_path(self, name: str):
        """Путь к кружку по имени файла, только внутри каталога и только .mp4."""
        if not re.fullmatch(r"[\w-]+\.mp4", name):
            return None
        p = self.video / name
        return p if p.is_file() else None

    def new_video_name(self, scenario: str) -> str:
        return f"{scenario}_{time.strftime('%Y%m%d%H%M%S')}.mp4"

    # карты
    def card_dirs(self) -> list:
        return [str(self.cards), str(self.base_cards)]

    def card_file(self, slug: str):
        for d in (self.cards, self.base_cards):
            p = d / f"{slug}.jpg"
            if p.exists():
                return p
        return None

    def card_overridden(self, slug: str) -> bool:
        return (self.cards / f"{slug}.jpg").exists()

    # аватар
    def avatar_file(self):
        p = self.avatar / "current.jpg"
        return p if p.exists() else None


def ffmpeg() -> str:
    return shutil.which("ffmpeg") or ""


async def to_video_note(src: Path, dst: Path) -> str:
    """Любое видео в кружок: квадрат по центру 640x640, H.264 + AAC, до 60 секунд.
    Возвращает текст ошибки или пустую строку."""
    if not ffmpeg():
        if src.suffix.lower() != ".mp4":
            return "На сервере нет ffmpeg, поэтому принимаю только готовый квадратный .mp4."
        shutil.copy2(src, dst)
        return ""
    args = [
        ffmpeg(), "-y", "-v", "error", "-i", str(src), "-t", str(MAX_VIDEO_SECONDS),
        "-vf", "crop='min(iw,ih)':'min(iw,ih)',scale=640:640,setsar=1,fps=30",
        "-c:v", "libx264", "-profile:v", "main", "-pix_fmt", "yuv420p", "-preset", "veryfast", "-crf", "26",
        "-c:a", "aac", "-b:a", "96k", "-ac", "1", "-movflags", "+faststart", str(dst),
    ]
    proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE,
                                                stderr=asyncio.subprocess.PIPE)
    try:
        _, err = await asyncio.wait_for(proc.communicate(), timeout=180)
    except asyncio.TimeoutError:
        proc.kill()
        return "Видео слишком долго перекодируется, попробуй файл покороче."
    if proc.returncode != 0 or not dst.exists():
        dst.unlink(missing_ok=True)
        return "Не получилось перекодировать видео: " + err.decode(errors="ignore")[-300:]
    return ""
