# -*- coding: utf-8 -*-
"""
AI Self-Healing сервис для автокликера.
Использует OpenRouter API с vision-моделью для:
- Альтернативного распознавания букв на колесе (когда EasyOCR не справляется)
- Определения состояния экрана (игра / реклама / меню)
- Генерации слов из букв (когда словарь не помог)
"""

import base64
import json
import time
import urllib.request
import urllib.error
import cv2
import numpy as np
from typing import List, Optional, Tuple

import config


class AIHealingService:
    """
    Self-healing сервис на базе OpenRouter API.
    Вызывается когда все штатные стратегии исчерпаны.
    """

    OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self):
        self.api_key = config.OPENROUTER_API_KEY
        self.model = config.AI_HEALING_MODEL
        self.timeout = config.AI_HEALING_TIMEOUT
        self.cooldown = config.AI_HEALING_COOLDOWN
        self.last_call_time = 0.0
        self._enabled = bool(self.api_key and config.AI_HEALING_ENABLED)

        if self._enabled:
            print(f"[AI Healing] Сервис инициализирован. Модель: {self.model}")
        else:
            if not self.api_key:
                print("[AI Healing] API ключ не задан. Сервис отключён.")
                print("             Для включения задайте OPENROUTER_API_KEY в файле .env")
            else:
                print("[AI Healing] Сервис отключён в настройках (AI_HEALING_ENABLED=False).")

    @property
    def is_enabled(self) -> bool:
        """Проверяет, доступен ли сервис."""
        return self._enabled

    def _can_call(self) -> bool:
        """Проверяет, прошёл ли cooldown с последнего вызова."""
        return time.time() - self.last_call_time >= self.cooldown

    def _encode_image(self, img_bgr: np.ndarray, quality: int = 70) -> str:
        """Кодирует изображение OpenCV в base64 JPEG строку."""
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, quality]
        _, buffer = cv2.imencode('.jpg', img_bgr, encode_params)
        return base64.b64encode(buffer).decode('utf-8')

    def _call_api(self, prompt: str, image_b64: Optional[str] = None, max_tokens: int = 300) -> Optional[str]:
        """
        Отправляет запрос к OpenRouter API.
        Возвращает текстовый ответ модели или None при ошибке.
        """
        if not self._enabled:
            return None

        if not self._can_call():
            remaining = self.cooldown - (time.time() - self.last_call_time)
            print(f"[AI Healing] Cooldown: ещё {remaining:.1f}с до следующего вызова.")
            return None

        self.last_call_time = time.time()

        # Формируем содержимое сообщения
        content = []
        if image_b64:
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{image_b64}"
                }
            })
        content.append({
            "type": "text",
            "text": prompt
        })

        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [
                {
                    "role": "user",
                    "content": content
                }
            ]
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/GhelgenWhy/OCR-autoclicker",
            "X-Title": "Word City Autoclicker"
        }

        try:
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(
                self.OPENROUTER_API_URL,
                data=data,
                headers=headers,
                method="POST"
            )

            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                result = json.loads(response.read().decode('utf-8'))

            # Извлекаем текст ответа
            choices = result.get("choices", [])
            if choices:
                message = choices[0].get("message", {})
                text = message.get("content", "")
                if text:
                    return text.strip()

            print("[AI Healing] Пустой ответ от API.")
            return None

        except urllib.error.HTTPError as e:
            error_body = ""
            try:
                error_body = e.read().decode('utf-8')
            except Exception:
                pass
            print(f"[AI Healing] HTTP ошибка {e.code}: {error_body[:200]}")
            return None
        except urllib.error.URLError as e:
            print(f"[AI Healing] Ошибка сети: {e.reason}")
            return None
        except Exception as e:
            print(f"[AI Healing] Неожиданная ошибка: {e}")
            return None

    def recognize_letters(self, screenshot_bgr: np.ndarray) -> List[str]:
        """
        Отправляет кроп области колеса букв в vision-модель для распознавания.
        Возвращает список отдельных букв (lowercase) или пустой список при ошибке.
        """
        if not self._enabled:
            return []

        # Вырезаем область колеса букв
        roi = config.CIRCLE_ROI
        crop = screenshot_bgr[roi["y"]:roi["y"]+roi["h"], roi["x"]:roi["x"]+roi["w"]]

        image_b64 = self._encode_image(crop)

        prompt = (
            "You are looking at a word game screen. There is a circle/wheel with individual "
            "letters arranged around it. Each letter is placed on a separate circular tile.\n\n"
            "TASK: List ONLY the individual letters you see on the circular tiles.\n"
            "FORMAT: Return letters separated by commas, lowercase. Example: a, b, c, d, e\n"
            "RULES:\n"
            "- Only include letters that are clearly on the circular wheel tiles\n"
            "- Do NOT include any text from buttons, labels, or UI elements\n"
            "- If a letter appears multiple times on separate tiles, list it multiple times\n"
            "- Return ONLY the comma-separated letters, nothing else"
        )

        print("[AI Healing] Распознавание букв через AI vision...")
        response = self._call_api(prompt, image_b64, max_tokens=100)

        if not response:
            return []

        # Парсим ответ — ожидаем формат "a, b, c, d, e"
        letters = []
        # Убираем возможные markdown/thinking блоки
        clean = response.strip()
        # Если ответ содержит переводы строк, берём последнюю непустую строку
        lines = [l.strip() for l in clean.split('\n') if l.strip()]
        if lines:
            # Берём строку, которая больше всего похожа на список букв
            best_line = lines[-1]
            for line in lines:
                # Ищем строку с запятыми (формат ответа)
                if ',' in line and len(line) < 50:
                    best_line = line
                    break

            parts = best_line.replace(' ', '').split(',')
            for part in parts:
                char = part.strip().lower()
                if len(char) == 1 and char.isalpha():
                    letters.append(char)

        if letters:
            print(f"[AI Healing] AI распознал буквы: {letters}")
        else:
            print(f"[AI Healing] Не удалось распарсить ответ AI: '{response[:100]}'")

        return letters

    def detect_screen_state(self, screenshot_bgr: np.ndarray) -> str:
        """
        Определяет текущее состояние экрана: 'game', 'ad', 'menu', 'level_complete'.
        Используется когда стандартные методы не могут определить ситуацию.
        """
        if not self._enabled:
            return "unknown"

        image_b64 = self._encode_image(screenshot_bgr, quality=50)

        prompt = (
            "You are looking at a mobile phone screenshot. Determine the current screen state.\n\n"
            "Possible states:\n"
            "- 'game' — A word puzzle game is visible with a letter wheel at the bottom\n"
            "- 'ad' — An advertisement is showing (banner, video ad, interstitial)\n"
            "- 'menu' — A game menu, settings, or popup dialog\n"
            "- 'level_complete' — A level completion screen with congratulations or next button\n\n"
            "Return ONLY one of these exact words: game, ad, menu, level_complete"
        )

        print("[AI Healing] Определение состояния экрана через AI...")
        response = self._call_api(prompt, image_b64, max_tokens=50)

        if not response:
            return "unknown"

        # Парсим ответ
        clean = response.strip().lower()
        valid_states = {"game", "ad", "menu", "level_complete"}

        # Ищем точное совпадение
        for state in valid_states:
            if state in clean:
                print(f"[AI Healing] Состояние экрана: {state}")
                return state

        print(f"[AI Healing] Неизвестное состояние: '{response[:50]}'")
        return "unknown"

    def solve_with_ai(self, letters: List[str]) -> List[str]:
        """
        Просит AI составить английские слова из заданных букв.
        Fallback когда словарь и веб-поиск не помогли.
        Возвращает список слов (отсортированных по длине, длинные первыми).
        """
        if not self._enabled:
            return []

        letters_str = ", ".join(letters)

        prompt = (
            f"You are helping solve a word puzzle game.\n"
            f"Available letters: {letters_str}\n\n"
            f"TASK: List ALL valid English words (3+ letters) that can be made using ONLY these letters.\n"
            f"Each letter can only be used as many times as it appears in the list.\n"
            f"FORMAT: Return words separated by commas, lowercase. Example: word, cat, dog\n"
            f"RULES:\n"
            f"- Only common English words (no proper nouns, no abbreviations)\n"
            f"- Minimum 3 letters per word\n"
            f"- Each letter used at most as many times as available\n"
            f"- Return ONLY the comma-separated words, nothing else\n"
            f"- List longer words first"
        )

        print(f"[AI Healing] Генерация слов из букв {letters} через AI...")
        response = self._call_api(prompt, max_tokens=500)

        if not response:
            return []

        # Парсим ответ
        words = []
        clean = response.strip()
        lines = [l.strip() for l in clean.split('\n') if l.strip()]

        if lines:
            # Ищем строку с запятыми
            best_line = lines[-1]
            for line in lines:
                if ',' in line:
                    best_line = line
                    break

            parts = best_line.split(',')
            for part in parts:
                word = part.strip().lower()
                if len(word) >= 3 and word.isalpha():
                    words.append(word)

        # Сортируем по длине (длинные первыми)
        words.sort(key=lambda w: len(w), reverse=True)

        if words:
            print(f"[AI Healing] AI предложил {len(words)} слов: {words[:10]}{'...' if len(words) > 10 else ''}")
        else:
            print(f"[AI Healing] Не удалось извлечь слова из ответа AI: '{response[:100]}'")

        return words
