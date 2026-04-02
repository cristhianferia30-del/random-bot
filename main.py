import os
import re
import json
import textwrap
import hashlib
import random
import base64

import requests
import feedparser

from openai import OpenAI, BadRequestError
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
from moviepy.editor import ImageClip, CompositeVideoClip

print("BOT V8 INICIANDO", flush=True)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
FACEBOOK_PAGE_TOKEN = os.environ.get("FACEBOOK_PAGE_TOKEN", "")
FACEBOOK_PAGE_ID = os.environ.get("FACEBOOK_PAGE_ID", "")

TEXT_MODEL = os.environ.get("TEXT_MODEL", "gpt-4o-mini")
IMAGE_MODEL = os.environ.get("IMAGE_MODEL", "gpt-image-1")
IMAGE_QUALITY = os.environ.get("IMAGE_QUALITY", "low")
VIDEO_SECONDS = float(os.environ.get("VIDEO_SECONDS", "8"))

client = OpenAI(api_key=OPENAI_API_KEY)

STATE_FILE = "posted_topics.json"
OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

RSS_FEEDS = [
    "https://news.google.com/rss?hl=es-419&gl=MX&ceid=MX:es-419",
    "https://news.google.com/rss/search?q=famosos&hl=es-419&gl=MX&ceid=MX:es-419",
    "https://news.google.com/rss/search?q=viral&hl=es-419&gl=MX&ceid=MX:es-419",
    "https://news.google.com/rss/search?q=misterio&hl=es-419&gl=MX&ceid=MX:es-419",
    "https://news.google.com/rss/search?q=deportes&hl=es-419&gl=MX&ceid=MX:es-419",
    "https://news.google.com/rss/search?q=mundial&hl=es-419&gl=MX&ceid=MX:es-419",
    "https://news.google.com/rss/search?q=anime&hl=es-419&gl=MX&ceid=MX:es-419",
    "https://news.google.com/rss/search?q=wendy+guevara&hl=es-419&gl=MX&ceid=MX:es-419",
    "https://news.google.com/rss/search?q=poncho+de+nigris&hl=es-419&gl=MX:es-419",
    "https://news.google.com/rss/search?q=terremoto&hl=es-419&gl=MX&ceid=MX:es-419",
    "https://news.google.com/rss/search?q=sismo&hl=es-419&gl=MX&ceid=MX:es-419",
]

def load_state():
    if not os.path.exists(STATE_FILE):
        return {"used": []}
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

def norm(t):
    return re.sub(r"\s+", " ", t.lower().strip())

def text_hash(t):
    return hashlib.md5(norm(t).encode()).hexdigest()

def clean_title(t):
    t = re.sub(r"[-–|].*$", "", t)
    return t.strip()

def fetch_news():
    items = []
    seen = set()

    for url in RSS_FEEDS:
        feed = feedparser.parse(url)
        for e in feed.entries[:12]:
            title = clean_title(e.get("title", ""))
            if len(title) < 10:
                continue
            h = text_hash(title)
            if h not in seen:
                seen.add(h)
                items.append(title)

    return items

def score_topic(title):
    t = clean_title(title).lower()
    score = 0

    if any(x in t for x in ["muere", "accidente", "explota", "caos", "impacta", "sismo", "terremoto", "temblor", "incendio", "desastre"]):
        score += 5

    if any(x in t for x in ["wendy", "poncho", "nigris", "actor", "cantante", "famoso", "marcela", "de nigris", "casa de los famosos"]):
        score += 4

    if any(x in t for x in ["mundial", "futbol", "cristiano", "gol", "america", "estadio", "ronaldo"]):
        score += 4

    if any(x in t for x in ["viral", "redes", "video", "filtran", "escandalo", "polémica", "revela", "rompe"]):
        score += 3

    if any(x in t for x in ["ovni", "extraño", "misterio", "raro", "inexplicable"]):
        score += 3

    return score

def pick_topic(items, state):
    used = set(state.get("used", []))
    fresh = []

    for t in items:
        h = text_hash(t)
        if h not in used:
            fresh.append(t)

    if not fresh:
        fresh = items[:]

    fresh.sort(key=score_topic, reverse=True)
    top = fresh[:5] if len(fresh) >= 5 else fresh
    return random.choice(top)

