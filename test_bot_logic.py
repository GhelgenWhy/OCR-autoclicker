# -*- coding: utf-8 -*-
"""
Модульные тесты для проверки внутренней логики bot.py и utils.py.
"""

import unittest
import sys
from unittest.mock import MagicMock

# Мокаем тяжелые бинарные зависимости для запуска тестов без установки OpenCV/EasyOCR/uiautomator2
sys.modules['cv2'] = MagicMock()
sys.modules['uiautomator2'] = MagicMock()
sys.modules['easyocr'] = MagicMock()

from bot import clean_ocr_text, get_word_swipe_path, _guess_letter_by_shape
from utils import solve_anagrams, get_expected_letter_counts

class TestBotLogic(unittest.TestCase):
    
    def test_clean_ocr_text(self):
        """Проверка очистки распознанных EasyOCR символов."""
        self.assertEqual(clean_ocr_text(" 0 "), "o")
        self.assertEqual(clean_ocr_text("1"), "i")
        self.assertEqual(clean_ocr_text(" 8"), "b")
        self.assertEqual(clean_ocr_text("5"), "s")
        self.assertEqual(clean_ocr_text(" | "), "i")
        self.assertEqual(clean_ocr_text("A"), "a")
        self.assertEqual(clean_ocr_text("!@#"), "i")  # ! -> i (новый маппинг)
        self.assertEqual(clean_ocr_text("123"), "i")  # Берет первый подходящий
        self.assertEqual(clean_ocr_text("???"), "")   # Нет букв
        
    def test_clean_ocr_text_extended_mappings(self):
        """Проверка расширенного маппинга ошибок OCR."""
        self.assertEqual(clean_ocr_text("!"), "i")   # ! -> i
        self.assertEqual(clean_ocr_text("/"), "i")   # / -> i
        self.assertEqual(clean_ocr_text("\\"), "i")  # \ -> i
        self.assertEqual(clean_ocr_text("["), "i")   # [ -> i
        self.assertEqual(clean_ocr_text("]"), "i")   # ] -> i
        self.assertEqual(clean_ocr_text("6"), "g")   # 6 -> g
        self.assertEqual(clean_ocr_text("9"), "g")   # 9 -> g
        self.assertEqual(clean_ocr_text("7"), "t")   # 7 -> t
        self.assertEqual(clean_ocr_text("("), "c")   # ( -> c
        
    def test_get_word_swipe_path(self):
        """Проверка построения пути для свайпа с учетом повторяющихся букв."""
        # Расположенные буквы на экране (с координатами)
        letter_positions = [
            ('w', (100, 100)),
            ('o', (200, 100)),
            ('o', (300, 100)),
            ('d', (400, 100)),
            ('s', (500, 100))
        ]
        
        # 1. Простое слово
        path = get_word_swipe_path("sow", letter_positions)
        self.assertEqual(path, [(500, 100), (200, 100), (100, 100)])
        
        # 2. Слово с повторяющимися буквами ("wood")
        path_wood = get_word_swipe_path("wood", letter_positions)
        # Должен использовать разные координаты для двух 'o'
        self.assertEqual(path_wood, [(100, 100), (200, 100), (300, 100), (400, 100)])
        
        # 3. Слово, буквы которого отсутствуют
        path_invalid = get_word_swipe_path("word", letter_positions)  # Нет буквы 'r'
        self.assertEqual(path_invalid, [])
        
    def test_solve_anagrams(self):
        """Проверка решения анаграмм с ограничением частот букв."""
        dictionary = {"wood", "woods", "sow", "word", "door", "woo", "do"}
        # Набор букв: w, o, o, d, s
        letters = ['w', 'o', 'o', 'd', 's']
        
        solutions = solve_anagrams(letters, dictionary)
        
        # "woods" (5 букв), "wood" (4 буквы), "door" (4 буквы, нет 'r' в наборе -> не должно быть в ответах),
        # "sow" (3 буквы), "woo" (3 буквы), "do" (2 буквы -> слишком короткое, отсекается)
        self.assertIn("woods", solutions)
        self.assertIn("wood", solutions)
        self.assertIn("sow", solutions)
        self.assertIn("woo", solutions)
        self.assertNotIn("door", solutions)
        self.assertNotIn("do", solutions)
        
        # Проверка сортировки: сначала длинные
        self.assertEqual(solutions[0], "woods")
        self.assertEqual(solutions[1], "wood")

    def test_guess_letter_by_shape(self):
        """Проверка эвристики определения буквы 'I' по aspect ratio."""
        # Очень узкий и высокий контур -> должно вернуть 'i'
        self.assertEqual(_guess_letter_by_shape((0, 0, 15, 60)), 'i')  # ratio = 0.25
        self.assertEqual(_guess_letter_by_shape((0, 0, 20, 60)), 'i')  # ratio = 0.33
        
        # Обычные буквы — не I
        self.assertEqual(_guess_letter_by_shape((0, 0, 40, 60)), '')  # ratio = 0.67
        self.assertEqual(_guess_letter_by_shape((0, 0, 50, 50)), '')  # ratio = 1.0
        
        # Граничный случай: высота 0
        self.assertEqual(_guess_letter_by_shape((0, 0, 10, 0)), '')
        
    def test_get_expected_letter_counts(self):
        """Проверка вычисления количества букв на колесе."""
        words = ["hide", "hid", "die", "hi"]
        counts = get_expected_letter_counts(words)
        
        # 'h' max(1,1,0,1) = 1
        # 'i' max(1,1,1,1) = 1
        # 'd' max(1,1,1,0) = 1
        # 'e' max(1,0,1,0) = 1
        self.assertEqual(counts['h'], 1)
        self.assertEqual(counts['i'], 1)
        self.assertEqual(counts['d'], 1)
        self.assertEqual(counts['e'], 1)
        
    def test_get_expected_letter_counts_duplicates(self):
        """Проверка подсчёта для слов с дублями букв."""
        words = ["add", "dad"]
        counts = get_expected_letter_counts(words)
        
        # 'a' max(1,1) = 1
        # 'd' max(2,2) = 2
        self.assertEqual(counts['a'], 1)
        self.assertEqual(counts['d'], 2)

    def test_load_dictionary_plural_generation(self):
        """Проверка динамического добавления форм множественного числа."""
        import utils
        from unittest.mock import patch, mock_open, MagicMock

        # Тестовые слова с разными типами окончаний
        mock_file_content = "wood\nbox\nfly\nbus\n"
        mock_response = MagicMock()
        mock_response.__enter__.return_value = mock_response
        mock_response.read.return_value = b"wood\nbox\nfly\nbus\n"

        with patch("os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=mock_file_content)), \
             patch("urllib.request.urlopen", return_value=mock_response):
            # Загружаем словарь
            dictionary = utils.load_dictionary()

            # Должны присутствовать оригинальные слова
            self.assertIn("wood", dictionary)
            self.assertIn("box", dictionary)
            self.assertIn("fly", dictionary)
            self.assertIn("bus", dictionary)

            # Должны быть сгенерированы правильные формы по правилам
            self.assertIn("woods", dictionary)    # wood + s
            self.assertIn("boxes", dictionary)    # box + es
            self.assertIn("flies", dictionary)    # fly -> flies
            self.assertIn("buses", dictionary)    # bus + es

if __name__ == "__main__":
    unittest.main()
