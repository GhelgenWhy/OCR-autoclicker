# -*- coding: utf-8 -*-
"""
Конфигурационный файл для автокликера игры "Word City: Connect Word Game".
Все ключевые константы, пути и пороги чувствительности вынесены сюда.
"""

import os

# --- Настройки подключения устройства ---
# Если подключено только одно устройство через USB, можно оставить None
# Иначе укажите серийный номер из `adb devices` или IP-адрес для Wi-Fi (например, "192.168.1.100:5555")
DEVICE_SERIAL = None

# --- Настройки области поиска (ROI - Region of Interest) ---
# Область экрана, в которой расположен круг с буквами.
# Задается в виде координат bounding box (x, y, width, height) для скриншота.
# Эти значения ориентированы на стандартные разрешения (например, 1080x2400)
# и должны быть скорректированы пользователем с помощью calibrate.py.
CIRCLE_ROI = {
    "x": 220,  # Смещение по X от левого края экрана
    "y": 1540,  # Смещение по Y от верхнего края экрана (нижняя половина экрана)
    "w": 770,  # Ширина области круга
    "h": 750,  # Высота области круга
}

# --- Параметры обработки OpenCV ---
# Порог бинаризации изображения (Threshold) для выделения контуров букв
# Рекомендуется использовать адаптивный порог или обычный сглаженный
BINARY_THRESHOLD = 120

# Фильтрация контуров по площади (в пикселях), чтобы отсечь мусор и слишком большие объекты
MIN_LETTER_AREA = 500
MAX_LETTER_AREA = 12000

# Коэффициент масштабирования вырезанной буквы перед отправкой в EasyOCR.
# EasyOCR работает лучше, когда буквы крупные и имеют отступы (padding)
OCR_LETTER_SCALE = 2.0
OCR_LETTER_PADDING = 10

# Режим распознавания: True = вырезать каждый контур и распознавать отдельно (точнее, ловит 'I')
# False = распознавать всю ROI-область одним вызовом EasyOCR (быстрее, но теряет тонкие буквы)
OCR_CROP_MODE = True

# Диапазон адаптивного порога бинаризации: если основной порог не нашёл достаточно букв,
# бот повторит с порогами BINARY_THRESHOLD ± каждое значение из списка
ADAPTIVE_THRESHOLD_OFFSETS = [25, 50]

# --- Настройки EasyOCR ---
# Список языков для распознавания текста (используем только английский)
OCR_LANGUAGES = ["en"]

# --- Шаблоны и папки ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
SCREENSHOTS_DIR = os.path.join(BASE_DIR, "debug_screenshots")
WORDS_FILE = os.path.join(BASE_DIR, "words.txt")

# Создаем папки, если они не существуют
os.makedirs(TEMPLATES_DIR, exist_ok=True)
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

# --- Настройки поиска шаблонов (Template Matching) ---
# Порог уверенности для OpenCV matchTemplate (от 0.0 до 1.0)
TEMPLATE_THRESHOLD = 0.75

# --- Настройки Watchdog (Защита от рекламы и Play Market) ---
# Известные пакеты Play Market и браузеров для принудительного возврата
SUSPICIOUS_PACKAGES = [
    "com.android.vending",  # Google Play Store
    "com.chrome.android",  # Google Chrome
    "org.mozilla.firefox",  # Firefox
    "com.android.chrome",  # Chrome
    "com.opera.browser",  # Opera
    "com.sec.android.app.sbrowser",  # Samsung Internet
]

# Имя пакета игры (чтобы знать, запущена ли она)
# Пакет для "Word City: Connect Word Game" обычно "com.fugo.wordcity" (может отличаться)
GAME_PACKAGE = "com.fugo.wordcity"

# --- Настройки таймингов, скорости и логики ввода (Настраивайте под себя) ---
WATCHDOG_INTERVAL = 1.0  # Интервал проверки рекламы фоновым потоком (секунды)
SWIPE_DURATION = 0.015  # Длительность свайпа между двумя буквами (секунды одного перехода)
SWIPE_HOLD_LAST = True  # Удерживать ли последнюю букву перед отпусканием (позволяет избежать обрезки ввода)
SWIPE_DELAY = 0.25  # Пауза после ввода каждого слова (секунды)
ACTION_DELAY = 0.05  # Пауза перед проверкой переходов на новый уровень (секунды)

# Лимит группировки слов для ввода (Grouped Swiping):
# Число (например, 3) - вводить по N слов и делать проверку экрана.
# 0 или None - вводить сразу ВСЕ слова без промежуточных скриншотов и пауз.
SWIPE_GROUP_SIZE = 5
