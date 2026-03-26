import os
import re
import json
import time
import math
import random
import base64
import hashlib
import requests
import feedparser
from datetime import datetime, timezone
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import ImageClip, CompositeVideoClip, concatenate_videoclips

print("BOT V3 INICIANDO", flush=True)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
FACEBOOK_PAGE_TOKEN = os.environ.get("FACEBOOK_PAGE_TOKEN", "")
FACEBOOK_PAGE_ID = os.environ.get("FACEBOOK_PAGE_ID", "")
IMAGE_MODEL = os.environ.get("IMAGE_MODEL", "gpt-image-1")
IMAGE_QUALITY = os.environ.get("IMAGE_QUALITY", "low")
IMAGES_PER_VIDEO = int(os.environ.get("IMAGES_PER_VIDEO", "3"))

if not OPENAI_API_KEY:
    raise Exception("Falta OPENAI_API_KEY")
if not FACEBOOK_PAGE_TOKEN:
    raise Exception("Falta FACEBOOK_PAGE_TOKEN")
if not FACEBOOK_PAGE_ID:
    raise Exception("Falta FACEBOOK_PAGE_ID")

client = OpenAI(api_key=OPENAI_API_KEY)

STATE_FILE = "posted_topics.json"
OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

RSS_FEEDS = [
    "https://news.google.com/rss?hl=es-419&gl=MX&ceid=MX:es-419",
    "https://news.google.com/rss/search?q=farandula&hl=es-419&gl=MX&ceid=MX:es-419",
    "https://news.google.com/rss/search?q=deportes&hl=es-419&gl=MX&ceid=MX:es-419",
    "https://news.google.com/rss/search?q=politica&hl=es-419&gl=MX&ceid=MX:es-419",
    "https://news.google.com/rss/search?q=viral&hl=es-419&gl=MX&ceid=MX:es-419",
    "https://news.google.com/rss/search?q=meme&hl=es-419&gl=MX&ceid=MX:es-419",
    "https://news.google.com/rss/search?q=accidente&hl=es-419&gl=MX&ceid=MX:es-419",
    "https://news.google.com/rss/search?q=ovni+fantasma+misterio&hl=es-419&gl=MX&ceid=MX:es-419",
    "https://news.google.com/rss/search?q=internacional&hl=es-419&gl=MX&ceid=MX:es-419",
    "https://news.google.com/rss/search?q=influencer&hl=es-419&gl=MX&ceid=MX:es-419",
]

CATEGORY_KEYWORDS = {
    "meme": ["meme", "viral", "redes", "tiktok", "instagram", "x ", "twitter", "parodia", "broma", "burla"],
    "misterio": ["ovni", "fantasma", "misterio", "extraño", "raro", "aparición", "luces", "sombra", "paranormal", "terror"],
    "deporte": ["futbol", "box", "boxeo", "ufc", "deporte", "liga", "gol", "pelea", "partido", "nba", "champions"],
    "politica": ["senado", "presidente", "gobierno", "diputado", "politica", "eleccion", "reforma", "marcha"],
    "famosos": ["actor", "actriz", "cantante", "influencer", "famoso", "famosa", "celebridad", "televisa", "novela"],
    "noticia": ["volcan", "volcán", "sismo", "tormenta", "lluvia", "huracan", "huracán", "incendio", "accidente", "choque", "explosion", "explosión"],
    "internacional": ["eeuu", "usa", "europa", "china", "rusia", "ucrania", "internacional", "mundo", "global"],
}

SLOT_PREFS = {
    "12:00": ["noticia", "internacional", "politica"],
    "15:00": ["meme", "famosos", "deporte"],
    "18:00": ["misterio", "noticia"],
    "21:00": ["famosos", "deporte", "meme"],
    "22:30": ["misterio", "meme", "famosos"],
}

def load_state():
    if not os.path.exists(STATE_FILE):
        return {"used_hashes": [], "history": []}
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def norm(text):
    text = (text or "").lower().strip()
    text = re.sub(r"\s+", " ", text)
    return text

