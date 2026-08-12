from google import genai
from google.genai import types
from pydantic import BaseModel
from typing import Optional, Literal

from app.core.config import settings
from app.services.ollama_service import generate_with_ollama


# =========================================================
# GEMINI CLIENT
# =========================================================

client = genai.Client(
    api_key=settings.GEMINI_API_KEY
)


# =========================================================
# QUIZ RESPONSE MODELLERİ
# =========================================================

class QuizQuestion(BaseModel):
    # Artık yalnızca çoktan seçmeli soru kabul ediyoruz.
    question_type: Literal["multiple_choice"]

    question_text: str

    # Beş şık da zorunlu.
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    option_e: str

    # Doğru cevap yalnızca A-E olabilir.
    correct_answer: Literal["A", "B", "C", "D", "E"]

    explanation: str


class QuizResponse(BaseModel):
    questions: list[QuizQuestion]


# =========================================================
# PDF ÖZETLEME - OLLAMA
# =========================================================

def generate_summary(text: str):

    prompt = f"""
Sen StudyFlow AI adlı öğrenme platformunun
özetleme asistanısın.

Aşağıdaki ders notunu yalnızca verilen içeriğe dayanarak özetle.

DİL KURALI:
- Özet, kaynak ders notuyla AYNI DİLDE olmalıdır.
- Kaynak İngilizceyse İngilizce yaz.
- Kaynak Türkçeyse Türkçe yaz.
- Başka bir dildeyse mümkün olduğunca aynı dili kullan.

KURALLAR:
- Bilgi uydurma.
- Ders notunda olmayan bilgi ekleme.
- En fazla 500 kelime yaz.
- Düzenli başlıklar ve maddeler kullan.
- Önemli kavramları belirt.
- Teknik terimleri koru.
- Açık ve öğrenci dostu bir dil kullan.
- Gereksiz giriş ve kapanış cümleleri yazma.
- "Certainly", "Here is your summary" gibi gereksiz ifadeler yazma.
- Yalnızca özeti döndür.

DERS NOTU:

{text[:15000]}
"""

    return generate_with_ollama(prompt)


# =========================================================
# QUIZ DOĞRULAMA
# =========================================================

def _validate_quiz(
    quiz: QuizResponse,
    question_count: int
):

    if quiz is None:
        raise ValueError(
            "AI quiz cevabı boş döndü."
        )

    if not quiz.questions:
        raise ValueError(
            "AI hiç soru oluşturmadı."
        )

    # İstenen soru sayısı tam olmalı.
    if len(quiz.questions) != question_count:
        raise ValueError(
            f"AI {question_count} soru yerine "
            f"{len(quiz.questions)} soru oluşturdu."
        )

    for index, question in enumerate(
        quiz.questions,
        start=1
    ):

        # -----------------------------------------------------
        # SORU METNİ
        # -----------------------------------------------------

        if not question.question_text.strip():
            raise ValueError(
                f"{index}. sorunun soru metni boş."
            )

        # -----------------------------------------------------
        # QUESTION TYPE
        # -----------------------------------------------------

        if question.question_type != "multiple_choice":
            raise ValueError(
                f"{index}. sorunun soru tipi geçersiz: "
                f"{question.question_type}"
            )

        # -----------------------------------------------------
        # ŞIKLAR
        # -----------------------------------------------------

        options = [
            question.option_a,
            question.option_b,
            question.option_c,
            question.option_d,
            question.option_e,
        ]

        # Hiçbir şık boş olmamalı.
        if any(
            option is None or not option.strip()
            for option in options
        ):
            raise ValueError(
                f"{index}. soruda eksik veya boş şık var."
            )

        # Şıklar birbirinden farklı olmalı.
        normalized_options = [
            option.strip().casefold()
            for option in options
        ]

        if len(set(normalized_options)) != 5:
            raise ValueError(
                f"{index}. soruda tekrarlanan şık var."
            )

        # -----------------------------------------------------
        # DOĞRU CEVAP
        # -----------------------------------------------------

        correct_answer = (
            question.correct_answer
            .strip()
            .upper()
        )

        if correct_answer not in {
            "A",
            "B",
            "C",
            "D",
            "E"
        }:
            raise ValueError(
                f"{index}. sorunun doğru cevabı "
                f"A, B, C, D veya E olmalı."
            )

        # -----------------------------------------------------
        # AÇIKLAMA
        # -----------------------------------------------------

        if not question.explanation.strip():
            raise ValueError(
                f"{index}. sorunun açıklaması boş."
            )

    return quiz


