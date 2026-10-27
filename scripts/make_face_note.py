"""Собирает видео-кружок с лицом героини: портрет оживает (рот по громкости голоса, моргание, дыхание),
из рук взлетают карты, мерцает свеча. 640x640, mp4 H.264 + AAC.
Пример: .venv/bin/python scripts/make_face_note.py --portrait assets/notes/src/zarya_1.png \
    --text "Здравствуй. Я Заря." --out assets/notes/greeting_face_1.mp4
Нужны ffmpeg, edge-tts, numpy, pillow. Положение рта и глаз задано для zarya_1.png (см. MOUTH, EYES)."""
import argparse
import asyncio
import math
import random
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_note import card_back, duration, ease, speak, FPS, S  # noqa: E402

# кадр 960x960 из портрета 1254x1254, потом сжатие до 640
CROP = (147, 60, 1107, 1020)
K = S / 960
MOUTH = ((620 - 147) * K, 258.0)      # шов губ, пиксели кружка
EYES = [((547 - 147) * K, (305 - 60) * K), ((694 - 147) * K, (305 - 60) * K)]
HANDS = (S * 0.5, S * 0.76)                       # откуда взлетают карты


def load_envelope(wav_path, n_frames, lead):
    with wave.open(str(wav_path)) as w:
        sr = w.getframerate()
        raw = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
        if w.getnchannels() > 1:
            raw = raw.reshape(-1, w.getnchannels()).mean(axis=1)
    env = np.zeros(n_frames, np.float32)
    win = int(sr / FPS)
    for i in range(n_frames):
        s = int((i / FPS - lead) * sr)
        if s < 0 or s + win > len(raw):
            continue
        env[i] = np.sqrt(np.mean(raw[s:s + win] ** 2))
    env = env / (np.percentile(env[env > 0.002], 92) if (env > 0.002).any() else 1)
    env = np.clip(env, 0, 1)
    out = np.zeros_like(env)
    v = 0.0
    for i, e in enumerate(env):          # быстрый подъём, медленный спад
        v = v + (e - v) * (0.6 if e > v else 0.35)
        out[i] = v
    return out


def bilinear(img, xs, ys):
    h, w = img.shape[:2]
    xs = np.clip(xs, 0, w - 1.001)
    ys = np.clip(ys, 0, h - 1.001)
    x0, y0 = xs.astype(int), ys.astype(int)
    fx, fy = (xs - x0)[..., None], (ys - y0)[..., None]
    a = img[y0, x0] * (1 - fx) + img[y0, x0 + 1] * fx
    b = img[y0 + 1, x0] * (1 - fx) + img[y0 + 1, x0 + 1] * fx
    return a * (1 - fy) + b * fy