def text_hash(text):
    return hashlib.md5(norm(text).encode("utf-8")).hexdigest()

def detect_category(text):
    txt = norm(text)
    scores = {k: 0 for k in CATEGORY_KEYWORDS}
    for cat, words in CATEGORY_KEYWORDS.items():
        for w in words:
            if w in txt:
                scores[cat] += 1
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "noticia"

def freshness_score(entry):
    published = None
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        try:
            published = datetime.fromtimestamp(time.mktime(entry.published_parsed), tz=timezone.utc)
        except Exception:
            published = None

    if not published:
        return 1

    hours = (datetime.now(timezone.utc) - published).total_seconds() / 3600
    if hours <= 4:
        return 6
    if hours <= 12:
        return 5
    if hours <= 24:
        return 4
    if hours <= 48:
        return 3
    if hours <= 96:
        return 2
    return 1

def current_slot():
    now = datetime.now(timezone.utc)
    h = now.hour
    m = now.minute

    # UTC que equivale a MX aprox:
    # 12:00 MX -> 18:00 UTC
    # 15:00 MX -> 21:00 UTC
    # 18:00 MX -> 00:00 UTC
    # 21:00 MX -> 03:00 UTC
    # 22:30 MX -> 04:30 UTC
    if h == 18 and m < 30:
        return "12:00"
    if h == 21 and m < 30:
        return "15:00"
    if h == 0 and m < 30:
        return "18:00"
    if h == 3 and m < 30:
        return "21:00"
    return "22:30"

def fetch_candidates():
    items = []
    for url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            for e in feed.entries[:12]:
                title = (e.get("title") or "").strip()
                summary = re.sub("<.*?>", " ", (e.get("summary") or "")).strip()
                link = (e.get("link") or "").strip()
                combo = f"{title} {summary}"
                if len(title) < 10:
                    continue
                items.append({
                    "title": title,
                    "summary": summary,
                    "link": link,
                    "category": detect_category(combo),
                    "freshness": freshness_score(e),
                })
        except Exception as ex:
            print("RSS error:", url, str(ex), flush=True)
            continue
    return items

def pick_topic(items, state):
    used = set(state.get("used_hashes", []))
    slot = current_slot()
    prefs = SLOT_PREFS.get(slot, [])

    ranked = []
    seen = set()

    for item in items:
        h = text_hash(item["title"])
        if h in used or h in seen:
            continue
        seen.add(h)

        score = item["freshness"]

        if item["category"] in prefs:
            score += 4

        title_low = norm(item["title"])
        if any(x in title_low for x in ["video", "foto", "imagen", "memes", "viral"]):
            score += 1
        if len(item["title"]) > 25:
            score += 1

        item["score"] = score
        item["hash"] = h
        ranked.append(item)

    if not ranked:
        fallback = [
            {"title": "luces extrañas captadas por celular en mexico", "category": "misterio", "score": 8, "hash": text_hash("luces extrañas captadas por celular en mexico")},
            {"title": "meme viral de famosos explotando en redes", "category": "meme", "score": 8, "hash": text_hash("meme viral de famosos explotando en redes")},
            {"title": "noticia fresca que genera debate en mexico", "category": "noticia", "score": 8, "hash": text_hash("noticia fresca que genera debate en mexico")},
        ]
        return random.choice(fallback)

    ranked.sort(key=lambda x: x["score"], reverse=True)
    top = ranked[:8]
    return random.choice(top)

