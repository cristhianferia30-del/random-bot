import os
import json
import time
import random
import base64
import hashlib
import requests
import feedparser
from datetime import datetime, timezone
from openai import OpenAI

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
FACEBOOK_PAGE_TOKEN = os.environ.get("FACEBOOK_PAGE_TOKEN", "")
FACEBOOK_PAGE_ID = os.environ.get("FACEBOOK_PAGE_ID", "")

if not OPENAI_API_KEY:
    raise Exception("Falta OPENAI_API_KEY")
if not FACEBOOK_PAGE_TOKEN:
    raise Exception("Falta FACEBOOK_PAGE_TOKEN")
if not FACEBOOK_PAGE_ID:
    raise Exception("Falta FACEBOOK_PAGE_ID")

client = OpenAI(api_key=OPENAI_API_KEY)

STATE_FILE = "posted_topics.json"

RSS_FEEDS = [
    "https://news.google.com/rss?hl=es-419&gl=MX&ceid=MX:es-419",
    "https://news.google.com/rss/search?q=viral&hl=es-419&gl=MX&ceid=MX:es-419",
    "https://news.google.com/rss/search?q=meme&hl=es-419&gl=MX&ceid=MX:es-419",
    "https://news.google.com/rss/search?q=tendencia&hl=es-419&gl=MX&ceid=MX:es-419",
    "https://news.google.com/rss/search?q=famosos&hl=es-419&gl=MX&ceid=MX:es-419",
    "https://news.google.com/rss/search?q=ovni+fantasma+misterio&hl=es-419&gl=MX&ceid=MX:es-419",
]

