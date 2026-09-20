import unittest
from app.services.quiz_generation_service import Evidence, QuizQuestion, validate_question, _is_meta_instruction_question

class MetaInstructionTests(unittest.TestCase):
    def validate(self, text):
        evidence = Evidence(1, 'Düşük faiz oranları yatırımları artırarak ekonomik büyümeyi destekler.', 0, 3.0)
        question = QuizQuestion(1, text, ('Yatırımları artırarak ekonomik büyümeyi destekler', 'Yatırımları azaltır', 'Üretimi durdurur', 'İşsizliği artırır', 'Ticareti engeller'), 0)
        return validate_question(question, {1: evidence}, set(), set())

    def test_rejects_question_writing_requests(self):
        for text in (
            'Düşük faiz oranlarının ekonomik büyümeye nasıl katkıda bulunabileceğini soran bir soru oluşturun?',
            'Ekonomi hakkında bir soru oluştur?', 'Bu konu için soru hazırlayın?',
            'Bir soru yaz?', 'Bir soru yazınız?', 'Bu konuda soru üretiniz?',
            'Bir soru oluşturur musunuz?', 'Bir soru yazar mısınız?',
            'Bir soru hazırlar mısınız?', 'BİR SORU YAZINIZ?',
            'Bir soru oluşturun lütfen?',
            'Generate a question about low interest rates?',
            'Create a question about growth?',
            'Please write a quiz question about investment?',
            'Could you please formulate a multiple-choice question?',
            'Compose an exam question?',
        ):
            with self.subTest(text=text):
                self.assertEqual(self.validate(text), (False, 'meta_instruction_question'))

    def test_real_student_question_is_accepted(self):
        self.assertEqual(self.validate('Düşük faiz oranları ekonomik büyümeyi nasıl etkiler?'), (True, 'accepted'))

    def test_discussion_of_questions_is_not_a_writing_request(self):
        for text in (
            'Soru oluşturmanın öğrenmeye katkısı nedir?',
            'Bir soru hazırlayan öğretmen hangi ölçütü kullanır?',
            'Öğretmen neden soru yazmıştır?', 'Kim soru yazar?',
            'How do low interest rates affect economic growth?',
            'How does a teacher create a question?',
            'Who asked the students to generate a question?',
            'What does the instruction "create a question" mean?',
        ):
            with self.subTest(text=text):
                self.assertFalse(_is_meta_instruction_question(text))