class FaceScene:
    def __init__(self, portrait, D, env, seed=11):
        im = Image.open(portrait).convert("RGB").crop(CROP).resize((S, S), Image.LANCZOS)
        self.base = np.asarray(im, np.float32)
        self.D, self.env = D, env
        rnd = random.Random(seed)
        self.blinks = sorted(rnd.uniform(1.2, D - 1.2) for _ in range(max(2, int(D / 3.4))))
        self.back = card_back()
        self.sparks = [(rnd.uniform(0, S), rnd.uniform(0, S), rnd.uniform(0.2, 1.0),
                        rnd.uniform(6, 20), rnd.uniform(0, 6.28)) for _ in range(34)]
        # броски карт: (начало, длительность, куда по x, угол вращения)
        self.tosses = [(0.9, 1.3, -250, 200), (2.9, 1.3, 250, -240), (5.0, 1.3, -240, 160), (7.4, 1.3, 240, -200),
                       (9.6, 1.3, -250, 180), (11.8, 1.3, 250, -220)]
        self.tosses = [t for t in self.tosses if t[0] + t[1] < D - 0.2]
        y, x = np.mgrid[0:S, 0:S].astype(np.float32)
        d = np.sqrt((x - S / 2) ** 2 + (y - S / 2) ** 2) / (S * 0.72)
        self.vig = (1 - 0.55 * np.clip(d - 0.55, 0, 1) ** 1.5)[..., None]
        self.noise = [rnd.uniform(0, 6.28) for _ in range(3)]
        mx, my = MOUTH
        self.roi = (int(mx - 60), int(my - 40), int(mx + 60), int(my + 50))

    def speak_amp(self, t):
        i = min(int(t * FPS), len(self.env) - 1)
        return float(self.env[i])

    def mouth(self, img, t):
        amp = self.speak_amp(t)
        x0, y0, x1, y1 = self.roi
        sub = img[y0:y1, x0:x1]
        gy, gx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
        mx, my = MOUTH
        # нижняя губа и челюсть уходят вниз, верхняя остаётся
        drop = amp * 8.5
        gauss = np.exp(-(((gx - mx) / 30) ** 2 + ((gy - (my + 10)) / 20) ** 2))
        below = np.clip((gy - (my + 1)) / 5, 0, 1)
        dy = drop * gauss * below
        warped = bilinear(img, gx, gy - dy)
        # тёмный проём рта
        oh = max(0.0, drop * 0.95 - 0.8)
        if oh > 0.4:
            ell = (((gx - mx) / (14 + amp * 3)) ** 2 + ((gy - (my + 1 + oh * 0.5)) / max(oh * 0.6, 1)) ** 2)
            m = np.clip(1.3 - ell, 0, 1)[..., None]
            m = np.asarray(Image.fromarray((m[..., 0] * 255).astype(np.uint8)).filter(
                ImageFilter.GaussianBlur(1.2)), np.float32)[..., None] / 255
            warped = warped * (1 - m * 0.9) + np.array([52, 18, 22], np.float32) * (m * 0.9)
        img[y0:y1, x0:x1] = warped

    def blink(self, img, t):
        b = 0.0
        for bt in self.blinks:
            d = abs(t - bt)
            if d < 0.09:
                b = max(b, 1 - d / 0.09)
        if b <= 0:
            return
        for ex, ey in EYES:
            x0, x1, y0, y1 = int(ex - 34), int(ex + 34), int(ey - 20), int(ey + 16)
            gy, gx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
            skin = img[int(ey - 26), int(ex - 8):int(ex + 8)].mean(axis=0)
            ell = ((gx - ex) / 30) ** 2 + ((gy - ey) / (11 * b + 0.01)) ** 2
            m = np.clip(1.4 - ell, 0, 1)[..., None] * min(1.0, b * 1.4)
            img[y0:y1, x0:x1] = img[y0:y1, x0:x1] * (1 - m) + skin * m

    def cards(self, canvas, t):
        for t0, dur, dx, rot in self.tosses:
            p = (t - t0) / dur
            if not 0 <= p <= 1:
                continue
            hx, hy = HANDS
            x = hx + dx * ease(p)
            y = hy - 150 * math.sin(math.pi * p) + 30 * p
            sc = 0.42 + 0.14 * math.sin(math.pi * p)
            ang = rot * p
            xs = max(abs(math.cos(math.pi * p * 2.2)), 0.2)
            alpha = min(1.0, p * 8) * min(1.0, (1 - p) * 4)
            im = self.back.resize((max(2, int(self.back.width * sc * xs)), max(2, int(self.back.height * sc))),
                                  Image.LANCZOS).rotate(ang, expand=True, resample=Image.BICUBIC)
            a = im.getchannel("A").point(lambda v: int(v * alpha))
            im.putalpha(a)
            sp = Image.new("RGBA", (S, S), (0, 0, 0, 0))
            ImageDraw.Draw(sp).ellipse((x - 60, y - 60, x + 60, y + 60), fill=(255, 214, 120, int(60 * alpha)))
            canvas.alpha_composite(sp.filter(ImageFilter.GaussianBlur(24)))
            canvas.alpha_composite(im, (int(x - im.width / 2), int(y - im.height / 2)))

    def frame(self, t):
        img = self.base.copy()
        self.mouth(img, t)
        # дыхание и покачивание головы
        sway = 1.4 * math.sin(t * 0.9) + 0.6 * math.sin(t * 2.1)
        sc = 1.02 + 0.012 * math.sin(t * 1.5) + 0.01 * (t / self.D)
        ang = math.radians(0.7 * math.sin(t * 0.7))
        gy, gx = np.mgrid[0:S, 0:S].astype(np.float32)
        cx, cy = S / 2, S * 0.55
        xr, yr = gx - cx, gy - cy
        c, s = math.cos(ang), math.sin(ang)
        sx = (c * xr + s * yr) / sc + cx - sway
        sy = (-s * xr + c * yr) / sc + cy - 1.2 * math.sin(t * 1.5)
        img = bilinear(img, sx, sy)
        # мерцание свечей: лёгкое тёплое колебание яркости
        flick = 1.0 + 0.025 * math.sin(t * 9 + self.noise[0]) + 0.015 * math.sin(t * 17 + self.noise[1])
        img = img * flick * self.vig
        canvas = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).convert("RGBA")
        sp = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        sd = ImageDraw.Draw(sp)
        for x, y, size, speed, ph in self.sparks:
            yy = (y - t * speed) % S
            tw = 0.5 + 0.5 * math.sin(t * 2.4 + ph)
            r = 1.0 + 1.8 * size * tw
            sd.ellipse((x - r, yy - r, x + r, yy + r), fill=(255, 224, 160, int(40 + 120 * tw * size)))
        canvas.alpha_composite(sp.filter(ImageFilter.GaussianBlur(1.0)))
        self.cards(canvas, t)
        fade = 1.0
        if t > self.D - 0.5:
            fade = max(0.0, (self.D - t) / 0.5)
        if t < 0.25:
            fade = t / 0.25
        out = np.asarray(canvas.convert("RGB"), np.float32) * fade
        return out.astype(np.uint8).tobytes()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--portrait", required=True)
    ap.add_argument("--text", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--voice", default="ru-RU-SvetlanaNeural")
    ap.add_argument("--rate", default="-6%")
    ap.add_argument("--pitch", default="-2Hz")
    ap.add_argument("--lead", type=float, default=0.6)
    a = ap.parse_args()
    tmp = Path(tempfile.mkdtemp(prefix="facenote_"))
    voice = tmp / "voice.mp3"
    asyncio.run(speak(a.text, str(voice), a.voice, a.rate, a.pitch))
    wav = tmp / "voice.wav"
    subprocess.check_call(["ffmpeg", "-y", "-loglevel", "error", "-i", str(voice), "-ac", "1", "-ar", "16000", str(wav)])
    D = a.lead + duration(voice) + 0.7
    if D > 59:
        sys.exit("кружок длиннее 60 секунд, сократи текст")
    n = int(D * FPS)
    env = load_envelope(wav, n, a.lead)
    scene = FaceScene(a.portrait, D, env)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    pad = ("sine=f=110:d={d},volume=0.5[a];sine=f=165:d={d},volume=0.35[b];sine=f=220:d={d},volume=0.25[c];"
           "[a][b][c]amix=inputs=3:normalize=0,tremolo=f=0.25:d=0.5,lowpass=f=700,volume=0.3,"
           "afade=t=in:d=0.8,afade=t=out:st={fo}:d=0.6[pad];"
           "[1:a]adelay={ms}|{ms},volume=1.6[v];[pad][v]amix=inputs=2:normalize=0,alimiter=limit=0.95[aout]"
           ).format(d=D, fo=D - 0.6, ms=int(a.lead * 1000))
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{S}x{S}",
           "-r", str(FPS), "-i", "-", "-i", str(voice), "-filter_complex", pad,
           "-map", "0:v", "-map", "[aout]", "-t", f"{D:.2f}", "-c:v", "libx264", "-pix_fmt", "yuv420p",
           "-profile:v", "main", "-crf", "23", "-preset", "medium", "-movflags", "+faststart",
           "-c:a", "aac", "-b:a", "96k", "-ar", "44100", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(n):
        proc.stdin.write(scene.frame(i / FPS))
    proc.stdin.close()
    if proc.wait() != 0:
        sys.exit("ffmpeg упал")
    print(f"{out}: {D:.1f} с, {out.stat().st_size // 1024} КБ")


if __name__ == "__main__":
    main()