# =========================================================
# AI QUIZ OLUŞTURMA - OLLAMA
# =========================================================

def generate_quiz(

    text: str,

    question_count: int = 10

):

    questions = []

    for question_number in range(1, question_count + 1):

        prompt = f"""

Sen StudyFlow AI adlı kişisel öğrenme platformunun

çoktan seçmeli sınav hazırlama asistanısın.

Aşağıdaki ders notuna dayanarak SADECE 1 adet

çoktan seçmeli soru oluştur.

Bu soru, toplam {question_count} soruluk sınavın

{question_number}. sorusudur.

KURALLAR:

- Yalnızca 1 soru üret.

- question_type TAM OLARAK "multiple_choice" olmalıdır.

- question_text dolu olmalıdır.

- option_a dolu olmalıdır.

- option_b dolu olmalıdır.

- option_c dolu olmalıdır.

- option_d dolu olmalıdır.

- option_e dolu olmalıdır.

- Beş seçenek birbirinden farklı olmalıdır.

- correct_answer yalnızca "A", "B", "C", "D" veya "E" olmalıdır.

- explanation dolu olmalıdır.

- Soruyu yalnızca verilen ders notundaki bilgilerden oluştur.

- Bilgi uydurma.

- Soruyu ders notunun diliyle aynı dilde oluştur.

- Mümkün olduğunca önceki sorulardan farklı bir kavram seç.

DERS NOTU:

{text[:30000]}

"""

        max_attempts = 3

        generated_question = None

        for attempt in range(1, max_attempts + 1):

            try:

                raw_response = generate_with_ollama(

                    prompt,

                    response_schema=QuizQuestion.model_json_schema(),

                )

                generated_question = QuizQuestion.model_validate_json(

                    raw_response

                )

                temp_quiz = QuizResponse(

                    questions=[generated_question]

                )

                _validate_quiz(

                    temp_quiz,

                    1

                )

                break

            except Exception as error:

                print(

                    f"Ollama {question_number}. soru doğrulama hatası "

                    f"(deneme {attempt}/{max_attempts}): {error}"

                )

                if attempt == max_attempts:

                    raise ValueError(

                        f"{question_number}. soru oluşturulamadı."

                    ) from error

        if generated_question is None:

            raise ValueError(

                f"{question_number}. soru oluşturulamadı."

            )

        questions.append(generated_question)

    quiz = QuizResponse(

        questions=questions

    )

    quiz = _validate_quiz(

        quiz,

        question_count

    )

    print(

        f"Ollama Quiz başarıyla oluşturuldu. "

        f"Soru sayısı: {len(quiz.questions)}"

    )

    return quiz


# =========================================================
# QUIZ TEST
# =========================================================

if __name__ == "__main__":

    test_text = """
    Olasılık, bir olayın gerçekleşme ihtimalini ifade eder.
    Bir olayın olasılığı 0 ile 1 arasında değer alır.
    Kesin olayın olasılığı 1, imkansız olayın olasılığı 0'dır.

    Örneğin adil bir zar atıldığında
    6 gelme olasılığı 1/6'dır.
    """

    result = generate_quiz(
        test_text,
        3
    )

    print(
        "\n===== QUIZ TEST ====="
    )

    for i, question in enumerate(
        result.questions,
        start=1
    ):

        print(f"\nSoru {i}")

        print(
            "Tip:",
            question.question_type
        )

        print(
            "Soru:",
            question.question_text
        )

        print(
            "A:",
            question.option_a
        )

        print(
            "B:",
            question.option_b
        )

        print(
            "C:",
            question.option_c
        )

        print(
            "D:",
            question.option_d
        )

        print(
            "E:",
            question.option_e
        )

        print(
            "Cevap:",
            question.correct_answer
        )

        print(
            "Açıklama:",
            question.explanation
        )


