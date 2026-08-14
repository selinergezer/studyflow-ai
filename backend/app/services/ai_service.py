from google import genai
from google.genai import errors, types
from pydantic import BaseModel
from typing import Optional
import json
import time
from app.core.config import settings


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
    question_type: str
    question_text: str

    option_a: Optional[str] = None
    option_b: Optional[str] = None
    option_c: Optional[str] = None
    option_d: Optional[str] = None
    option_e: Optional[str] = None

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

def _validate_quiz(quiz: QuizResponse, question_count: int):
    """Validate Gemini quiz output before returning it to the API."""

    if quiz is None or not quiz.questions:
        raise ValueError("AI hiç soru oluşturmadı.")

    if len(quiz.questions) != question_count:
        raise ValueError(
            f"AI {question_count} soru yerine "
            f"{len(quiz.questions)} soru oluşturdu."
        )

    valid_types = {"multiple_choice", "true_false", "classic"}

    for index, question in enumerate(quiz.questions, start=1):

        if question.question_type not in valid_types:
            raise ValueError(
                f"{index}. sorunun soru tipi geçersiz: "
                f"{question.question_type}"
            )

        if not question.question_text.strip():
            raise ValueError(f"{index}. sorunun soru metni boş.")

        if not question.correct_answer.strip():
            raise ValueError(f"{index}. sorunun doğru cevabı boş.")

        if not question.explanation.strip():
            raise ValueError(f"{index}. sorunun açıklaması boş.")

        if question.question_type == "multiple_choice":

            options = [
                question.option_a,
                question.option_b,
                question.option_c,
                question.option_d,
                question.option_e,
            ]

            if any(
                option is None or not option.strip()
                for option in options
            ):
                raise ValueError(
                    f"{index}. multiple choice sorusunda "
                    f"eksik veya boş şık var."
                )

            normalized_options = [
                option.strip().casefold()
                for option in options
            ]

            if len(set(normalized_options)) != 5:
                raise ValueError(
                    f"{index}. multiple choice sorusunda "
                    f"tekrarlanan şık var."
                )

            correct_answer = question.correct_answer.strip().upper()

            if correct_answer not in {"A", "B", "C", "D", "E"}:
                raise ValueError(
                    f"{index}. multiple choice sorusunun "
                    f"doğru cevabı A, B, C, D veya E olmalı."
                )

        elif question.question_type == "true_false":

            correct_answer = question.correct_answer.strip().casefold()

            if correct_answer not in {"doğru", "yanlış"}:
                raise ValueError(
                    f"{index}. true_false sorusunun "
                    f"cevabı Doğru veya Yanlış olmalı."
                )

            question.option_a = None
            question.option_b = None
            question.option_c = None
            question.option_d = None
            question.option_e = None

        elif question.question_type == "classic":

            question.option_a = None
            question.option_b = None
            question.option_c = None
            question.option_d = None
            question.option_e = None

    return quiz


