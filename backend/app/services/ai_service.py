from anthropic import Anthropic

from app.core.config import settings

client = Anthropic(
    api_key=settings.ANTHROPIC_API_KEY
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

    response = client.messages.create(
        model="claude-3-5-haiku-latest",
        max_tokens=700,
        temperature=0.2,
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    return response.content[0].text