# =========================================================
# AI FLASHCARD OLUŞTURMA
# ŞİMDİLİK GEMINI
# =========================================================

class FlashcardItem(BaseModel):
    question: str
    answer: str


class FlashcardResponse(BaseModel):
    flashcards: list[FlashcardItem]


def generate_flashcards(
    text: str,
    flashcard_count: int = 10
):
    flashcards = []

    for card_number in range(1, flashcard_count + 1):

        prompt = f"""
Sen StudyFlow AI adlı öğrenme platformunun
bilgi kartı hazırlama asistanısın.

Aşağıdaki ders notuna dayanarak SADECE 1 adet
bilgi kartı oluştur.

Bu kart toplam {flashcard_count} kartın
{card_number}. kartıdır.

KURALLAR:

- Yalnızca 1 bilgi kartı oluştur.
- question alanı dolu olmalıdır.
- answer alanı dolu olmalıdır.
- question SADECE tek bir soru içermelidir.
- question kısa ve tek bir soru olmalıdır.
- Gereksiz uzun soru yazma.
- answer SADECE sorunun doğrudan cevabını içermelidir.
- answer en fazla 40 kelime olmalıdır.
- Uzun açıklama yazma.
- Özet oluşturma.
- Madde listesi oluşturma.
- Numaralı liste oluşturma.
- Markdown kullanma.
- Başlık veya liste biçimlendirmesi kullanma.
- Bir kartta yalnızca bir kavram veya bilgiyi ölç.
- Kart yalnızca verilen ders notuna dayanmalıdır.
- Bilgi uydurma.
- Ders notunda olmayan bilgi ekleme.
- Ders notunun diliyle aynı dilde oluştur.
DERS NOTU:

{text[:30000]}
"""

        max_attempts = 3
        generated_card = None

        for attempt in range(1, max_attempts + 1):

            try:
                raw_response = generate_with_ollama(
                    prompt,
                    response_schema=FlashcardItem.model_json_schema(),
                )

                generated_card = FlashcardItem.model_validate_json(
                    raw_response
                )

                if not generated_card.question.strip():
                    raise ValueError(
                        "Bilgi kartı sorusu boş."
                    )

                if not generated_card.answer.strip():
                    raise ValueError(
                        "Bilgi kartı cevabı boş."
                    )
                
                if len(generated_card.answer.split()) > 40:
                    raise ValueError(
                        "Bilgi kartı cevabı çok uzun."
                    )

                break

            except Exception as error:
                print(
                    f"Ollama {card_number}. bilgi kartı hatası "
                    f"(deneme {attempt}/{max_attempts}): {error}"
                )

                if attempt == max_attempts:
                    raise ValueError(
                        f"{card_number}. bilgi kartı oluşturulamadı."
                    ) from error

        if generated_card is None:
            raise ValueError(
                f"{card_number}. bilgi kartı oluşturulamadı."
            )

        flashcards.append(generated_card)

    result = FlashcardResponse(
        flashcards=flashcards
    )

    print(
        f"Ollama Bilgi Kartları başarıyla oluşturuldu. "
        f"Kart sayısı: {len(result.flashcards)}"
    )

    return result


# =========================================================
# AI ÇALIŞMA ÖNERİSİ
# ŞİMDİLİK GEMINI
# =========================================================

class StudyRecommendation(BaseModel):
    message: str
    priority: str
    recommended_action: str


