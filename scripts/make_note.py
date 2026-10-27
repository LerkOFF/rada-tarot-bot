"""Собирает видео-кружок (640x640, mp4 H.264 + AAC) без лица: колода, переворот карты, свеча, искры, голос.
Пример: .venv/bin/python scripts/make_note.py --text "Здравствуй. Я Заря." --card m17 --out assets/notes/greeting_1.mp4
Нужны ffmpeg и пакеты edge-tts, numpy, pillow. Голос Microsoft Neural через edge-tts (интернет)."""
import argparse
import asyncio
import math
import random
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
S = 640
FPS = 25
GOLD = (201, 169, 106)
CW, CH = 168, 292  # размер карты


def ease(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def background():
    y, x = np.mgrid[0:S, 0:S].astype(np.float32)
    d = np.sqrt((x - S / 2) ** 2 + (y - S * 0.55) ** 2) / (S * 0.75)
    top = np.array([26, 15, 48], np.float32)
    bot = np.array([6, 4, 14], np.float32)
    k = np.clip(d, 0, 1)[..., None]
    img = top * (1 - k) + bot * k
    return Image.fromarray(img.astype(np.uint8)).convert("RGBA")


def rounded(img, r=12):
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, img.width - 1, img.height - 1), r, fill=255)
    out = img.convert("RGBA")
    out.putalpha(mask)
    return out


def card_back():
    img = Image.new("RGB", (CW, CH), (24, 20, 64))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((5, 5, CW - 6, CH - 6), 10, outline=GOLD, width=3)
    d.rounded_rectangle((14, 14, CW - 15, CH - 15), 7, outline=(120, 100, 150), width=1)
    cx, cy = CW // 2, CH // 2
    pts = []
    for i in range(16):
        r = 46 if i % 2 == 0 else 20
        a = math.pi * i / 8 - math.pi / 2
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    d.polygon(pts, outline=GOLD, fill=(40, 32, 92))
    d.ellipse((cx - 9, cy - 9, cx + 9, cy + 9), fill=GOLD)
    for i in range(8):
        a = math.pi * i / 4
        d.ellipse((cx + 70 * math.cos(a) - 3, cy + 70 * math.sin(a) - 3,
                   cx + 70 * math.cos(a) + 3, cy + 70 * math.sin(a) + 3), fill=GOLD)
    return rounded(img)


def card_face(slug):
    p = ROOT / "assets" / "cards" / f"{slug}.jpg"
    if p.exists():
        img = Image.open(p).convert("RGB").resize((CW, CH))
    else:
        img = Image.new("RGB", (CW, CH), (236, 226, 200))
    return rounded(img)


def glow(size, color, alpha):
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse((S / 2 - size, S / 2 - size, S / 2 + size, S / 2 + size),
                                  fill=color + (int(alpha),))
    return layer.filter(ImageFilter.GaussianBlur(size * 0.45))


