from google import genai
from app.core.config import settings

client = genai.Client(api_key=settings.GEMINI_API_KEY)

print("========== AVAILABLE MODELS ==========")
for model in client.models.list():
    print(model.name)
print("======================================")

def generate_summary(text: str):

    print("AAAAAAAAAAAA")

    prompt = f"""
Aşağıdaki ders notunu Türkçe özetle.

Kurallar:
- En fazla 250 kelime.
- Madde madde yaz.
- Önemli kavramları belirt.

Ders Notu:

{text[:15000]}
"""

    print("MODEL TEST")
    print("Using model: gemini-2.5-flash")

    response = client.models.generate_content(
    model="models/gemini-2.5-flash",
    contents=prompt,
)

    return response.text