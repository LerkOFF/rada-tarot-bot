"""Картинки: карта (прямая и перевёрнутая), коллаж расклада, карточка аркана."""
import io
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from .deck import ROMAN, Card

CARD_W, CARD_H = 300, 520
SERIF = [
    "/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
    "/System/Library/Fonts/Supplemental/Georgia.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
]
SANS = [
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def font(paths: list, size: int) -> ImageFont.FreeTypeFont:
    custom = os.environ.get("FONT_PATH")
    for p in ([custom] if custom else []) + paths:
        if p and Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def _placeholder(card: Card) -> Image.Image:
    img = Image.new("RGB", (CARD_W, CARD_H), "#1c1830")
    d = ImageDraw.Draw(img)
    d.rectangle((8, 8, CARD_W - 9, CARD_H - 9), outline="#b8975a", width=3)
    mark = ROMAN[int(card.slug[1:])] if card.is_major else card.slug[1:].lstrip("0")
    d.text((CARD_W // 2, 70), mark, font=font(SERIF, 44), fill="#e8d9b0", anchor="mm")
    d.text((CARD_W // 2, CARD_H // 2), card.name, font=font(SERIF, 28), fill="#e8d9b0", anchor="mm")
    return img


def card_image(card: Card, cards_dir) -> Image.Image:
    """cards_dir - каталог или список каталогов: первый найденный файл главнее."""
    dirs = [cards_dir] if isinstance(cards_dir, (str, Path)) else cards_dir
    path = next((p for p in (Path(d) / f"{card.slug}.jpg" for d in dirs) if p.exists()), None)
    if path:
        img = ImageOps.fit(Image.open(path).convert("RGB"), (CARD_W, CARD_H))
    else:
        img = _placeholder(card)
    return img.rotate(180) if card.reversed else img


def to_bytes(img: Image.Image, fmt: str = "JPEG") -> bytes:
    buf = io.BytesIO()
    img.save(buf, fmt, quality=90) if fmt == "JPEG" else img.save(buf, fmt)
    return buf.getvalue()


def day_card(card: Card, cards_dir: str) -> bytes:
    """Карта на размытом фоне из неё же, как в подписи «карта дня»."""
    face = card_image(card, cards_dir)
    bg = ImageOps.fit(face, (900, 700)).filter(ImageFilter.GaussianBlur(30))
    bg = Image.blend(bg, Image.new("RGB", bg.size, "#2a2438"), 0.35)
    h = 640
    face = face.resize((int(CARD_W * h / CARD_H), h))
    bg.paste(face, ((900 - face.width) // 2, (700 - h) // 2))
    return to_bytes(bg)


def collage(cards: list, cards_dir: str) -> bytes:
    """Три карты: одна большая слева, две малые справа. Пять: ряд из пяти."""
    faces = [card_image(c, cards_dir) for c in cards]
    if len(faces) == 3:
        big = faces[0].resize((420, 728))
        small = [f.resize((210, 364)) for f in faces[1:]]
        canvas = Image.new("RGB", (420 + 210 + 24, 728), "#f4efe6")
        canvas.paste(big, (0, 0))
        canvas.paste(small[0], (432, 0))
        canvas.paste(small[1], (432, 364))
        return to_bytes(canvas)
    w, h = 240, 416
    canvas = Image.new("RGB", (w * len(faces) + 12 * (len(faces) - 1), h), "#f4efe6")
    for i, f in enumerate(faces):
        canvas.paste(f.resize((w, h)), (i * (w + 12), 0))
    return to_bytes(canvas)


def _wrap(draw, text, fnt, width):
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=fnt) <= width:
            line = trial
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def arcana_card(card: Card, data: dict, bot_username: str, cards_dir: str) -> bytes:
    """Карточка для шеринга: тёмный фон, имя аркана, три строки, цитата, ник бота."""
    W, H = 1080, 1350
    face = card_image(Card(card.slug, card.name), cards_dir)
    bg = ImageOps.fit(face, (W, H)).filter(ImageFilter.GaussianBlur(40))
    img = Image.blend(bg, Image.new("RGB", (W, H), "#0d0c14"), 0.82)
    d = ImageDraw.Draw(img)
    gold, ivory, dim = "#c9a96a", "#f1e8d2", "#a79f8f"
    d.line((80, 120, 130, 120), fill=gold, width=4)
    d.text((80, 150), "Твой аркан судьбы -", font=font(SANS, 34), fill=dim)
    d.text((80, 215), card.name, font=font(SERIF, 104), fill=ivory)
    roman = ROMAN[int(card.slug[1:])]
    d.text((80, 345), f"АРКАН {roman}", font=font(SANS, 26), fill=gold)
    pic = face.resize((300, 520))
    img.paste(pic, (W - 80 - 300, 150))
    y = 420
    for line in _wrap(d, data.get("epigraph", ""), font(SERIF, 36), 560):
        d.text((80, y), line, font=font(SERIF, 36), fill=ivory)
        y += 52
    y = max(y + 60, 720)
    for label, key in (("СИЛА", "power"), ("СЛЕПАЯ ЗОНА", "blind"), ("РЕШЕНИЯ", "decision")):
        d.text((80, y), label, font=font(SANS, 24), fill=gold)
        fy = y
        for line in _wrap(d, data.get(key, ""), font(SANS, 32), 640):
            d.text((380, fy - 4), line, font=font(SANS, 32), fill=ivory)
            fy += 44
        y = max(fy, y + 60) + 40
    d.line((80, y + 10, W - 80, y + 10), fill="#3a3548", width=2)
    y += 50
    for line in _wrap(d, f"«{data.get('quote', '')}»", font(SERIF, 38), W - 160):
        d.text((80, y), line, font=font(SERIF, 38), fill=ivory)
        y += 54
    d.text((80, H - 100), f"@{bot_username}", font=font(SANS, 30), fill=dim)
    d.text((W - 80, H - 100), card.name.upper(), font=font(SANS, 26), fill=dim, anchor="ra")
    return to_bytes(img, "PNG")
