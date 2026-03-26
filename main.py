# =========================
# RANDOM BOT V4
# =========================

import os
import re
import json
import time
import random
import base64
import hashlib
import requests
import feedparser

from datetime import datetime, timezone
from openai import OpenAI, BadRequestError
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import ImageClip, CompositeVideoClip, concatenate_videoclips

print("BOT V4 INICIANDO", flush=True)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
FACEBOOK_PAGE_TOKEN = os.environ.get("FACEBOOK_PAGE_TOKEN", "")
FACEBOOK_PAGE_ID = os.environ.get("FACEBOOK_PAGE_ID", "")

IMAGE_MODEL = "gpt-image-1"
IMAGES_PER_VIDEO = 3

client = OpenAI(api_key=OPENAI_API_KEY)

STATE_FILE = "posted_topics.json"
OUTPUT_DIR = "output"

os.makedirs(OUTPUT_DIR, exist_ok=True)


# =========================
# RSS
# =========================

RSS_FEEDS = [

    "https://news.google.com/rss?hl=es-419&gl=MX&ceid=MX:es-419",
    "https://news.google.com/rss/search?q=famosos&hl=es-419&gl=MX&ceid=MX:es-419",
    "https://news.google.com/rss/search?q=viral&hl=es-419&gl=MX&ceid=MX:es-419",
    "https://news.google.com/rss/search?q=misterio&hl=es-419&gl=MX&ceid=MX:es-419",
    "https://news.google.com/rss/search?q=deportes&hl=es-419&gl=MX&ceid=MX:es-419",

]


# =========================
# STATE
# =========================

def load_state():

    if not os.path.exists(STATE_FILE):

        return {"used": []}

    with open(STATE_FILE, "r", encoding="utf-8") as f:

        return json.load(f)


def save_state(state):

    with open(STATE_FILE, "w", encoding="utf-8") as f:

        json.dump(state, f, indent=2, ensure_ascii=False)


# =========================
# HELPERS
# =========================

def norm(t):

    return re.sub(r"\s+", " ", t.lower().strip())


def text_hash(t):

    return hashlib.md5(norm(t).encode()).hexdigest()


# =========================
# FETCH RSS
# =========================

def fetch_news():

    items = []

    for url in RSS_FEEDS:

        feed = feedparser.parse(url)

        for e in feed.entries[:10]:

            title = e.get("title", "")

            if len(title) < 8:

                continue

            items.append(title)

    return items


# =========================
# PICK
# =========================

def pick_topic(items, state):

    used = set(state["used"])

    for t in items:

        h = text_hash(t)

        if h not in used:

            state["used"].append(h)

            return t

    return random.choice(items)


# =========================
# CAPTION NUEVO
# =========================

def clean_title(t):

    t = re.sub(r"[-–|].*$", "", t)

    return t.strip()


def build_caption(title):

    t = clean_title(title)

    line1 = f"Última hora: {t}."

    line2 = "La noticia comienza a circular en redes y genera reacciones."

    line3 = "Usuarios dicen que el video ya se está volviendo viral."

    line4 = "No es coincidencia. Es Random."

    return f"{line1}\n{line2}\n{line3}\n{line4}"


# =========================
# PROMPTS MEJORADOS
# =========================

def build_prompts(title):

    t = clean_title(title)

    base = (
        "vertical 9:16, hiperrealista, captado con celular, "
        "persona parecida a actor famoso pero no idéntica, "
        "sin copiar rostro real, estilo televisión, realista"
    )

    p1 = f"{t}, escena realista, hospital, drama, {base}"
    p2 = f"{t}, escena emotiva, familia, realista, {base}"
    p3 = f"{t}, escena viral, redes sociales, realista, {base}"

    return [p1, p2, p3]


# =========================
# IMAGE
# =========================

def generate_image(prompt, idx):

    path = f"{OUTPUT_DIR}/img_{idx}.png"

    try:

        r = client.images.generate(

            model=IMAGE_MODEL,
            prompt=prompt,
            size="1024x1536",

        )

    except BadRequestError:

        prompt = "escena realista captada con celular, persona genérica, noticia viral"

        r = client.images.generate(

            model=IMAGE_MODEL,
            prompt=prompt,
            size="1024x1536",

        )

    with open(path, "wb") as f:

        f.write(base64.b64decode(r.data[0].b64_json))

    return path


# =========================
# VIDEO
# =========================

def make_video(images, title):

    clips = []

    for img in images:

        clip = ImageClip(img).set_duration(2.5).resize(height=1920)

        clips.append(clip)

    final = concatenate_videoclips(clips)

    out = f"{OUTPUT_DIR}/video.mp4"

    final.write_videofile(out, fps=24, audio=False)

    return out


# =========================
# FACEBOOK
# =========================

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

        )

    print(r.text)


# =========================
# MAIN
# =========================

def main():

    state = load_state()

    news = fetch_news()

    title = pick_topic(news, state)

    caption = build_caption(title)

    prompts = build_prompts(title)

    print("TITLE:", title)

    images = []

    for i, p in enumerate(prompts, 1):

        images.append(generate_image(p, i))

    video = make_video(images, title)

    post_video(video, caption)

    save_state(state)


if __name__ == "__main__":

    main()