CATEGORY_KEYWORDS = {
    "meme": [
        "meme", "viral", "redes", "tiktok", "instagram", "twitter", "x",
        "pelea", "trejo", "adame", "famoso", "burlas", "beso", "parodia"
    ],
    "misterio": [
        "ovni", "fantasma", "misterio", "extraño", "raro", "aparición",
        "luces", "figura", "sombra", "terror", "paranormal"
    ],
    "noticia": [
        "volcán", "volcan", "sismo", "huracán", "tormenta", "incendio",
        "choque", "accidente", "lluvia", "nube", "explosión", "explosion"
    ],
    "famosos": [
        "actor", "actriz", "cantante", "influencer", "famoso", "famosa",
        "trejo", "adame", "celebridad"
    ],
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
    return " ".join((text or "").lower().strip().split())

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
    if hours <= 6:
        return 5
    if hours <= 24:
        return 4
    if hours <= 48:
        return 3
    if hours <= 96:
        return 2
    return 1

def fetch_candidates():
    items = []
    for url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            for e in feed.entries[:10]:
                title = (e.get("title") or "").strip()
                summary = (e.get("summary") or "").strip()
                link = (e.get("link") or "").strip()
                combo = f"{title} {summary}"
                if len(title) < 8:
                    continue
                items.append({
                    "title": title,
                    "summary": summary,
                    "link": link,
                    "category": detect_category(combo),
                    "freshness": freshness_score(e),
                })
        except Exception:
            continue
    return items

def dedupe_and_pick(items, state):
    seen = set()
    clean = []
    used = set(state.get("used_hashes", []))

    for it in items:
        h = text_hash(it["title"])
        if h in seen or h in used:
            continue
        seen.add(h)
        score = it["freshness"]

        if it["category"] == "meme":
            score += 3
        elif it["category"] == "misterio":
            score += 2
        elif it["category"] == "famosos":
            score += 2

        if any(x in norm(it["title"]) for x in ["video", "fotos", "imagen", "memes", "viral"]):
            score += 1

        it["score"] = score
        it["hash"] = h
        clean.append(it)

    if not clean:
        fallback = [
            {"title": "nube rara sobre una colonia en mexico", "category": "noticia", "score": 5, "hash": text_hash("nube rara sobre una colonia en mexico")},
            {"title": "meme viral de famosos en redes", "category": "meme", "score": 5, "hash": text_hash("meme viral de famosos en redes")},
            {"title": "figura extraña captada en la madrugada", "category": "misterio", "score": 5, "hash": text_hash("figura extraña captada en la madrugada")},
        ]
        clean = fallback

    clean.sort(key=lambda x: x["score"], reverse=True)
    top = clean[:5]
    return random.choice(top)

def build_title(item):
    raw = item["title"]
    cat = item["category"]

    if cat == "meme":
        bases = [
            "imagen viral inspirada en una tendencia absurda de redes",
            "escena viral tipo meme ultra realista basada en tendencia fresca",
            "momento extraño y chistoso que parece noticia real"
        ]
    elif cat == "misterio":
        bases = [
            "figura extraña aparece en la madrugada en una colonia de mexico",
            "objeto raro genera dudas en redes en mexico",
            "luces misteriosas captadas por celular en mexico"
        ]
    elif cat == "famosos":
        bases = [
            "escena viral relacionada con famosos que está explotando en redes",
            "imagen tendencia de celebridades convertida en escena hiperrealista",
            "situación absurda y viral inspirada en famosos del momento"
        ]
    else:
        bases = [
            "escena viral inspirada en una noticia fresca en mexico",
            "imagen hiperrealista basada en un tema que se está moviendo en redes",
            "momento impactante inspirado en una noticia reciente"
        ]

    return f"{random.choice(bases)} relacionado con {raw}"

def build_caption(title):
    options = [
        f"Esto comenzó a circular hace unas horas: {title}. ¿Casualidad o algo más?",
        f"Ya empezó a moverse en redes: {title}. Algunos dicen que parece falso, otros no tanto.",
        f"Última hora en modo Random: {title}. ¿Tú qué ves aquí?"
    ]
    return random.choice(options)

def build_prompt(item, final_title):
    cat = item["category"]

    if cat == "meme":
        return f"""
Genera una imagen hiperrealista vertical 9:16 como si fuera una foto tomada con celular en México.
Tema principal: {final_title}
Debe verse actual, viral, absurda pero creíble.
Puede tener vibra de meme fresco de internet, pero sin caricatura.
Nada de texto dentro de la imagen.
Rostros, ropa, calles y luces deben verse reales.
""".strip()

    if cat == "misterio":
        return f"""
Genera una imagen hiperrealista vertical 9:16 como si fuera captada por celular en México.
Tema principal: {final_title}
Debe verse misteriosa, real, inquietante y viral.
Puede incluir calle, colonia, cables, postes, cielo raro, figura o luces extrañas.
Nada de texto dentro de la imagen.
Todo debe parecer evidencia real.
""".strip()

    if cat == "famosos":
        return f"""
Genera una imagen hiperrealista vertical 9:16 inspirada en una tendencia viral de famosos.
Tema principal: {final_title}
Debe verse como una foto real, fresca, actual y muy compartible en redes.
Nada de texto dentro de la imagen.
No estilo caricatura.
""".strip()

    return f"""
Genera una imagen hiperrealista vertical 9:16 como si fuera tomada con celular en México.
Tema principal: {final_title}
Debe parecer una noticia fresca, real y viral.
Nada de texto dentro de la imagen.
Ambiente creíble, luz realista y composición natural.
""".strip()

def generate_image(prompt):
    result = client.images.generate(
        model="gpt-image-1",
        prompt=prompt,
        size="1024x1536"
    )
    output_path = "imagen.png"
    with open(output_path, "wb") as f:
        f.write(base64.b64decode(result.data[0].b64_json))
    return output_path

def publish_facebook(image_path, caption):
    url = f"https://graph.facebook.com/v20.0/{FACEBOOK_PAGE_ID}/photos"
    payload = {
        "access_token": FACEBOOK_PAGE_TOKEN,
        "caption": caption
    }
    with open(image_path, "rb") as f:
        response = requests.post(url, data=payload, files={"source": f})
    print("FACEBOOK STATUS:", response.status_code, flush=True)
    print("FACEBOOK RESPONSE:", response.text, flush=True)
    response.raise_for_status()

def main():
    print("BOT V2 INICIANDO", flush=True)
    state = load_state()
    items = fetch_candidates()
    selected = dedupe_and_pick(items, state)

    final_title = build_title(selected)
    caption = build_caption(final_title)
    prompt = build_prompt(selected, final_title)

    print("SELECCIONADO:", selected["title"], flush=True)
    print("CATEGORIA:", selected["category"], flush=True)
    print("FINAL TITLE:", final_title, flush=True)

    image_path = generate_image(prompt)
    publish_facebook(image_path, caption)

    state["used_hashes"] = (state.get("used_hashes", []) + [selected["hash"]])[-200:]
    state["history"] = (state.get("history", []) + [{
        "source_title": selected["title"],
        "final_title": final_title,
        "category": selected["category"],
        "published_at": datetime.now(timezone.utc).isoformat()
    }])[-200:]
    save_state(state)

    print("PUBLICACION TERMINADA", flush=True)

if __name__ == "__main__":
    main()