def build_caption(title):
    t = clean_title(title)
    return (
        f"Última hora: {t}.\n"
        "La noticia comienza a circular en redes.\n"
        "Este tema ya está generando conversación.\n"
        "No es coincidencia. Es Random."
    )

def fallback_prompt(title):
    t = clean_title(title)
    return f"""
Fotografía REAL tomada con celular, estilo noticia de último momento.

Escena basada en: {t}

IMPORTANTE:
- personas reales
- rostro humano natural
- textura real de piel
- iluminación imperfecta de celular
- ligero ruido de cámara
- ligero desenfoque natural
- encuadre imperfecto como si alguien tomara la foto rápido
- fondo totalmente relacionado con la noticia
- sensación de reportaje o testigo presencial
- hiperrealista
- muy creíble
- nada artístico

PROHIBIDO:
- caricatura
- ilustración
- pintura
- CGI
- render
- 3D
- anime
- muñeco
- texto dentro de la imagen

Si aparecen famosos:
- solo parecidos
- nunca idénticos
- estilo personas reales inspiradas en figuras públicas

La imagen debe parecer una foto real tomada por un celular en la vida real.
"""

def ask_ai_for_plan(title):
    system = (
        "Eres un editor viral de Facebook. "
        "Devuelve solo JSON válido. "
        "Tu objetivo es hacer una salida hiperrealista, humana, visual y creíble. "
        "Nada caricaturizado. "
        "Nada artístico."
    )

    user = f"""
Noticia: "{title}"

Devuelve JSON con esta forma exacta:
{{
  "headline": "titulo corto e impactante en español",
  "subtitle": "subtitulo corto en español",
  "image_prompt": "prompt hiperrealista y muy real tipo celular",
  "caption": "texto corto para Facebook en español"
}}

Reglas:
- headline máximo 10 palabras.
- subtitle máximo 14 palabras.
- image_prompt debe verse como foto real tomada con celular.
- cero caricatura, cero ilustración, cero render.
- si hay famosos, solo parecidos, nunca idénticos.
- caption máximo 4 líneas.
"""

    try:
        r = client.chat.completions.create(
            model=TEXT_MODEL,
            temperature=0.7,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )

        text = r.choices[0].message.content.strip()
        match = re.search(r"\{.*\}", text, re.S)
        if match:
            text = match.group(0)

        data = json.loads(text)

        headline = data.get("headline", "").strip()
        subtitle = data.get("subtitle", "").strip()
        image_prompt = data.get("image_prompt", "").strip()
        caption = data.get("caption", "").strip()

        if not headline:
            headline = f"Última hora: {clean_title(title)}"
        if not subtitle:
            subtitle = "La noticia ya comienza a mover redes."
        if not image_prompt:
            image_prompt = fallback_prompt(title)
        if not caption:
            caption = build_caption(title)

        return {
            "headline": headline,
            "subtitle": subtitle,
            "image_prompt": image_prompt,
            "caption": caption,
        }

    except Exception as e:
        print("AI PLAN FALLBACK:", e, flush=True)
        return {
            "headline": f"Última hora: {clean_title(title)}",
            "subtitle": "La noticia ya comienza a mover redes.",
            "image_prompt": fallback_prompt(title),
            "caption": build_caption(title),
        }

def generate_ai_background(prompt):
    path = os.path.join(OUTPUT_DIR, "bg.png")

    try:
        r = client.images.generate(
            model=IMAGE_MODEL,
            prompt=prompt,
            size="1024x1536",
            quality=IMAGE_QUALITY,
        )
    except BadRequestError as e:
        print("IMAGE ERROR 1:", e, flush=True)
        r = client.images.generate(
            model=IMAGE_MODEL,
            prompt="""
Fotografía real tomada con celular.
Escena urbana real.
Iluminación natural.
Piel real.
Sin texto.
Sin caricatura.
Sin ilustración.
Sin render.
""",
            size="1024x1536",
            quality=IMAGE_QUALITY,
        )

    img_bytes = base64.b64decode(r.data[0].b64_json)
    with open(path, "wb") as f:
        f.write(img_bytes)

    return path

