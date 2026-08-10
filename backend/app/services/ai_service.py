from google import genai

from app.core.config import settings


client = genai.Client(
    api_key=settings.GEMINI_API_KEY
)


def generate_summary(text: str):

    prompt = f"""
Aşağıdaki ders notunu Türkçe özetle.

Kurallar:
- En fazla 250 kelime.
- Madde madde yaz.
- Önemli kavramları belirt.

Ders Notu:

{text[:15000]}
"""

    response = client.models.generate_content(
        model="gemini-3.5-flash",
        contents=prompt,
    )

    return response.text