class Scene:
    def __init__(self, duration, face_slug, seed=7):
        self.D = duration
        self.bg = background()
        self.back = card_back()
        self.face = card_face(face_slug)
        rnd = random.Random(seed)
        self.sparks = [(rnd.uniform(0, S), rnd.uniform(0, S), rnd.uniform(0.2, 1.0),
                        rnd.uniform(8, 26), rnd.uniform(0, 6.28)) for _ in range(46)]
        self.noise = [rnd.uniform(0, 6.28) for _ in range(4)]

    def place(self, canvas, img, cx, cy, angle=0.0, scale=1.0, alpha=1.0, xscale=1.0):
        w, h = max(2, int(img.width * scale * xscale)), max(2, int(img.height * scale))
        im = img.resize((w, h), Image.LANCZOS)
        if angle:
            im = im.rotate(angle, expand=True, resample=Image.BICUBIC)
        if alpha < 1:
            a = im.getchannel("A").point(lambda v: int(v * alpha))
            im.putalpha(a)
        canvas.alpha_composite(im, (int(cx - im.width / 2), int(cy - im.height / 2)))

    def frame(self, t):
        D = self.D
        canvas = self.bg.copy()
        breathe = 1.0 + 0.012 * math.sin(t * 1.6)
        # свечной блик снизу: тёплое пятно с живым мерцанием
        flick = 0.65 + 0.2 * math.sin(t * 9 + self.noise[0]) + 0.15 * math.sin(t * 17 + self.noise[1])
        warm = glow(210, (255, 150, 60), 48 * flick)
        canvas.alpha_composite(warm, (0, 150))
        # искры
        sp = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        sd = ImageDraw.Draw(sp)
        for x, y, size, speed, ph in self.sparks:
            yy = (y - t * speed) % S
            tw = 0.5 + 0.5 * math.sin(t * 2.4 + ph)
            r = 1.2 + 2.2 * size * tw
            sd.ellipse((x - r, yy - r, x + r, yy + r), fill=(255, 224, 160, int(60 + 150 * tw * size)))
        canvas.alpha_composite(sp.filter(ImageFilter.GaussianBlur(1.2)))
        # колода
        appear = ease(t / 1.3)
        flip_t = ease((t - 3.4) / 1.0)
        spread = 13 * ease((t - 0.4) / 1.2)
        base_y = S * 0.56 + 38 * (1 - appear)
        fl = 5 * math.sin(t * 1.3)
        if flip_t > 0.02:
            canvas.alpha_composite(glow(150 + 18 * math.sin(t * 3), (255, 214, 120), 70 * flip_t))
        for k, ang in ((-1, spread), (1, -spread)):
            self.place(canvas, self.back, S / 2 + k * 92 * ease((t - 0.3) / 1.2), base_y + fl * k + 8 * abs(k),
                       angle=ang, scale=breathe * 0.92, alpha=appear * (1 - 0.35 * flip_t))
        # средняя карта: поднимается и переворачивается
        lift = 34 * flip_t
        cy = base_y - lift + fl
        if flip_t <= 0:
            self.place(canvas, self.back, S / 2, cy, scale=breathe, alpha=appear)
        else:
            xs = abs(math.cos(math.pi * flip_t))
            img = self.back if flip_t < 0.5 else self.face
            self.place(canvas, img, S / 2, cy, scale=breathe * (1 + 0.1 * flip_t), xscale=max(xs, 0.04))
        # лёгкое затемнение краёв и в конце, чтобы кружок закрывался мягко
        fade = 1.0
        if t > D - 0.5:
            fade = max(0.0, (D - t) / 0.5)
        if t < 0.25:
            fade = t / 0.25
        out = np.asarray(canvas.convert("RGB"), np.float32) * fade
        return out.astype(np.uint8).tobytes()


async def speak(text, path, voice, rate, pitch):
    import edge_tts
    await edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).save(path)


def duration(path):
    out = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                   "-of", "csv=p=0", str(path)])
    return float(out.strip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", required=True)
    ap.add_argument("--card", default="m17")
    ap.add_argument("--out", required=True)
    ap.add_argument("--voice", default="ru-RU-SvetlanaNeural")
    ap.add_argument("--rate", default="-6%")
    ap.add_argument("--pitch", default="-2Hz")
    ap.add_argument("--lead", type=float, default=0.5, help="тишина перед голосом, с")
    a = ap.parse_args()
    tmp = Path(tempfile.mkdtemp(prefix="note_"))
    voice = tmp / "voice.mp3"
    asyncio.run(speak(a.text, str(voice), a.voice, a.rate, a.pitch))
    D = a.lead + duration(voice) + 0.7
    if D > 59:
        sys.exit("кружок длиннее 60 секунд, сократи текст")
    scene = Scene(D, a.card)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    # тихий пад на фоне: три синуса с тремоло и фильтром, голос поверх
    pad = ("sine=f=110:d={d},volume=0.5[a];sine=f=165:d={d},volume=0.35[b];sine=f=220:d={d},volume=0.25[c];"
           "[a][b][c]amix=inputs=3:normalize=0,tremolo=f=0.25:d=0.5,lowpass=f=700,volume=0.35,"
           "afade=t=in:d=0.8,afade=t=out:st={fo}:d=0.6[pad];"
           "[1:a]adelay={ms}|{ms},volume=1.6[v];[pad][v]amix=inputs=2:normalize=0,alimiter=limit=0.95[aout]"
           ).format(d=D, fo=D - 0.6, ms=int(a.lead * 1000))
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{S}x{S}",
           "-r", str(FPS), "-i", "-", "-i", str(voice), "-filter_complex", pad,
           "-map", "0:v", "-map", "[aout]", "-t", f"{D:.2f}", "-c:v", "libx264", "-pix_fmt", "yuv420p",
           "-profile:v", "main", "-crf", "23", "-preset", "medium", "-movflags", "+faststart",
           "-c:a", "aac", "-b:a", "96k", "-ar", "44100", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    n = int(D * FPS)
    for i in range(n):
        proc.stdin.write(scene.frame(i / FPS))
    proc.stdin.close()
    if proc.wait() != 0:
        sys.exit("ffmpeg упал")
    print(f"{out}: {D:.1f} с, {out.stat().st_size // 1024} КБ")


if __name__ == "__main__":
    main()