def build_final_title(item):
    t = item["title"]
    cat = item["category"]

    if cat == "meme":
        bases = [
            "escena viral absurda pero creíble basada en tendencia fresca",
            "momento viral estilo meme convertido en foto hiperrealista",
            "imagen extraña y chistosa inspirada en lo que explota en redes"
        ]
    elif cat == "misterio":
        bases = [
            "figura extraña aparece en una colonia de mexico",
            "luces misteriosas captadas por celular en mexico",
            "objeto raro genera dudas en redes en mexico"
        ]
    elif cat == "famosos":
        bases = [
            "escena hiperrealista inspirada en famosos del momento",
            "imagen viral relacionada con celebridades que está explotando en redes",
            "momento extraño y viral inspirado en farándula actual"
        ]
    elif cat == "deporte":
        bases = [
            "imagen viral inspirada en deporte y pelea del momento",
            "momento tenso convertido en escena hiperrealista de tendencia deportiva",
            "escena fuerte basada en una tendencia deportiva reciente"
        ]
    elif cat == "politica":
        bases = [
            "imagen viral inspirada en una noticia política caliente",
            "momento de debate convertido en escena hiperrealista actual",
            "escena intensa basada en tema político fresco"
        ]
    else:
        bases = [
            "escena viral inspirada en una noticia fresca en mexico",
            "momento impactante basado en un tema que se está moviendo en redes",
            "imagen hiperrealista basada en una noticia reciente"
        ]

    return f"{random.choice(bases)} relacionado con {t}"

def build_caption(final_title):
    options = [
        f"Esto comenzó a circular hace unas horas: {final_title}. ¿Casualidad o algo más?",
        f"Ya empezó a moverse en redes: {final_title}. Algunos dicen que parece falso, otros no tanto.",
        f"Última hora en modo Random: {final_title}. ¿Tú qué ves aquí?"
    ]
    return random.choice(options)

def build_prompts(item, final_title, n=3):
    cat = item["category"]
    source = item["title"]

    base_real = "vertical 9:16, hiperrealista, captado con celular, iluminación real, nada de caricatura, sin texto dentro de la imagen"
    prompts = []

    scene1 = f"Primera toma amplia. {final_title}. Inspirado en: {source}. {base_real}."
    scene2 = f"Segunda toma media, más cerca del momento principal. {final_title}. Misma historia, misma vibra visual, más detalle en rostros/objetos/entorno. {base_real}."
    scene3 = f"Tercera toma cercana o final. {final_title}. Misma historia, detalle fuerte y creíble para volverse viral. {base_real}."

    if cat == "meme":
        scene1 += " La escena debe verse absurda pero creíble y muy compartible en redes."
        scene2 += " La situación debe mantener humor raro sin romper el realismo."
        scene3 += " Debe parecer el fotograma más viral del clip."
    elif cat == "misterio":
        scene1 += " Debe sentirse inquietante, raro y real."
        scene2 += " Puede incluir sombras, luces, cielo raro, calle o colonia."
        scene3 += " Debe parecer evidencia captada en el momento."
    elif cat == "famosos":
        scene1 += " La escena debe verse como paparazzi o foto viral."
        scene2 += " Mantener estética real de red social o nota de farándula."
        scene3 += " Debe parecer el momento más comentado."
    elif cat == "deporte":
        scene1 += " La escena debe verse intensa, rápida y muy compartible."
        scene2 += " Mantener energía deportiva realista."
        scene3 += " Debe parecer el frame que todos comentan."
    elif cat == "politica":
        scene1 += " La escena debe verse como momento tenso de debate o noticia."
        scene2 += " Mantener tono serio pero viral."
        scene3 += " Debe parecer la imagen más fuerte del tema."
    else:
        scene1 += " Debe sentirse como noticia fresca y real."
        scene2 += " Mantener coherencia visual."
        scene3 += " Debe cerrar fuerte."

    prompts.extend([scene1, scene2, scene3])
    return prompts[:n]

def generate_image(prompt, idx):
    path = os.path.join(OUTPUT_DIR, f"img_{idx}.png")
    result = client.images.generate(
        model=IMAGE_MODEL,
        prompt=prompt,
        size="1024x1536",
        quality=IMAGE_QUALITY
    )
    with open(path, "wb") as f:
        f.write(base64.b64decode(result.data[0].b64_json))
    return path