def generate_quiz(
    text: str,
    question_count: int = 10
):

    prompt = f"""
Sen StudyFlow AI adlı kişisel öğrenme platformunun
sınav hazırlama asistanısın.

Aşağıdaki ders notuna dayanarak TAM OLARAK
{question_count} adet quiz sorusu oluştur.

==================================================
ÇOK ÖNEMLİ
==================================================

- Tam olarak {question_count} soru üret.
- Eksik soru üretme.
- Fazladan soru üretme.
- Her soru tamamen doldurulmuş olmalıdır.
- Boş soru üretme.
- Boş seçenek üretme.
- Sorular yalnızca verilen ders notundaki bilgilere dayanmalı.
- Bilgi uydurma.
- Sorular birbirinden farklı olmalı.
- Türkçe yaz.

==================================================
SORU TİPLERİ
==================================================

Soru tiplerini dengeli şekilde kullan:

1. multiple_choice
2. true_false
3. classic

==================================================
MULTIPLE CHOICE
==================================================

Her multiple_choice sorusunda TAM OLARAK 5 seçenek bulunmalıdır:

- option_a dolu olmalı.
- option_b dolu olmalı.
- option_c dolu olmalı.
- option_d dolu olmalı.
- option_e dolu olmalı.
- Beş seçenek birbirinden farklı olmalı.
- Hiçbir seçenek boş olmamalı.
- correct_answer yalnızca A, B, C, D veya E olmalı.
- option_a, option_b, option_c, option_d ve option_e gerçek metin içermelidir.
- "A", "B", "C", "D", "E" gibi yalnızca harf yazma.
- "Seçenek", "Yok", "-" veya benzeri yer tutucu kullanma.
- Beş seçeneğin tamamı soruyla doğrudan ilişkili olmalıdır.
- Yanlış seçenekler de ders notundaki bilgilerle çelişmeyecek şekilde makul çeldiriciler olmalıdır.

KESİNLİKLE BOŞ ŞIK ÜRETME.

==================================================
TRUE / FALSE
==================================================

true_false sorularında:

- correct_answer yalnızca "Doğru" veya "Yanlış" olmalı.
- option_a boş olmalı.
- option_b boş olmalı.
- option_c boş olmalı.
- option_d boş olmalı.
- option_e boş olmalı.

==================================================
CLASSIC
==================================================

classic sorularda:

- option_a boş olmalı.
- option_b boş olmalı.
- option_c boş olmalı.
- option_d boş olmalı.
- option_e boş olmalı.
- correct_answer kısa ve açık olmalı.

==================================================
GENEL KURALLAR
==================================================

- Öğrencinin konuyu gerçekten anlayıp anlamadığını ölç.
- Aynı bilgiyi farklı cümlelerle tekrar etme.
- Her sorunun question_text alanı dolu olmalı.
- Her sorunun correct_answer alanı dolu olmalı.
- Her sorunun explanation alanı dolu olmalı.
- Hiçbir zorunlu alan boş bırakılamaz.

Ders Notu:

{text[:30000]}
"""

    max_attempts = 1

    for attempt in range(1, max_attempts + 1):

        response = client.models.generate_content(
            model="gemini-3.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=QuizResponse,
            ),
        )

        try:
            quiz = response.parsed

            if quiz is None:
                raise ValueError("AI cevabı boş döndü.")

            quiz = _validate_quiz(quiz, question_count)

            print(
                f"AI Quiz başarıyla oluşturuldu. "
                f"Soru sayısı: {len(quiz.questions)}"
            )

            return quiz

        except ValueError as error:

            print(
                f"Quiz doğrulama hatası "
                f"(deneme {attempt}/{max_attempts}): "
                f"{error}"
            )

            if attempt == max_attempts:
                raise ValueError(
                    "AI geçerli bir quiz oluşturamadı. "
                    "Lütfen tekrar deneyin."
                )

    raise ValueError("AI quiz oluşturma işlemi başarısız.")


# =========================================================
# QUIZ TEST
# =========================================================

if __name__ == "__main__":

    test_text = """
    Olasılık, bir olayın gerçekleşme ihtimalini ifade eder.
    Bir olayın olasılığı 0 ile 1 arasında değer alır.
    Kesin olayın olasılığı 1, imkansız olayın olasılığı 0'dır.

    Örneğin adil bir zar atıldığında 6 gelme olasılığı 1/6'dır.
    """

    result = generate_quiz(
        test_text,
        3
    )

    print("\n===== QUIZ TEST =====")

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

    prompt = f"""
Aşağıdaki ders notuna göre {flashcard_count} adet flashcard oluştur.

Kurallar:

- Sorular yalnızca verilen ders notundaki bilgilere dayanmalı.
- Bilgi uydurma.
- Her soru farklı bir kavramı veya önemli bilgiyi ölçmeli.
- Sorular kısa ve anlaşılır olmalı.
- Cevaplar kısa ama yeterince açıklayıcı olmalı.
- Türkçe yaz.
- Flashcard'lar sınava hazırlanmak için kullanılabilecek nitelikte olmalı.
- Gereksiz ayrıntılardan kaçın.
- Aynı bilgiyi tekrar eden kartlar oluşturma.

Ders Notu:

{text[:30000]}
"""

    response = client.models.generate_content(
        model="gemini-3.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=FlashcardResponse,
        ),
    )

    return response.parsed


# =========================================================
# AI ÇALIŞMA ÖNERİSİ
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
- Priority değeri yalnızca "low", "medium" veya "high" olabilir.

message alanında öğrencinin mevcut durumunu
kısa şekilde açıkla.

