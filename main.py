print("MAIN INICIANDO DESDE GITHUB")

import os
import random
import base64
import requests
from openai import OpenAI
from pytrends.request import TrendReq

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
FACEBOOK_PAGE_TOKEN = os.environ["FACEBOOK_PAGE_TOKEN"]
FACEBOOK_PAGE_ID = os.environ["FACEBOOK_PAGE_ID"]

print("Secrets detectados:")
print("OPENAI_API_KEY OK")
print("FACEBOOK_PAGE_TOKEN OK")
print("FACEBOOK_PAGE_ID:", FACEBOOK_PAGE_ID)

client = OpenAI(api_key=OPENAI_API_KEY)

def obtener_trends():
    print("Obteniendo trends...")
    pytrends = TrendReq(hl="es-MX", tz=360)
    df = pytrends.trending_searches(pn="mexico")
    trends = df[0].dropna().astype(str).tolist()[:5]
    print("Trends encontradas:", trends)
    return trends

def crear_titulo(trend):
    bases = [
        "objeto raro aparece sobre cerros en mexico",
        "luces misteriosas en el cielo captadas por celular en mexico",
        "fenomeno extraño genera dudas en redes en mexico",
        "figura extraña aparece en la madrugada en una colonia de mexico"
    ]
    titulo = f"{random.choice(bases)} relacionado con {trend}"
    print("Titulo generado:", titulo)
    return titulo

def descripcion_fb(titulo):
    opciones = [
        f"Esto comenzó a circular hace unas horas: {titulo}. Testigos dicen que todo ocurrió muy rápido. ¿Casualidad o algo más?",
        f"Última hora: {titulo}. Algunos usuarios aseguran que no tiene explicación clara. ¿Tú qué opinas?",
        f"Imágenes que ya están dando de qué hablar: {titulo}. ¿Tú cómo lo ves?"
    ]
    mensaje = random.choice(opciones)
    print("Descripcion generada:", mensaje)
    return mensaje

def generar_imagen(prompt):
    print("Generando imagen con OpenAI...")
    result = client.images.generate(
        model="gpt-image-1",
        prompt=prompt,
        size="1024x1536"
    )

    image_base64 = result.data[0].b64_json
    output_path = "imagen.png"

    with open(output_path, "wb") as f:
        f.write(base64.b64decode(image_base64))

    print("Imagen guardada en:", output_path)
    return output_path

def publicar_imagen_fb(image_path, mensaje):
    print("Publicando en Facebook...")
    url = f"https://graph.facebook.com/v20.0/{FACEBOOK_PAGE_ID}/photos"

    payload = {
        "access_token": FACEBOOK_PAGE_TOKEN,
        "caption": mensaje
    }

    with open(image_path, "rb") as f:
        response = requests.post(url, data=payload, files={"source": f})

    print("Status code Facebook:", response.status_code)
    print("Facebook response:", response.text)

    response.raise_for_status()

def main():
    trends = obtener_trends()

    if not trends:
        raise Exception("No se encontraron trends")

    trend = random.choice(trends)
    titulo = crear_titulo(trend)
    mensaje = descripcion_fb(titulo)

    prompt = f"""
Genera una imagen hiperrealista vertical 9:16 como si hubiera sido tomada con un celular en México.
Tema: {titulo}.
Debe parecer real, misteriosa, viral y creíble.
No pongas texto dentro de la imagen.
""".strip()

    image_path = generar_imagen(prompt)
    publicar_imagen_fb(image_path, mensaje)
    print("PUBLICACION TERMINADA")

if __name__ == "__main__":
    main()