def load_font(size=52, bold=False):
    options = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for p in options:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()

def wrap_text(draw, text, font, max_width):
    words = text.split()
    lines = []
    line = ""
    for w in words:
        test = w if not line else f"{line} {w}"
        bbox = draw.textbbox((0, 0), test, font=font)
        if (bbox[2] - bbox[0]) <= max_width:
            line = test
        else:
            if line:
                lines.append(line)
            line = w
    if line:
        lines.append(line)
    return lines

def make_overlay(text, out_path, width=1080, height=250, font_size=52, bold=True):
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = load_font(font_size, bold=bold)

    pad = 40
    lines = wrap_text(draw, text.upper(), font, width - pad * 2)
    line_h = draw.textbbox((0, 0), "Ag", font=font)[3] + 12
    box_h = len(lines) * line_h + 40
    y0 = max(10, (height - box_h) // 2)
    y1 = min(height - 10, y0 + box_h)

    draw.rounded_rectangle([(20, y0), (width - 20, y1)], radius=26, fill=(0, 0, 0, 145))

    y = y0 + 20
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        x = (width - w) // 2
        draw.text((x, y), line, font=font, fill=(255, 255, 255, 255))
        y += line_h

    img.save(out_path)
    return out_path

def make_video(image_paths, title):
    clips = []

    title_png = os.path.join(OUTPUT_DIR, "title.png")
    make_overlay(title[:110], title_png, height=260, font_size=48, bold=True)

    for i, path in enumerate(image_paths):
        base = ImageClip(path).set_duration(2.7).resize(height=1920).set_position("center")
        zoom = base.resize(lambda t: 1 + 0.04 * (t / 2.7))

        title_clip = ImageClip(title_png).set_duration(2.7).set_position(("center", 50))

        comp = CompositeVideoClip([zoom, title_clip], size=(1080, 1920))
        clips.append(comp)

    final = concatenate_videoclips(clips, method="compose")
    video_path = os.path.join(OUTPUT_DIR, "final_video.mp4")
    final.write_videofile(
        video_path,
        fps=24,
        codec="libx264",
        audio=False,
        preset="medium",
        threads=2
    )
    return video_path

def publish_video_fb(video_path, caption):
    print("Publicando video en Facebook...", flush=True)
    url = f"https://graph.facebook.com/v20.0/{FACEBOOK_PAGE_ID}/videos"
    payload = {
        "access_token": FACEBOOK_PAGE_TOKEN,
        "description": caption
    }
    with open(video_path, "rb") as f:
        r = requests.post(url, data=payload, files={"source": f})
    print("FACEBOOK STATUS:", r.status_code, flush=True)
    print("FACEBOOK RESPONSE:", r.text, flush=True)
    r.raise_for_status()

def main():
    state = load_state()
    items = fetch_candidates()
    selected = pick_topic(items, state)
    final_title = build_final_title(selected)
    caption = build_caption(final_title)
    prompts = build_prompts(selected, final_title, IMAGES_PER_VIDEO)

    print("TOPICO:", selected["title"], flush=True)
    print("CATEGORIA:", selected["category"], flush=True)
    print("TITULO FINAL:", final_title, flush=True)

    image_paths = []
    for idx, prompt in enumerate(prompts, start=1):
        print(f"Generando imagen {idx}...", flush=True)
        image_paths.append(generate_image(prompt, idx))

    video_path = make_video(image_paths, final_title)
    publish_video_fb(video_path, caption)

    state["used_hashes"] = (state.get("used_hashes", []) + [selected["hash"]])[-300:]
    state["history"] = (state.get("history", []) + [{
        "source_title": selected["title"],
        "final_title": final_title,
        "category": selected["category"],
        "slot": current_slot(),
        "published_at": datetime.now(timezone.utc).isoformat()
    }])[-300:]
    save_state(state)

    print("PUBLICACION TERMINADA", flush=True)

if __name__ == "__main__":
    main()