recommended_action alanında öğrencinin bugün
uygulayabileceği somut bir çalışma görevi ver.
"""

    response = client.models.generate_content(
        model="gemini-3.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=StudyRecommendation,
        ),
    )

    return response.parsed

# =========================================================
# PDF ÜZERİNDEN AI SOHBET
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

Kurallar:
- Yalnızca verilen ders notundaki bilgilere dayan.
- Ders notunda cevap yoksa bunu açıkça belirt.
- Bilgi uydurma.
- Türkçe cevap ver.
- Anlaşılır ve öğretici ol.
- Gereksiz uzun cevap verme.

DERS NOTU:
{document_text[:30000]}

ÖĞRENCİNİN SORUSU:
{question}
"""

    response = client.models.generate_content(
        model="gemini-3.5-flash",
        contents=prompt,
    )

    return response.text


# =========================================================
# AI ÇALIŞMA PLANI OLUŞTURMA
# =========================================================

class StudyPlanItem(BaseModel):
    day: str
    course: str
    duration_minutes: int
    reason: str


class PlannerResponse(BaseModel):
    weekly_plan: list[StudyPlanItem]
    general_advice: str


class PlannerServiceUnavailableError(Exception):
    def __init__(self, status_code: int):
        self.status_code = status_code
        super().__init__("Gemini planner service is temporarily unavailable.")


def _transient_gemini_status(error: errors.APIError) -> Optional[int]:
    code = getattr(error, "code", None)

    if code in (429, 503):
        return code

    message = str(error).upper()

    if "RESOURCE_EXHAUSTED" in message or "RATE LIMIT" in message:
        return 429

    if "UNAVAILABLE" in message:
        return 503

    return None


