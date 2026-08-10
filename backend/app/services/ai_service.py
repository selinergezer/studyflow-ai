from google import genai
from google.genai import types
from pydantic import BaseModel

from app.core.config import settings


client = genai.Client(
    api_key=settings.GEMINI_API_KEY
)


# =========================================================
# QUIZ RESPONSE MODELLERİ
# =========================================================

class QuizQuestion(BaseModel):
    question_type: str
    question_text: str

    option_a: str | None = None
    option_b: str | None = None
    option_c: str | None = None
    option_d: str | None = None

    correct_answer: str
    explanation: str


class QuizResponse(BaseModel):
    questions: list[QuizQuestion]


# =========================================================
# PDF ÖZETLEME
# =========================================================

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


# =========================================================
# AI QUIZ OLUŞTURMA
# =========================================================

def generate_quiz(text: str, question_count: int = 10):

    prompt = f"""
Aşağıdaki ders notuna göre bir sınav quiz'i oluştur.

Kurallar:

- Toplam {question_count} soru oluştur.
- Sorular yalnızca verilen ders notundaki bilgilere dayanmalı.
- Bilgi uydurma.
- Sorular birbirinden farklı olmalı.
- Sorular öğrencinin konuyu gerçekten anlayıp anlamadığını ölçmeli.
- Türkçe yaz.

Soru tiplerini dengeli şekilde kullan:

1. multiple_choice
2. true_false
3. classic

Multiple choice sorularında A, B, C ve D seçenekleri bulunmalı.

True/false sorularında doğru cevap "Doğru" veya "Yanlış" olmalı.
Bu soru tipinde seçenekleri boş bırak.

Classic sorularda seçenekleri boş bırak.
Doğru cevap kısa ve açık şekilde verilmelidir.

Her sorunun açıklamasını da oluştur.

Ders Notu:

{text[:30000]}
"""

    response = client.models.generate_content(
        model="gemini-3.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=QuizResponse,
        ),
    )

    return response.parsed

if __name__ == "__main__":
    test_text = """
    Olasılık, bir olayın gerçekleşme ihtimalini ifade eder.
    Bir olayın olasılığı 0 ile 1 arasında değer alır.
    Kesin olayın olasılığı 1, imkansız olayın olasılığı 0'dır.

    Örneğin adil bir zar atıldığında 6 gelme olasılığı 1/6'dır.
    """

    result = generate_quiz(test_text, 3)

    print("\n===== QUIZ TEST =====")

    for i, question in enumerate(result.questions, start=1):
        print(f"\nSoru {i}")
        print("Tip:", question.question_type)
        print("Soru:", question.question_text)
        print("A:", question.option_a)
        print("B:", question.option_b)
        print("C:", question.option_c)
        print("D:", question.option_d)
        print("Cevap:", question.correct_answer)
        print("Açıklama:", question.explanation)