def generate_study_recommendation(
    total_courses: int,
    total_quizzes: int,
    quiz_average: float,
    total_flashcards: int,
    flashcard_reviews: int,
    weakest_course: Optional[str] = None,
    study_hours: float = 0
):

    prompt = f"""
Bir öğrencinin çalışma verilerini analiz et ve
ona kişiselleştirilmiş bir çalışma önerisi oluştur.

Öğrenci verileri:

- Toplam ders sayısı: {total_courses}
- Toplam quiz sayısı: {total_quizzes}
- Quiz ortalaması: {quiz_average}
- Toplam flashcard sayısı: {total_flashcards}
- Yapılan flashcard tekrar sayısı: {flashcard_reviews}
- En zayıf ders: {weakest_course or "Belirlenmemiş"}
- Çalışma süresi: {study_hours} saat

Kurallar:

- Türkçe yaz.
- Öğrencinin verilerine göre gerçekçi bir öneri oluştur.
- Verilmeyen bilgileri uydurma.
- Kısa ve net ol.
- Öğrenciye bugün ne yapması gerektiğini söyle.
- Eğer quiz ortalaması düşükse quiz çalışmasına ağırlık ver.
- Eğer flashcard tekrarları düşükse tekrar yapmasını öner.
- En zayıf ders belli ise önceliği o derse ver.
- Çalışma süresi düşükse uygulanabilir bir çalışma süresi öner.
- Priority değeri yalnızca
  "low", "medium" veya "high" olabilir.

message alanında öğrencinin mevcut durumunu
kısa şekilde açıkla.

recommended_action alanında öğrencinin bugün
uygulayabileceği somut bir çalışma görevi ver.
"""

    raw_response = generate_with_ollama(
        prompt,
        response_schema=StudyRecommendation.model_json_schema(),
)

    result = StudyRecommendation.model_validate_json(
    raw_response
)

    return result

  


# =========================================================
# PDF ÜZERİNDEN AI SOHBET
# ŞİMDİLİK GEMINI
# =========================================================

def ask_ai_about_document(
    document_text: str,
    question: str
):

    prompt = f"""
Sen StudyFlow AI adlı kişisel öğrenme platformunun
ders asistanısın.

Aşağıdaki ders notunu kaynak olarak kullanarak
öğrencinin sorusunu cevapla.

KURALLAR:

- Yalnızca verilen ders notundaki bilgilere dayan.
- Ders notunda cevap yoksa açıkça belirt.
- Bilgi uydurma.
- Sorunun dilini ve ders notunun dilini dikkate al.
- Cevabı mümkün olduğunca aynı dilde ver.
- Anlaşılır ve öğretici ol.
- Gereksiz uzun cevap verme.
- Konuyla ilgisiz bilgi ekleme.
- Gereksiz giriş ve kapanış cümleleri yazma.

DERS NOTU:

{document_text[:30000]}

ÖĞRENCİNİN SORUSU:

{question}
"""

    return generate_with_ollama(prompt)


# =========================================================
# AI ÇALIŞMA PLANI OLUŞTURMA
# ŞİMDİLİK GEMINI
# =========================================================

class StudyPlanItem(BaseModel):
    day: str
    course: str
    duration_minutes: int
    reason: str


class PlannerResponse(BaseModel):
    weekly_plan: list[StudyPlanItem]
    general_advice: str