def generate_study_plan(
    courses,
    events,
    goals,
    available_hours_per_day: float,
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
            "start_date": str(event.start_date),
            "end_date": str(event.end_date) if event.end_date else None,
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
            "start_date": str(goal.start_date),
            "end_date": str(goal.end_date),
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

    # Haftalık hedef günlük kapasiteden büyükse
    # AI'ya gerçekçi maksimum süreyi bildiriyoruz.
    effective_weekly_target_minutes = min(
        weekly_target_minutes,
        maximum_weekly_minutes
    )

    effective_weekly_target_hours = (
        effective_weekly_target_minutes / 60
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

Öğrencinin uygulanabilir maksimum haftalık çalışma kapasitesi:
{maximum_weekly_minutes} dakika

Planlanması gereken haftalık çalışma süresi:
{effective_weekly_target_minutes} dakika
({effective_weekly_target_hours} saat)


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
   {daily_limit_minutes} dakikayı kesinlikle geçmemelidir.

4. Haftalık toplam çalışma süresi
   mümkün olduğunca tam olarak
   {effective_weekly_target_minutes} dakika olmalıdır.

5. Haftalık hedef günlük kapasiteden büyükse,
   günlük kapasiteyi aşma.
   Bu durumda maksimum uygulanabilir süreyi kullan.

6. Dersleri yalnızca öğrencinin gerçek
   ders listesinden seç.

7. Öğrencinin ders listesinde olmayan hiçbir
   ders oluşturma.

8. Ders isimlerini kesinlikle birleştirme.

   Örneğin:

   YANLIŞ:
   "Matematik ve Veri Yapıları"

   DOĞRU:
   "Matematik"

   veya:

   "Veri Yapıları"

9. Her plan öğesinde yalnızca BİR ders bulunmalıdır.

10. Bir güne birden fazla çalışma kaydı
    koyabilirsin.

11. Yaklaşan sınavlara öncelik ver.

12. Yaklaşan ödevlere öncelik ver.

13. Yaklaşan projelere öncelik ver.

14. Aktif hedefleri dikkate al.

15. Dersleri mümkün olduğunca dengeli dağıt.

16. Aynı dersi gereksiz şekilde her güne koyma.

17. Ancak yaklaşan sınav veya önemli bir
    deadline varsa ilgili derse daha fazla
    çalışma süresi ayırabilirsin.

18. Konu bilgisi verilmediği için konu
    uydurma.

19. Output içinde topics alanı bulunmayacaktır.

20. Her çalışma kaydının duration_minutes
    değeri gerçekçi olmalıdır.

21. Çalışma süreleri dakika cinsinden olmalıdır.

22. Her gün mutlaka çalışma kaydı oluşturmak
    zorunda değilsin.

23. Fakat 7 günlük plan içerisinde toplam
    çalışma süresini haftalık hedefe
    mümkün olduğunca tam olarak ulaştır.

24. Tamamlanmış hedefleri dikkate alma.

25. Tamamlanmış eventleri dikkate alma.

26. Verilmeyen bilgileri uydurma.

27. general_advice içerisinde yanlış bir
    haftalık toplam süre belirtme.

28. Planın toplam süresini hesaplarken
    duration_minutes değerlerini dikkate al.

29. Haftalık hedef:
    {effective_weekly_target_minutes} dakika.

30. Bu hedefi aşma.

31. Mümkünse bu hedefin altında da kalma.


==================================================
GEÇERLİ DERSLER
==================================================

course alanı SADECE aşağıdaki değerlerden
biri olabilir:

{course_names}


==================================================
ÇIKTI KURALLARI
==================================================

JSON dışında hiçbir şey döndürme.

weekly_plan içerisindeki her nesne şu alanlara
sahip olmalıdır:

- day
- course
- duration_minutes
- reason

topics ALANI KULLANMA.

Her nesnede yalnızca bir ders olmalıdır.

course değeri yukarıdaki gerçek derslerden
biri olmalıdır.

duration_minutes pozitif bir sayı olmalıdır.

general_advice kısa ve Türkçe olmalıdır.

Plan öğrencinin günlük ve haftalık çalışma
kapasitesini aşmamalıdır.
"""

    # ---------------------------------------------------------
    # GEMINI
    # ---------------------------------------------------------

    maximum_attempts = 3

    for attempt in range(1, maximum_attempts + 1):
        try:
            response = client.models.generate_content(
                model="gemini-3.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=PlannerResponse,
                ),
            )
            break
        except errors.APIError as error:
            transient_status = _transient_gemini_status(error)

            if transient_status is None:
                raise

            if attempt == maximum_attempts:
                raise PlannerServiceUnavailableError(
                    transient_status
                ) from error

            time.sleep(2 ** (attempt - 1))

    # ---------------------------------------------------------
    # AI CEVABI KONTROL
    # ---------------------------------------------------------

    if response.parsed is None:

        print("AI PLANNER RESPONSE PARSED NONE")
        print("AI RESPONSE TEXT:")
        print(response.text)

        raise ValueError(
            "AI Planner geçerli bir plan oluşturamadı."
        )

    result = response.parsed

    # ---------------------------------------------------------
    # BACKEND KONTROLLERİ
    # ---------------------------------------------------------

    valid_course_names = set(course_names)

    total_minutes = 0

    for item in result.weekly_plan:

        # Geçersiz ders kontrolü
        if item.course not in valid_course_names:

            raise ValueError(
                f"AI geçersiz bir ders oluşturdu: {item.course}"
            )

        # Günlük limit kontrolü daha aşağıda
        total_minutes += item.duration_minutes

    # ---------------------------------------------------------
    # HAFTALIK TOPLAM KONTROLÜ
    # ---------------------------------------------------------

    if total_minutes > effective_weekly_target_minutes:

        raise ValueError(
            f"AI haftalık çalışma hedefini aştı. "
            f"Hedef: {effective_weekly_target_minutes} dakika, "
            f"oluşturulan: {total_minutes} dakika."
        )

    # ---------------------------------------------------------
    # GÜNLÜK TOPLAM KONTROLÜ
    # ---------------------------------------------------------

    daily_totals = {}

    for item in result.weekly_plan:

        daily_totals[item.day] = (
            daily_totals.get(item.day, 0)
            + item.duration_minutes
        )

    for day, total in daily_totals.items():

        if total > daily_limit_minutes:

            raise ValueError(
                f"{day} günü günlük çalışma limitini aşıyor. "
                f"Limit: {daily_limit_minutes} dakika, "
                f"oluşturulan: {total} dakika."
            )

    # ---------------------------------------------------------
    # SONUÇ
    # ---------------------------------------------------------

    print(
        f"AI Planner oluşturuldu. "
        f"Haftalık toplam: {total_minutes} dakika / "
        f"{effective_weekly_target_minutes} dakika"
    )

    return result
