# -*- coding: utf-8 -*-
"""
Конфигурационный файл для автокликера игры "Word City: Connect Word Game".
Все ключевые константы, пути и пороги чувствительности вынесены сюда.
"""

import os

# Загрузка переменных окружения из .env файла
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass  # python-dotenv не установлен — переменные окружения читаются напрямую

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

# Паддинг вокруг вырезанной буквы перед отправкой в EasyOCR
OCR_LETTER_PADDING = 10

# Режим распознавания: True = вырезать каждый контур и распознавать отдельно (точнее, ловит 'I')
# False = распознавать всю ROI-область одним вызовом EasyOCR (быстрее, но теряет тонкие буквы)
OCR_CROP_MODE = True

# Диапазон адаптивного порога бинаризации: если основной порог не нашёл достаточно букв,
# бот повторит с порогами BINARY_THRESHOLD ± каждое значение из списка
ADAPTIVE_THRESHOLD_OFFSETS = [25, 50]

# Максимальное количество уникальных букв на колесе (для валидации OCR)
# Если распознано больше — результат считается мусором (вероятно, текст рекламы)
MAX_UNIQUE_LETTERS = 10

# --- Настройки EasyOCR ---
# Список языков для распознавания текста (используем только английский)
OCR_LANGUAGES = ["en"]

# --- Шаблоны и папки ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
SCREENSHOTS_DIR = os.path.join(BASE_DIR, "debug_screenshots")
WORDS_FILE = os.path.join(BASE_DIR, "words.txt")
LEVEL_STATE_FILE = os.path.join(BASE_DIR, "level_state.json")

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

# Имя пакета игры (используется для точной проверки, что мы в игре)
GAME_PACKAGE = "com.fugo.wordcity"

# Доля экрана по высоте для поиска рекламных крестиков (1.0 = весь экран)
# Некоторые рекламы (например, от Google) могут располагать кнопки закрытия в нижней части экрана
AD_SEARCH_REGION_RATIO = 1.0

# Пауза основного цикла после обнаружения рекламы Watchdog-ом (секунды)
# Предотвращает OCR по тексту рекламы, которая ещё не закрылась
AD_COOLDOWN_SECONDS = 3.0

# Максимальное число кликов по одному шаблону за период (защита от ложных срабатываний)
AD_TEMPLATE_CLICK_LIMIT = 3  # Максимум кликов
AD_TEMPLATE_CLICK_WINDOW = 20.0  # За сколько секунд

# --- Настройки таймингов, скорости и логики ввода (Настраивайте под себя) ---
WATCHDOG_INTERVAL = 1.0  # Интервал проверки рекламы фоновым потоком (секунды)
SWIPE_DURATION = (
    0.015  # Длительность свайпа между двумя буквами (секунды одного перехода)
)
SWIPE_HOLD_LAST = True  # Удерживать ли последнюю букву перед отпусканием (позволяет избежать обрезки ввода)
SWIPE_DELAY = 0.25  # Пауза после ввода каждого слова (секунды)
ACTION_DELAY = 0.05  # Пауза перед проверкой переходов на новый уровень (секунды)

# Лимит группировки слов для ввода (Grouped Swiping):
# Число (например, 3) - вводить по N слов и делать проверку экрана.
# 0 или None - вводить сразу ВСЕ слова без промежуточных скриншотов и пауз.
SWIPE_GROUP_SIZE = 5

# --- Методы сопоставления шаблонов (Template Matching) ---
# Доступные значения: "bgr", "hsv", "sobel"
# "bgr" - стандартный цветной поиск (быстро, чувствителен к свету/градиенту)
# "hsv" - поиск в цветовом пространстве HSV (может быть стабильнее при изменении яркости)
# "sobel" - поиск по контурам (фильтр Собеля; идеален для кнопок на градиентном фоне)
NAV_BUTTONS_MATCH_METHOD = "bgr"  # Для кнопок навигации (Next, Continue)
AD_CLOSE_MATCH_METHOD = "sobel"  # Для рекламных крестиков (Close)

# --- Настройки при застревании бота на уровне ---
STUCK_LOCAL_FALLBACK_LIMIT = (
    2  # Через сколько попыток ввода веб-слов переходить на локальный словарь
)
STUCK_RESET_LIMIT = 4  # Через сколько попыток сбрасывать уровень и пересканировать OCR
STUCK_AI_HEALING_LIMIT = 6  # Через сколько попыток вызывать AI Self-Healing (после исчерпания всех стратегий)

# --- AI Self-Healing (OpenRouter) ---
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
AI_HEALING_ENABLED = True  # Включить AI Self-Healing (требуется API ключ)
AI_HEALING_MODEL = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"
AI_HEALING_TIMEOUT = 15  # Таймаут HTTP запроса к OpenRouter (секунды)
AI_HEALING_COOLDOWN = 10  # Минимальный интервал между вызовами AI (секунды)

# --- Отладка ---
SHOW_TAPS = True  # Включить отображение нажатий на экране устройства (Developer Options → Show taps)