def cover_crop(img, target_w=1080, target_h=1920):
    w, h = img.size
    src_ratio = w / h
    tgt_ratio = target_w / target_h

    if src_ratio > tgt_ratio:
        new_h = target_h
        new_w = int(new_h * src_ratio)
    else:
        new_w = target_w
        new_h = int(new_w / src_ratio)

    img = img.resize((new_w, new_h), Image.LANCZOS)

    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    return img.crop((left, top, left + target_w, top + target_h))

def add_overlays(base_img, headline, subtitle):
    img = cover_crop(base_img)

    img = ImageEnhance.Contrast(img).enhance(1.08)
    img = ImageEnhance.Color(img).enhance(0.96)
    img = ImageEnhance.Sharpness(img).enhance(1.06)

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    for y in range(1100, 1920):
        alpha = int(215 * ((y - 1100) / 820))
        draw.line((0, y, 1080, y), fill=(0, 0, 0, alpha))

    for y in range(0, 260):
        alpha = int(120 * (1 - (y / 260)))
        draw.line((0, y, 1080, y), fill=(0, 0, 0, alpha))

    try:
        font_big = ImageFont.truetype("DejaVuSans-Bold.ttf", 76)
        font_mid = ImageFont.truetype("DejaVuSans-Bold.ttf", 54)
        font_small = ImageFont.truetype("DejaVuSans.ttf", 36)
    except Exception:
        font_big = ImageFont.load_default()
        font_mid = ImageFont.load_default()
        font_small = ImageFont.load_default()

    draw.text((58, 72), "ÚLTIMA HORA", font=font_mid, fill=(255, 255, 255, 255))

    wrapped_headline = textwrap.fill(headline.upper(), width=18)
    wrapped_subtitle = textwrap.fill(subtitle, width=28)

    draw.text((58, 1220), wrapped_headline, font=font_big, fill=(255, 255, 255, 255))
    draw.text((58, 1630), wrapped_subtitle, font=font_small, fill=(235, 235, 235, 255))

    final = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    out = os.path.join(OUTPUT_DIR, "frame.jpg")
    final.save(out, quality=95)
    return out

def make_video(image_path):
    clip = ImageClip(image_path).set_duration(VIDEO_SECONDS)
    zoomed = clip.resize(lambda t: 1.0 + (0.08 * (t / VIDEO_SECONDS)))
    final = CompositeVideoClip([zoomed.set_position("center")], size=(1080, 1920))
    final = final.set_duration(VIDEO_SECONDS)

    out = os.path.join(OUTPUT_DIR, "video.mp4")
    final.write_videofile(
        out,
        fps=24,
        codec="libx264",
        audio=False,
        threads=2,
        preset="medium",
    )
    return out

def post_video(video, caption):
    url = f"https://graph.facebook.com/v20.0/{FACEBOOK_PAGE_ID}/videos"

    with open(video, "rb") as f:
        r = requests.post(
            url,
            data={
                "access_token": FACEBOOK_PAGE_TOKEN,
                "description": caption,
            },
            files={"source": f},
            timeout=120,
        )

    print("FACEBOOK RESPONSE:", r.text, flush=True)
    r.raise_for_status()

def main():
    state = load_state()
    news = fetch_news()

    if not news:
        print("NO HAY NOTICIAS", flush=True)
        return

    title = pick_topic(news, state)
    plan = ask_ai_for_plan(title)

    print("TITLE:", title, flush=True)
    print("HEADLINE:", plan["headline"], flush=True)
    print("IMAGE PROMPT:", plan["image_prompt"], flush=True)

    bg_path = generate_ai_background(plan["image_prompt"])
    bg_img = Image.open(bg_path).convert("RGB")

    frame_path = add_overlays(bg_img, plan["headline"], plan["subtitle"])
    video_path = make_video(frame_path)
    post_video(video_path, plan["caption"])

    used = state.get("used", [])
    used.append(text_hash(title))
    state["used"] = used[-400:]
    save_state(state)

if __name__ == "__main__":
    main()