def generate_study_plan(
    courses,
    events,
    goals,
    available_hours_per_day: float,
    target_gpa: float,
    weekly_hours_target: float
):

    # ---------------------------------------------------------
    # DERS BİLGİLERİ
    # ---------------------------------------------------------

    course_info = []

    for course in courses:

        course_info.append({
            "id": course.id,
            "name": course.name,
            "description": course.description
        })

    # ---------------------------------------------------------
    # EVENT BİLGİLERİ
    # ---------------------------------------------------------

    event_info = []

    for event in events:

        event_info.append({
            "title": event.title,
            "event_type": event.event_type,
            "start_date": str(
                event.start_date
            ),
            "end_date": (
                str(event.end_date)
                if event.end_date
                else None
            ),
            "course_id": event.course_id
        })

    # ---------------------------------------------------------
    # HEDEF BİLGİLERİ
    # ---------------------------------------------------------

    goal_info = []

    for goal in goals:

        goal_info.append({
            "title": goal.title,
            "goal_type": goal.goal_type,
            "target_value": goal.target_value,
            "current_value": goal.current_value,
            "start_date": str(
                goal.start_date
            ),
            "end_date": str(
                goal.end_date
            ),
            "completed": goal.completed,
            "course_id": goal.course_id
        })

    # ---------------------------------------------------------
    # GERÇEK DERS İSİMLERİ
    # ---------------------------------------------------------

    course_names = [
        course.name
        for course in courses
    ]

    # ---------------------------------------------------------
    # PLANLAMA KAPASİTESİ
    # ---------------------------------------------------------

    daily_limit_minutes = int(
        available_hours_per_day * 60
    )

    weekly_target_minutes = int(
        weekly_hours_target * 60
    )

    maximum_weekly_minutes = (
        daily_limit_minutes * 7
    )

    effective_weekly_target_minutes = min(
        weekly_target_minutes,
        maximum_weekly_minutes
    )

    effective_weekly_target_hours = (
        effective_weekly_target_minutes
        / 60
    )

    # ---------------------------------------------------------
    # PROMPT
    # ---------------------------------------------------------

    prompt = f"""
Sen StudyFlow AI adlı kişisel öğrenme platformunun
AI çalışma planlayıcısısın.

Öğrencinin mevcut verilerini analiz ederek
önümüzdeki 7 gün için gerçekçi, dengeli ve
uygulanabilir bir çalışma planı oluştur.

==================================================
ÖĞRENCİNİN BİLGİLERİ
==================================================

Günlük maksimum çalışma süresi:
{available_hours_per_day} saat

Günlük maksimum çalışma süresi:
{daily_limit_minutes} dakika

Öğrencinin haftalık çalışma hedefi:
{weekly_hours_target} saat

Öğrencinin uygulanabilir maksimum
haftalık çalışma kapasitesi:
{maximum_weekly_minutes} dakika

Planlanması gereken haftalık çalışma süresi:
{effective_weekly_target_minutes} dakika
({effective_weekly_target_hours} saat)

Hedef GPA:
{target_gpa}

==================================================
ÖĞRENCİNİN DERSLERİ
==================================================

{course_info}

==================================================
YAKLAŞAN ETKİNLİKLER
==================================================

{event_info}

==================================================
ÖĞRENCİNİN AKTİF HEDEFLERİ
==================================================

{goal_info}

==================================================
PLANLAMA KURALLARI
==================================================

1. Türkçe yaz.

2. Tam olarak 7 günlük plan oluştur:
   Pazartesi
   Salı
   Çarşamba
   Perşembe
   Cuma
   Cumartesi
   Pazar

3. Günlük toplam çalışma süresi
   {daily_limit_minutes} dakikayı
   kesinlikle geçmemelidir.

4. Haftalık toplam çalışma süresi
   mümkün olduğunca
   {effective_weekly_target_minutes}
   dakika olmalıdır.

5. Haftalık hedef günlük kapasiteden büyükse,
   günlük kapasiteyi aşma.

6. Dersleri yalnızca öğrencinin
   gerçek ders listesinden seç.

7. Öğrencinin ders listesinde olmayan
   hiçbir ders oluşturma.

8. Ders isimlerini birleştirme.

9. Her plan öğesinde yalnızca bir ders bulunmalıdır.

10. Bir güne birden fazla çalışma kaydı koyabilirsin.

11. Yaklaşan sınavlara öncelik ver.

12. Yaklaşan ödevlere öncelik ver.

13. Yaklaşan projelere öncelik ver.

14. Aktif hedefleri dikkate al.

15. Hedef GPA'yı dikkate al.

16. Dersleri mümkün olduğunca dengeli dağıt.

17. Aynı dersi gereksiz şekilde her güne koyma.

18. Önemli deadline varsa ilgili derse
    daha fazla zaman ayırabilirsin.

19. Konu bilgisi verilmediği için konu uydurma.

20. topics alanı kullanma.

21. duration_minutes gerçekçi olmalıdır.

22. Çalışma süreleri dakika cinsinden olmalıdır.

23. Her gün çalışma olmak zorunda değildir.

24. Haftalık hedefe mümkün olduğunca yaklaş.

25. Tamamlanmış hedefleri dikkate alma.

26. Tamamlanmış eventleri dikkate alma.

27. Verilmeyen bilgileri uydurma.

28. general_advice içinde yanlış toplam süre verme.

29. duration_minutes değerlerini kullanarak
    toplam süreyi hesapla.

30. Haftalık hedef:
    {effective_weekly_target_minutes} dakika.

31. Bu hedefi aşma.

==================================================
GEÇERLİ DERSLER
==================================================

course alanı SADECE aşağıdaki
değerlerden biri olabilir:

{course_names}

==================================================
ÇIKTI KURALLARI
==================================================

JSON dışında hiçbir şey döndürme.

weekly_plan içerisindeki her nesne
şu alanlara sahip olmalıdır:

day
course
duration_minutes
reason

topics alanı kullanma.

Her nesnede yalnızca bir ders bulunmalıdır.

course değeri yalnızca gerçek derslerden
biri olmalıdır.

duration_minutes pozitif bir sayı olmalıdır.

general_advice kısa ve Türkçe olmalıdır.
"""

    # ---------------------------------------------------------
    # GEMINI
    # ---------------------------------------------------------

    response = client.models.generate_content(
        model="gemini-3.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=PlannerResponse,
        ),
    )

    # ---------------------------------------------------------
    # AI CEVABI KONTROL
    # ---------------------------------------------------------

    if response.parsed is None:

        print(
            "AI PLANNER RESPONSE PARSED NONE"
        )

        print(
            "AI RESPONSE TEXT:"
        )

        print(
            response.text
        )

        raise ValueError(
            "AI Planner geçerli bir plan "
            "oluşturamadı."
        )

    result = response.parsed

    # ---------------------------------------------------------
    # BACKEND KONTROLLERİ
    # ---------------------------------------------------------

    valid_course_names = set(
        course_names
    )

    total_minutes = 0

    for item in result.weekly_plan:

        if item.course not in valid_course_names:

            raise ValueError(
                f"AI geçersiz bir ders oluşturdu: "
                f"{item.course}"
            )

        total_minutes += (
            item.duration_minutes
        )

    # ---------------------------------------------------------
    # HAFTALIK TOPLAM KONTROLÜ
    # ---------------------------------------------------------

    if (
        total_minutes
        > effective_weekly_target_minutes
    ):

        raise ValueError(
            f"AI haftalık çalışma hedefini aştı. "
            f"Hedef: "
            f"{effective_weekly_target_minutes} dakika, "
            f"oluşturulan: "
            f"{total_minutes} dakika."
        )

    # ---------------------------------------------------------
    # GÜNLÜK TOPLAM KONTROLÜ
    # ---------------------------------------------------------

    daily_totals = {}

    for item in result.weekly_plan:

        daily_totals[item.day] = (
            daily_totals.get(
                item.day,
                0
            )
            + item.duration_minutes
        )

    for day, total in daily_totals.items():

        if total > daily_limit_minutes:

            raise ValueError(
                f"{day} günü günlük çalışma "
                f"limitini aşıyor. "
                f"Limit: {daily_limit_minutes} dakika, "
                f"oluşturulan: {total} dakika."
            )

    # ---------------------------------------------------------
    # SONUÇ
    # ---------------------------------------------------------

    print(
        f"AI Planner oluşturuldu. "
        f"Haftalık toplam: "
        f"{total_minutes} dakika / "
        f"{effective_weekly_target_minutes} dakika"
    )

    return result