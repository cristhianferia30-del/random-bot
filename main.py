import os
import re
import json
import textwrap
import hashlib
import random
from io import BytesIO

import requests
import feedparser

from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
from moviepy.editor import ImageClip, CompositeVideoClip


print("BOT V5 INICIANDO", flush=True)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
FACEBOOK_PAGE_TOKEN = os.environ.get("FACEBOOK_PAGE_TOKEN", "")
FACEBOOK_PAGE_ID = os.environ.get("FACEBOOK_PAGE_ID", "")

TEXT_MODEL = os.environ.get("TEXT_MODEL", "gpt-4o-mini")
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
]

BAD_IMAGE_WORDS = [
    "logo", "icon", "map", "flag", "escudo", "seal", "diagram",
    "drawing", "illustration", "poster", "cartoon"
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


def pick_topic(items, state):
    used = set(state.get("used", []))

    fresh = []
    for t in items:
        h = text_hash(t)
        if h not in used:
            fresh.append(t)

    if not fresh:
        fresh = items[:]

    return random.choice(fresh)


def ask_ai_for_plan(title):
    system = (
        "Eres un editor viral de noticias para Facebook. "
        "Devuelve SOLO JSON válido. "
        "Busca una salida hiperrealista, creíble y visual. "
        "Nada de fantasía absurda. "
        "El fondo debe coincidir con la noticia."
    )

    user = f"""
Noticia: "{title}"

Devuelve JSON con esta forma exacta:
{{
  "headline": "titulo corto e impactante en español",
  "subtitle": "subtitulo corto en español",
  "queries": ["busqueda 1", "busqueda 2", "busqueda 3", "busqueda 4"],
  "caption": "texto corto para Facebook en español"
}}

Reglas:
- headline máximo 11 palabras.
- subtitle máximo 14 palabras.
- queries deben buscar escenarios reales y visuales ligados a la noticia.
- Si hay famoso o político, combina persona + lugar + contexto real.
- Prioriza escenas tipo celular/noticia real.
- caption máximo 4 líneas.
"""

    try:
        r = client.chat.completions.create(
            model=TEXT_MODEL,
            temperature=0.6,
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
        queries = data.get("queries", [])
        caption = data.get("caption", "").strip()

        if not headline:
            headline = f"Última hora: {clean_title(title)}"
        if not subtitle:
            subtitle = "La noticia ya comienza a mover redes."
        if not queries:
            queries = fallback_queries(title)
        if not caption:
            caption = build_caption(title)

        return {
            "headline": headline,
            "subtitle": subtitle,
            "queries": queries[:4],
            "caption": caption,
        }

    except Exception as e:
        print("AI PLAN FALLBACK:", e, flush=True)
        return {
            "headline": f"Última hora: {clean_title(title)}",
            "subtitle": "La noticia ya comienza a mover redes.",
            "queries": fallback_queries(title),
            "caption": build_caption(title),
        }


def fallback_queries(title):
    t = clean_title(title)

    queries = [
        t,
        f"{t} noticia",
        f"{t} escenario real",
        "ciudad noticias breaking news",
    ]

    t_low = t.lower()

    if "trump" in t_low or "casa blanca" in t_low:
        queries = [
            "Donald Trump White House press conference",
            "White House exterior news",
            "Washington DC press briefing",
            t,
        ]
    elif "cristiano" in t_low or "mundial" in t_low or "futbol" in t_low:
        queries = [
            "Cristiano Ronaldo stadium football match",
            "Estadio Azteca football crowd",
            "football stadium night crowd",
            t,
        ]
    elif "marina" in t_low or "barco" in t_low or "huachicol" in t_low or "puerto" in t_low:
        queries = [
            "navy ship sea investigation",
            "oil ship port mexico",
            "mexico navy port operations",
            t,
        ]
    elif "anime" in t_low or "jujutsu" in t_low:
        queries = [
            "Tokyo city night crowd",
            "anime convention crowd",
            "neon city dramatic sky",
            t,
        ]

    return queries


def build_caption(title):
    t = clean_title(title)
    return (
        f"Última hora: {t}.\n"
        "La noticia comienza a circular en redes.\n"
        "Este tema ya está generando conversación.\n"
        "No es coincidencia. Es Random."
    )


def search_wikimedia_image(query):
    url = "https://commons.wikimedia.org/w/api.php"
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": query,
        "gsrnamespace": 6,
        "gsrlimit": 8,
        "prop": "imageinfo",
        "iiprop": "url|size|mime",
    }

    try:
        r = requests.get(url, params=params, timeout=20)
        data = r.json()
        pages = data.get("query", {}).get("pages", {})

        candidates = []
        for page in pages.values():
            title = page.get("title", "").lower()
            if any(bad in title for bad in BAD_IMAGE_WORDS):
                continue

            ii = page.get("imageinfo", [])
            if not ii:
                continue

            info = ii[0]
            mime = info.get("mime", "")
            img_url = info.get("url", "")
            width = info.get("width", 0)
            height = info.get("height", 0)

            if mime not in ["image/jpeg", "image/png", "image/webp"]:
                continue
            if width < 900 or height < 600:
                continue
            if not img_url:
                continue

            score = width * height
            candidates.append((score, img_url))

        if candidates:
            candidates.sort(reverse=True)
            return candidates[0][1]

    except Exception as e:
        print("WIKIMEDIA SEARCH ERROR:", e, flush=True)

    return None


def download_best_background(queries):
    for q in queries:
        img_url = search_wikimedia_image(q)
        if img_url:
            try:
                r = requests.get(img_url, timeout=30)
                img = Image.open(BytesIO(r.content)).convert("RGB")
                path = os.path.join(OUTPUT_DIR, "bg.jpg")
                img.save(path, quality=95)
                print("BACKGROUND OK:", q, flush=True)
                return path
            except Exception as e:
                print("DOWNLOAD ERROR:", e, flush=True)

    return create_fallback_background()


def create_fallback_background():
    img = Image.new("RGB", (1080, 1920), (18, 24, 36))
    draw = ImageDraw.Draw(img)

    for y in range(1920):
        c = int(18 + (y / 1920) * 40)
        draw.line((0, y, 1080, y), fill=(c, c + 4, c + 10))

    path = os.path.join(OUTPUT_DIR, "bg.jpg")
    img.save(path, quality=95)
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
    img = ImageEnhance.Color(img).enhance(0.95)
    img = ImageEnhance.Sharpness(img).enhance(1.05)

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    for y in range(1100, 1920):
        alpha = int(220 * ((y - 1100) / 820))
        draw.line((0, y, 1080, y), fill=(0, 0, 0, alpha))

    for y in range(0, 260):
        alpha = int(120 * (1 - (y / 260)))
        draw.line((0, y, 1080, y), fill=(0, 0, 0, alpha))

    try:
        font_big = ImageFont.truetype("DejaVuSans-Bold.ttf", 78)
        font_mid = ImageFont.truetype("DejaVuSans-Bold.ttf", 56)
        font_small = ImageFont.truetype("DejaVuSans.ttf", 38)
    except Exception:
        font_big = ImageFont.load_default()
        font_mid = ImageFont.load_default()
        font_small = ImageFont.load_default()

    draw.text((58, 72), "ÚLTIMA HORA", font=font_mid, fill=(255, 255, 255, 255))

    wrapped_headline = textwrap.fill(headline.upper(), width=18)
    wrapped_subtitle = textwrap.fill(subtitle, width=26)

    draw.text((58, 1230), wrapped_headline, font=font_big, fill=(255, 255, 255, 255))
    draw.text((58, 1630), wrapped_subtitle, font=font_small, fill=(235, 235, 235, 255))

    final = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    out = os.path.join(OUTPUT_DIR, "frame.jpg")
    final.save(out, quality=95)
    return out


def make_video(image_path):
    clip = ImageClip(image_path).set_duration(VIDEO_SECONDS)

    zoomed = clip.resize(lambda t: 1.0 + (0.06 * (t / VIDEO_SECONDS)))
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
    print("QUERIES:", plan["queries"], flush=True)

    bg_path = download_best_background(plan["queries"])
    bg_img = Image.open(bg_path).convert("RGB")

    frame_path = add_overlays(
        bg_img,
        plan["headline"],
        plan["subtitle"],
    )

    video_path = make_video(frame_path)
    post_video(video_path, plan["caption"])

    used = state.get("used", [])
    used.append(text_hash(title))
    state["used"] = used[-400:]
    save_state(state)


if __name__ == "__main__":
    main()
