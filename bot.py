# -*- coding: utf-8 -*-
"""
Основной бот bot.py для автопрохождения игры "Word City: Connect Word Game".
Управляет процессом распознавания букв, генерации ответов, свайпов и борьбы с рекламой.
"""

import os
import sys
import time
import json
import threading
import cv2
import numpy as np
import uiautomator2 as u2

import config
import utils

# Глобальный замок для синхронизации доступа к устройству между основным потоком и watchdog
device_lock = threading.Lock()
stop_event = threading.Event()

# Timestamp, до которого основной цикл НЕ запускает OCR (после обнаружения рекламы)
ad_cooldown_until = 0.0
ad_cooldown_lock = threading.Lock()

try:
    import msvcrt
except ImportError:
    msvcrt = None

def check_pause():
    """
    Проверяет нажатие клавиши паузы (Пробел или 'P') во входном буфере консоли.
    При обнаружении приостанавливает выполнение до повторного нажатия.
    """
    if msvcrt and msvcrt.kbhit():
        try:
            # Считываем нажатую клавишу
            key = msvcrt.getch()
            # Нажата ли пауза (пробел или p / P)
            if key in (b' ', b'p', b'P'):
                print("\n" + "=" * 55)
                print("[ПАУЗА] Бот приостановлен пользователем.")
                print("        Нажмите ПРОБЕЛ или 'P' для возобновления работы...")
                print("=" * 55)
                # Ждем повторного нажатия
                while True:
                    time.sleep(0.1)
                    if msvcrt.kbhit():
                        next_key = msvcrt.getch()
                        if next_key in (b' ', b'p', b'P'):
                            print("[СТАРТ] Бот возобновлен. Продолжаем...\n")
                            break
        except Exception as e:
            print(f"[!] Ошибка обработки клавиши паузы: {e}")

def connect_device():
    """Подключается к устройству."""
    try:
        if config.DEVICE_SERIAL:
            d = u2.connect(config.DEVICE_SERIAL)
        else:
            d = u2.connect()
        print(f"[+] Бот успешно подключен к устройству: {d.info.get('productName')}")
        return d
    except Exception as e:
        print(f"[!] Ошибка подключения: {e}")
        sys.exit(1)

def take_screenshot(d):
    """
    Делает скриншот устройства. Пытается получить его сразу в формате OpenCV BGR
    (это работает быстрее и не требует ручной конвертации PIL -> numpy).
    Если не удается, делает стандартный скриншот и конвертирует его.
    """
    with device_lock:
        try:
            return d.screenshot(format="opencv")
        except Exception:
            pil_img = d.screenshot()
            return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

def get_sobel_edges(img):
    """
    Вычисляет градиенты Собеля по направлениям X и Y, объединяет их
    для получения контуров изображения (помогает игнорировать градиенты фона).
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    sobelx = cv2.Sobel(blurred, cv2.CV_8U, 1, 0, ksize=3)
    sobely = cv2.Sobel(blurred, cv2.CV_8U, 0, 1, ksize=3)
    return cv2.addWeighted(sobelx, 0.5, sobely, 0.5, 0)

def find_template_on_screen(screen_bgr, template_path, threshold=config.TEMPLATE_THRESHOLD,
                            method="bgr", search_region=None):
    """
    Ищет изображение-шаблон на скриншоте экрана.
    Поддерживает методы:
      - "bgr": сопоставление по исходным цветам BGR
      - "hsv": сопоставление по цветовому пространству HSV (3 канала)
      - "sobel": сопоставление по контурам Собеля (устойчиво к градиентным фонам)

    search_region: (y_start, y_end) — ограничить поиск по вертикали (опционально).
    Возвращает (x, y) центра совпадения и коэффициент уверенности, или (None, 0.0).
    """
    if not os.path.exists(template_path):
        return None, 0.0
        
    template_img = cv2.imread(template_path)
    if template_img is None:
        return None, 0.0

    # Ограничиваем область поиска, если задано
    if search_region:
        y_start, y_end = search_region
        search_area = screen_bgr[y_start:y_end, :]
        y_offset = y_start
    else:
        search_area = screen_bgr
        y_offset = 0
        
    # Размеры шаблона
    h_t, w_t = template_img.shape[:2]

    # Проверяем что область поиска достаточна для шаблона
    if search_area.shape[0] < h_t or search_area.shape[1] < w_t:
        return None, 0.0
    
    # Предобработка скриншота и шаблона в зависимости от метода
    method_lower = method.lower()
    if method_lower == "sobel":
        s_processed = get_sobel_edges(search_area)
        t_processed = get_sobel_edges(template_img)
    elif method_lower == "hsv":
        s_processed = cv2.cvtColor(search_area, cv2.COLOR_BGR2HSV)
        t_processed = cv2.cvtColor(template_img, cv2.COLOR_BGR2HSV)
    else:
        s_processed = search_area
        t_processed = template_img

    # Шаблонный поиск
    res = cv2.matchTemplate(s_processed, t_processed, cv2.TM_CCOEFF_NORMED)
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
    
    if max_val >= threshold:
        cx = max_loc[0] + w_t // 2
        cy = max_loc[1] + h_t // 2 + y_offset  # Добавляем смещение по Y
        return (cx, cy), max_val
        
    return None, max_val


def check_for_navigation_buttons(d, screen_bgr):
    """
    Проверяет наличие кнопок на экране.
    Различает два типа:
      - "next_level": кнопка перехода на следующий уровень (шаблоны с 'next' или 'ok' в имени)
      - "tap_continue": промежуточная кнопка 'tap to continue' (шаблоны 'continue_*')
    Возвращает (pos, filename, button_type) или (None, None, None).
    """
    next_templates = []      # Кнопки перехода на след. уровень
    continue_templates = []  # Промежуточные 'tap to continue'
    
    if os.path.exists(config.TEMPLATES_DIR):
        for f in os.listdir(config.TEMPLATES_DIR):
            name_lower = f.lower()
            full_path = os.path.join(config.TEMPLATES_DIR, f)
            if "next" in name_lower or "ok" in name_lower:
                next_templates.append(full_path)
            elif "continue" in name_lower:
                continue_templates.append(full_path)
    
    # Сначала проверяем кнопку Next (приоритет — переход на уровень)
    for t_path in next_templates:
        pos, score = find_template_on_screen(screen_bgr, t_path, method=config.NAV_BUTTONS_MATCH_METHOD)
        if pos:
            return pos, os.path.basename(t_path), "next_level"
    
    # Затем промежуточные continue
    for t_path in continue_templates:
        pos, score = find_template_on_screen(screen_bgr, t_path, method=config.NAV_BUTTONS_MATCH_METHOD)
        if pos:
            return pos, os.path.basename(t_path), "tap_continue"
            
    return None, None, None


def _set_ad_cooldown():
    """Выставляет cooldown для основного цикла после обнаружения рекламы."""
    global ad_cooldown_until
    with ad_cooldown_lock:
        ad_cooldown_until = time.time() + config.AD_COOLDOWN_SECONDS


def _is_ad_cooldown_active() -> bool:
    """Проверяет, активен ли cooldown после рекламы."""
    with ad_cooldown_lock:
        return time.time() < ad_cooldown_until


def watchdog_worker(d, stop_event):
    """
    Фоновый поток (Watchdog).
    Быстро проверяет:
    1. Не сменилось ли приложение на Google Play / браузер (если да, шлет "back").
    2. Нет ли на экране рекламных крестиков [X] (если да, кликает по ним).

    Улучшения:
    - Ограничение зоны поиска шаблонов (верхние 25% экрана)
    - Cooldown по шаблонам: не кликать один шаблон более N раз за M секунд
    - Выставление ad_cooldown для основного цикла
    """
    print("[*] Поток Watchdog запущен.")

    # Словарь для отслеживания кликов по каждому шаблону: {template_name: [timestamp, ...]}
    template_click_history = {}

    while not stop_event.is_set():
        try:
            # 1. Проверяем текущее активное приложение (дешёвая операция — делаем первой)
            with device_lock:
                app = d.app_current()
                
            package_name = app.get("package") if app else None
            
            if package_name:
                # Проверяем, находится ли пакет в списке подозрительных
                is_suspicious = False
                for susp in config.SUSPICIOUS_PACKAGES:
                    if susp in package_name:
                        is_suspicious = True
                        break
                
                # Если свернулась игра и открылся Play Market/браузер
                if is_suspicious:
                    print(f"[Watchdog] Нежелательное приложение в фокусе: {package_name}. Отправляем кнопку BACK...")
                    with device_lock:
                        d.press("back")
                    _set_ad_cooldown()
                    time.sleep(1.0)
                    continue

            # 2. Сканируем экран на наличие кнопок (навигационных и крестиков рекламы)
            screen_bgr = take_screenshot(d)
            screen_h = screen_bgr.shape[0]

            # Ограничиваем область поиска крестиков рекламы (если настроено)
            if config.AD_SEARCH_REGION_RATIO and config.AD_SEARCH_REGION_RATIO < 1.0:
                ad_search_y_end = int(screen_h * config.AD_SEARCH_REGION_RATIO)
                search_region = (0, ad_search_y_end)
            else:
                search_region = None
            
            # Собираем шаблоны
            nav_templates = []
            x_templates = []
            if os.path.exists(config.TEMPLATES_DIR):
                for f in os.listdir(config.TEMPLATES_DIR):
                    name_lower = f.lower()
                    full_path = os.path.join(config.TEMPLATES_DIR, f)
                    if "next" in name_lower or "ok" in name_lower or "continue" in name_lower:
                        nav_templates.append(full_path)
                    elif name_lower.startswith(("close", "x", "ad_close")):
                        x_templates.append(full_path)
            
            clicked = False
            
            # 2.1. Сначала проверяем навигационные кнопки (Next, Continue) — приоритет!
            for t_path in nav_templates:
                t_name = os.path.basename(t_path)
                pos, score = find_template_on_screen(
                    screen_bgr, t_path,
                    method=config.NAV_BUTTONS_MATCH_METHOD
                )
                if pos:
                    print(f"[Watchdog] Обнаружена навигационная кнопка ({t_name}) с уверенностью {score:.2f}. Кликаем {pos}...")
                    with device_lock:
                        d.click(pos[0], pos[1])
                    _set_ad_cooldown()
                    time.sleep(1.0)
                    clicked = True
                    break
            
            if clicked:
                continue
            
            # 2.2. Затем проверяем рекламные крестики
            for t_path in x_templates:
                t_name = os.path.basename(t_path)

                # Проверяем cooldown по шаблону: не кликали ли мы его слишком часто
                now = time.time()
                if t_name in template_click_history:
                    # Удаляем устаревшие записи
                    template_click_history[t_name] = [
                        ts for ts in template_click_history[t_name]
                        if now - ts < config.AD_TEMPLATE_CLICK_WINDOW
                    ]
                    if len(template_click_history[t_name]) >= config.AD_TEMPLATE_CLICK_LIMIT:
                        # Слишком много кликов по этому шаблону — пропускаем
                        continue

                pos, score = find_template_on_screen(
                    screen_bgr, t_path,
                    method=config.AD_CLOSE_MATCH_METHOD,
                    search_region=search_region
                )
                if pos:
                    print(f"[Watchdog] Обнаружен рекламный крестик ({t_name}) с уверенностью {score:.2f}. Закрываем рекламу по координатам {pos}...")
                    with device_lock:
                        d.click(pos[0], pos[1])

                    # Записываем клик в историю
                    if t_name not in template_click_history:
                        template_click_history[t_name] = []
                    template_click_history[t_name].append(now)

                    _set_ad_cooldown()
                    time.sleep(1.0)
                    break  # Переходим к следующему циклу watchdog
                    
        except Exception as e:
            # Предотвращаем падение потока при временных ошибках ADB
            print(f"[Watchdog Warning] Ошибка в фоновом потоке: {e}")
            
        time.sleep(config.WATCHDOG_INTERVAL)
        
    print("[*] Поток Watchdog остановлен.")

def clean_ocr_text(text: str) -> str:
    """Очищает и корректирует типичные ошибки EasyOCR для одиночных букв."""
    text = text.strip().lower()
    
    # Расширенный маппинг ошибочных символов на правильные буквы
    char_corrections = {
        '0': 'o',
        '1': 'i',
        '8': 'b',
        '5': 's',
        '3': 'e',
        '|': 'i',
        '$': 's',
        '+': 't',
        '#': 'h',
        '*': 'x',
        '!': 'i',    # EasyOCR часто путает I с !
        '(': 'c',    # Скобка → C
        '{': 'c',
        '6': 'g',    # 6 → G
        '9': 'g',    # 9 → G
        '2': 'z',    # 2 → Z
        '7': 't',    # 7 → T
        '4': 'a',    # 4 → A
        '/': 'i',    # Slash → I
        '\\': 'i',   # Backslash → I
        '[': 'i',    # Bracket → I (вертикальная линия)
        ']': 'i',    # Bracket → I
        'l': 'l',    # Оставляем L как L (не путаем с I здесь)
    }
    
    # Если EasyOCR вернул один символ — обрабатываем быстро
    if len(text) == 1:
        corrected = char_corrections.get(text, text)
        return corrected if corrected.isalpha() else ""
    
    # Если EasyOCR вернул несколько символов, берем первый подходящий буквенный
    for char in text:
        corrected = char_corrections.get(char, char)
        if corrected.isalpha():
            return corrected
            
    return ""


def _find_contours_with_threshold(roi_gray, threshold_value):
    """
    Находит контуры букв в ROI с заданным порогом бинаризации.
    Возвращает список контуров, прошедших фильтрацию по площади и расстоянию до центра.
    """
    h_roi, w_roi = roi_gray.shape[:2]
    cx_roi, cy_roi = w_roi // 2, h_roi // 2
    
    blurred = cv2.GaussianBlur(roi_gray, (5, 5), 0)
    _, thresh = cv2.threshold(blurred, threshold_value, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    valid_contours = []
    for c in contours:
        area = cv2.contourArea(c)
        if config.MIN_LETTER_AREA <= area <= config.MAX_LETTER_AREA:
            bx, by, bw, bh = cv2.boundingRect(c)
            M = cv2.moments(c)
            if M["m00"] != 0:
                cx_local = int(M["m10"] / M["m00"])
                cy_local = int(M["m01"] / M["m00"])
                
                # Фильтруем по расстоянию до центра ROI (буквы лежат на кольце радиусом ~280px)
                dist = np.sqrt((cx_local - cx_roi)**2 + (cy_local - cy_roi)**2)
                if 200 <= dist <= 350:
                    valid_contours.append({
                        'center_local': (cx_local, cy_local),
                        'bbox': (bx, by, bw, bh),
                        'area': area,
                        'contour': c
                    })
    
    return valid_contours


def _ocr_single_crop(reader, roi, bbox):
    """
    Вырезает один контур из ROI, бинаризует и инвертирует (черный символ на белом фоне),
    масштабирует по высоте до оптимальных 80 пикселей и распознает с помощью EasyOCR.
    Возвращает распознанную букву или пустую строку.
    """
    bx, by, bw, bh = bbox
    pad = config.OCR_LETTER_PADDING
    
    # Вырезаем bounding box с паддингом (не выходя за границы)
    y1 = max(0, by - pad)
    y2 = min(roi.shape[0], by + bh + pad)
    x1 = max(0, bx - pad)
    x2 = min(roi.shape[1], bx + bw + pad)
    
    crop = roi[y1:y2, x1:x2]
    if crop.size == 0:
        return ""
    
    # Конвертируем в оттенки серого
    crop_gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    
    # Бинаризуем и инвертируем для получения четких черных букв на белом фоне
    blurred_crop = cv2.GaussianBlur(crop_gray, (5, 5), 0)
    _, thresh_crop = cv2.threshold(blurred_crop, config.BINARY_THRESHOLD, 255, cv2.THRESH_BINARY_INV)
    
    # Масштабируем по высоте до оптимальных 80 пикселей для лучшего распознавания EasyOCR
    target_h = 80
    h_crop, w_crop = thresh_crop.shape[:2]
    scale = target_h / h_crop
    crop_resized = cv2.resize(thresh_crop, (int(w_crop * scale), target_h), interpolation=cv2.INTER_NEAREST)
    
    # Распознаём
    results = reader.readtext(crop_resized, detail=1, paragraph=False,
                              allowlist='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz')
    
    for _, text, confidence in results:
        char = clean_ocr_text(text)
        if char:
            return char
    
    return ""


def _guess_letter_by_shape(bbox):
    """
    Эвристика определения буквы по aspect ratio контура.
    Очень узкие и высокие контуры — это почти наверняка 'I'.
    Возвращает букву или пустую строку.
    """
    _, _, bw, bh = bbox
    if bh == 0:
        return ""
    
    aspect_ratio = bw / float(bh)
    
    # Буква I: очень узкая (aspect ratio < 0.35)
    if aspect_ratio < 0.35:
        return 'i'
    
    return ""


def detect_letters_on_screen(d, reader, expected_letters=None, screen_bgr=None) -> list:
    """
    Делает скриншот области CIRCLE_ROI (или использует готовый), находит центроиды букв по контурам,
    и распознает их с помощью crop-based EasyOCR + shape heuristic + гибридного заполнения.
    Возвращает список кортежей вида: [(буква, (абс_x, абс_y)), ...]
    """
    if screen_bgr is None:
        screen_bgr = take_screenshot(d)
    
    x_roi, y_roi, w_roi, h_roi = config.CIRCLE_ROI["x"], config.CIRCLE_ROI["y"], config.CIRCLE_ROI["w"], config.CIRCLE_ROI["h"]
    roi = screen_bgr[y_roi:y_roi+h_roi, x_roi:x_roi+w_roi]
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    
    # 1. Поиск контуров с основным порогом
    contours_data = _find_contours_with_threshold(gray, config.BINARY_THRESHOLD)
    
    # Если нашли слишком мало контуров — пробуем адаптивные пороги
    expected_count = len(expected_letters) if expected_letters else 0
    min_acceptable = max(3, expected_count)
    
    if len(contours_data) < min_acceptable:
        best_contours = contours_data
        for offset in config.ADAPTIVE_THRESHOLD_OFFSETS:
            for adjusted_thresh in [config.BINARY_THRESHOLD - offset, config.BINARY_THRESHOLD + offset]:
                if 30 <= adjusted_thresh <= 230:
                    alt_contours = _find_contours_with_threshold(gray, adjusted_thresh)
                    if len(alt_contours) > len(best_contours):
                        best_contours = alt_contours
                        print(f"  [Adaptive] Порог {adjusted_thresh} дал {len(alt_contours)} контуров (лучше чем {len(contours_data)})")
        contours_data = best_contours
    
    if not contours_data:
        return []
    
    # 2. Распознавание каждого контура
    assigned = {}  # idx -> char
    
    if config.OCR_CROP_MODE:
        # === CROP-BASED OCR: вырезаем каждый контур и распознаём отдельно ===
        for idx, cd in enumerate(contours_data):
            bbox = cd['bbox']
            
            # Шаг 2a: Сначала проверяем shape heuristic (мгновенно, без OCR)
            shape_guess = _guess_letter_by_shape(bbox)
            if shape_guess:
                assigned[idx] = shape_guess
                continue
            
            # Шаг 2b: OCR на кропе
            char = _ocr_single_crop(reader, roi, bbox)
            if char:
                assigned[idx] = char
    else:
        # === LEGACY: один вызов OCR на всю ROI ===
        ocr_results = reader.readtext(roi, detail=1)
        
        detected_ocr = []
        for bbox_pts, text, confidence in ocr_results:
            char = clean_ocr_text(text)
            if char:
                xs = [pt[0] for pt in bbox_pts]
                ys = [pt[1] for pt in bbox_pts]
                cx_ocr = x_roi + int(sum(xs) / len(xs))
                cy_ocr = y_roi + int(sum(ys) / len(ys))
                detected_ocr.append({'char': char, 'center': (cx_ocr, cy_ocr)})
        
        # Связываем OCR-распознавания с геометрическими центроидами
        matched_ocr_indices = set()
        for cent_idx, cent in enumerate(contours_data):
            cx = x_roi + cent['center_local'][0]
            cy = y_roi + cent['center_local'][1]
            best_ocr = None
            best_dist = 60
            best_ocr_idx = -1
            
            for ocr_idx, ocr in enumerate(detected_ocr):
                if ocr_idx in matched_ocr_indices:
                    continue
                ox, oy = ocr['center']
                dist = np.sqrt((cx - ox)**2 + (cy - oy)**2)
                if dist < best_dist:
                    best_dist = dist
                    best_ocr = ocr
                    best_ocr_idx = ocr_idx
                    
            if best_ocr:
                assigned[cent_idx] = best_ocr['char']
                matched_ocr_indices.add(best_ocr_idx)
    
    # 3. Гибридное восстановление пропущенных букв по словарю уровня
    #    Расширенная версия: работает даже если пропущено несколько букв
    if expected_letters:
        matched_chars = list(assigned.values())
        
        remaining_expected = list(expected_letters)
        for mc in matched_chars:
            if mc in remaining_expected:
                remaining_expected.remove(mc)
                
        unassigned_indices = [idx for idx in range(len(contours_data)) if idx not in assigned]
        
        if len(unassigned_indices) > 0 and len(unassigned_indices) == len(remaining_expected):
            # Сортируем оставшиеся центроиды по соотношению сторон (width/height),
            # чтобы 'I' попала на самый узкий контур
            unassigned_indices.sort(
                key=lambda idx: contours_data[idx]['bbox'][2] / float(contours_data[idx]['bbox'][3])
            )
            remaining_expected.sort(key=lambda char: 0.1 if char.lower() == 'i' else 1.0)
            
            for idx, char in zip(unassigned_indices, remaining_expected):
                assigned[idx] = char.lower()
                cx_abs = x_roi + contours_data[idx]['center_local'][0]
                cy_abs = y_roi + contours_data[idx]['center_local'][1]
                print(f"  [Hybrid OCR] Восстановлена буква '{char.upper()}' для центроида ({cx_abs}, {cy_abs})")
        elif len(unassigned_indices) > 0 and len(remaining_expected) > 0:
            # Частичное восстановление: назначаем сколько можем (по соотношению сторон)
            unassigned_indices.sort(
                key=lambda idx: contours_data[idx]['bbox'][2] / float(contours_data[idx]['bbox'][3])
            )
            remaining_expected.sort(key=lambda char: 0.1 if char.lower() == 'i' else 1.0)
            
            for idx, char in zip(unassigned_indices, remaining_expected):
                assigned[idx] = char.lower()
                cx_abs = x_roi + contours_data[idx]['center_local'][0]
                cy_abs = y_roi + contours_data[idx]['center_local'][1]
                print(f"  [Hybrid OCR partial] Восстановлена буква '{char.upper()}' для центроида ({cx_abs}, {cy_abs})")
                
    # Собираем финальный результат
    letter_positions = []
    for idx, cd in enumerate(contours_data):
        char = assigned.get(idx)
        if char:
            abs_center = (x_roi + cd['center_local'][0], y_roi + cd['center_local'][1])
            letter_positions.append((char, abs_center))
            print(f"  [Letter] '{char.upper()}' в координатах {abs_center}")
            
    return letter_positions

def get_word_swipe_path(word: str, letter_positions: list) -> list:
    """
    Строит список точек (X, Y) для последовательного свайпа слова.
    Учитывает повторяющиеся буквы (каждая физическая координата используется один раз).
    """
    path = []
    used_indices = set()
    
    for char in word:
        found = False
        for idx, (l_char, pos) in enumerate(letter_positions):
            if l_char == char and idx not in used_indices:
                path.append(pos)
                used_indices.add(idx)
                found = True
                break
        if not found:
            # Если слово содержит букву, которой нет на экране (по ошибке OCR)
            return []
            
    return path

def swipe_word_group(d, group, letters, solutions_len, swiped_start, skipped_start):
    """
    Вводит группу слов свайпами.
    Возвращает кортеж: (new_swiped_count, new_skipped_count, popup_detected, last_processed_index)
    Если по ходу ввода обнаружено бонусное окно, прекращает ввод, закрывает его и возвращает popup_detected = True.
    """
    swiped_count = swiped_start
    skipped_count = skipped_start
    
    words_to_swipe = list(group)
    i = 0
    while i < len(words_to_swipe):
        word = words_to_swipe[i]
        check_pause()
        
        path = get_word_swipe_path(word, letters)
        if not path:
            skipped_count += 1
            i += 1
            continue
            
        execution_path = list(path)
        if config.SWIPE_HOLD_LAST and len(execution_path) > 0:
            execution_path.append(execution_path[-1])
        
        total_duration = max(0.05, (len(execution_path) - 1) * config.SWIPE_DURATION)
        print(f"[{swiped_count + skipped_count + 1}/{solutions_len}] Ввод слова: {word.upper()} ({len(word)} букв)")
        
        try:
            with device_lock:
                d.swipe_points(execution_path, total_duration)
            swiped_count += 1
        except Exception as e:
            print(f"[!] Ошибка при выполнении свайпа: {e}")
        
        time.sleep(config.SWIPE_DELAY)
        
        # Проверяем, не сменилось ли состояние экрана (появилась ли кнопка перехода/продолжения)
        screen_after = take_screenshot(d)
        state, button_pos, button_name = check_game_state(d, screen_after)
        if state in ("tap_continue", "next_level"):
            print(f"[Swipe Loop] Обнаружено всплывающее окно ({state}: {button_name}). Прерываем ввод группы.")
            return swiped_count, skipped_count, True, i
            
        i += 1
        
    return swiped_count, skipped_count, False, len(words_to_swipe)

def check_game_state(d, screen_bgr=None):
    """
    Делает скриншот (или использует готовый) и проверяет текущую ситуацию на экране.
    Возвращает (state, pos, name) где state может быть:
      - "next_level" — кнопка перехода на следующий уровень
      - "tap_continue" — промежуточная кнопка 'tap to continue'
      - "playing" — игровое поле
    """
    if screen_bgr is None:
        screen_bgr = take_screenshot(d)
    
    pos, name, btn_type = check_for_navigation_buttons(d, screen_bgr)
    if pos:
        return btn_type, pos, name
        
    return "playing", None, None


def _is_game_in_foreground(d):
    """
    Проверяет, что игра сейчас в фокусе.
    Использует GAME_PACKAGE для точной проверки + проверку подозрительных пакетов.
    """
    try:
        with device_lock:
            app = d.app_current()
        package_name = app.get("package") if app else None
        if not package_name:
            return True  # Не удалось определить — не блокируем

        # Проверяем, что это именно игра
        if config.GAME_PACKAGE and config.GAME_PACKAGE in package_name:
            return True

        # Проверяем, не подозрительный ли пакет
        for susp in config.SUSPICIOUS_PACKAGES:
            if susp in package_name:
                return False

        # Неизвестный пакет — может быть оверлей рекламы, не блокируем
        return True
    except Exception:
        return True


def _wait_for_button_gone(d, timeout=4.0):
    """
    Ждёт, пока кнопка Next исчезнет с экрана.
    Защита от двойного клика, который приводит к пропуску уровня.
    """
    time.sleep(2.0)  # Минимальная пауза на анимацию
    start = time.time()
    while time.time() - start < timeout:
        state, _, _ = check_game_state(d)
        if state == "playing":
            print("[+] Экран перехода исчез. Продолжаем.")
            return
        time.sleep(0.5)
    print("[*] Таймаут ожидания. Продолжаем.")


def _enable_show_taps(d, enable=True):
    """
    Включает/выключает отображение нажатий на экране через Developer Options.
    Полезно для отладки — видно где именно бот нажимает.
    """
    value = 1 if enable else 0
    try:
        with device_lock:
            d.shell(f"settings put system show_touches {value}")
        state_str = "включено" if enable else "выключено"
        print(f"[+] Отображение нажатий на экране {state_str}.")
    except Exception as e:
        print(f"[!] Не удалось {'включить' if enable else 'выключить'} show_touches: {e}")


def _save_level_state(current_level):
    """Сохраняет текущий уровень в файл для восстановления при перезапуске."""
    try:
        state = {"current_level": current_level, "timestamp": time.time()}
        with open(config.LEVEL_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f)
    except Exception as e:
        print(f"[!] Ошибка сохранения состояния уровня: {e}")


def _load_level_state():
    """Загружает сохранённый уровень из файла. Возвращает номер уровня или None."""
    try:
        if os.path.exists(config.LEVEL_STATE_FILE):
            with open(config.LEVEL_STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
            level = state.get("current_level")
            ts = state.get("timestamp", 0)
            # Считаем состояние актуальным в течение 24 часов
            if level is not None and (time.time() - ts) < 86400:
                return level
    except Exception as e:
        print(f"[!] Ошибка загрузки состояния уровня: {e}")
    return None


def main():
    print("====================================================")
    print("   Запуск автокликера Word City: Connect Word Game   ")
    print("====================================================")
    
    # 1. Подключение устройства
    d = connect_device()

    # 1.1. Включаем отображение нажатий для отладки
    if config.SHOW_TAPS:
        _enable_show_taps(d, enable=True)
    
    # 2. Загрузка словаря
    dictionary = utils.load_dictionary()
    
    # 3. Инициализация EasyOCR
    print("[*] Инициализация EasyOCR (загрузка библиотек может занять 30-40 секунд)...")
    try:
        # Ускорение импорта за счет отключения неиспользуемого distributed.tensor в PyTorch
        from unittest.mock import MagicMock
        sys.modules['torch.distributed.tensor'] = MagicMock()
        
        import torch
        import easyocr
        
        use_gpu = torch.cuda.is_available()
        if use_gpu:
            print("[+] Обнаружена видеокарта с поддержкой CUDA! EasyOCR будет работать с аппаратным ускорением GPU.")
        else:
            print("[*] Видеокарта с поддержкой CUDA не найдена. EasyOCR будет использовать процессор (CPU).")
            print("    Обратите внимание, что аппаратное ускорение CUDA поддерживается только на видеокартах NVIDIA.")
    except Exception:
        use_gpu = False
        import easyocr
        print("[*] Не удалось проверить поддержку CUDA. Используем CPU для EasyOCR.")
        
    reader = easyocr.Reader(config.OCR_LANGUAGES, gpu=use_gpu)
    print("[+] EasyOCR успешно инициализирован.")

    # 3.1. Инициализация AI Self-Healing сервиса
    from ai_healing import AIHealingService
    ai_service = AIHealingService()
    
    # 4. Запуск Watchdog потока
    stop_event.clear()
    watchdog_thread = threading.Thread(target=watchdog_worker, args=(d, stop_event), daemon=True)
    watchdog_thread.start()
    
    print("\n[+] Автокликер запущен и переходит в игровой цикл.")
    print("    Нажмите Ctrl+C в терминале для остановки бота.")
    print("    Нажмите ПРОБЕЛ или 'P' в окне консоли для приостановки бота (пауза).")
    
    # Загрузка сохранённого уровня
    saved_level = _load_level_state()

    # Запрос стартового уровня у пользователя
    try:
        if saved_level is not None:
            level_input = input(f"\n[*] Найден сохранённый уровень: {saved_level}. Нажмите Enter для продолжения или введите другой номер: ").strip()
        else:
            level_input = input("\n[*] Введите номер текущего уровня (или нажмите Enter для автоопределения по буквам): ").strip()
        
        if level_input.isdigit():
            current_level = int(level_input)
        elif saved_level is not None and not level_input:
            current_level = saved_level
            print(f"[+] Продолжаем с сохранённого уровня: {current_level}")
        else:
            current_level = None
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception:
        current_level = saved_level

    mismatch_counter = 0
    stuck_counter = 0  # Счётчик: сколько раз подряд уровень не прошёл после ввода всех слов
    try:
        while True:
            # Проверяем, не нажал ли пользователь паузу
            check_pause()
            
            # Шаг A0. Проверяем, что мы в игре (а не в Play Market/браузере)
            if not _is_game_in_foreground(d):
                print("[Watchdog] Мы не в игре, ждём возврата...")
                time.sleep(1.5)
                continue

            # Шаг A0.5. Проверяем cooldown после рекламы
            if _is_ad_cooldown_active():
                remaining = ad_cooldown_until - time.time()
                if remaining > 0.5:  # Логируем только если ожидание значительное
                    print(f"[*] Ожидание закрытия рекламы ({remaining:.1f}с)...")
                time.sleep(0.5)
                continue
            
            # Шаг A. Получаем скриншот один раз для всего цикла
            screen_bgr = take_screenshot(d)
            
            # Проверяем, не зависли ли мы на экране победы/промежуточном экране
            state, button_pos, button_name = check_game_state(d, screen_bgr=screen_bgr)
            
            if state == "tap_continue":
                # Промежуточная кнопка "Tap to continue" — просто кликаем, уровень НЕ меняется
                print(f"[+] Промежуточная кнопка ({button_name}). Кликаем {button_pos}...")
                with device_lock:
                    d.click(button_pos[0], button_pos[1])
                time.sleep(1.5)
                continue
            
            if state == "next_level":
                print(f"[+] Кнопка перехода на след. уровень ({button_name}). Кликаем {button_pos}...")
                with device_lock:
                    d.click(button_pos[0], button_pos[1])
                if current_level is not None:
                    current_level += 1
                    print(f"[+] Переход на следующий уровень. Ожидаемый уровень: {current_level}")
                    _save_level_state(current_level)
                stuck_counter = 0
                _wait_for_button_gone(d)
                continue
                
            # Шаг B. Получение решений и распознавание букв
            solutions = []
            expected_letters = None

            # Определяем стратегию в зависимости от stuck_counter
            use_ai_healing = False

            if stuck_counter >= config.STUCK_AI_HEALING_LIMIT:
                use_ai_healing = True
            
            # AI Self-Healing: сначала попробуем закрыть рекламу по крестику
            if use_ai_healing and ai_service.is_enabled:
                print(f"\n[AI Healing] === Проверка наличия рекламы на экране (stuck={stuck_counter}) ===")
                ad_close_pos = ai_service.find_ad_close_coordinate(screen_bgr)
                if ad_close_pos:
                    print(f"[AI Healing] Кликаем по найденным AI координатам крестика: {ad_close_pos}")
                    with device_lock:
                        d.click(ad_close_pos[0], ad_close_pos[1])
                    time.sleep(3.0)
                    stuck_counter = max(0, stuck_counter - 1)
                    continue

                # Если крестик не найден, пробуем обычное AI Self-Healing (распознавание букв и составление слов)
                print(f"[AI Healing] Крестик рекламы не обнаружен. Пробуем распознавание букв через AI...")
                ai_letters = ai_service.recognize_letters(screen_bgr)
                if ai_letters:
                    print(f"[AI Healing] AI распознал буквы: {ai_letters}")

                    # Шаг 2: AI генерирует слова
                    ai_words = ai_service.solve_with_ai(ai_letters)
                    if ai_words:
                        solutions = ai_words
                        # Пересканируем буквы с OCR для получения координат
                        print("[*] Сканирование букв для получения координат...")
                        letters = detect_letters_on_screen(d, reader, expected_letters=ai_letters, screen_bgr=screen_bgr)

                        if not letters:
                            print("[AI Healing] Не удалось получить координаты букв. Ждём...")
                            time.sleep(2.0)
                            continue

                        detected_chars = [item[0] for item in letters]
                        print(f"[AI Healing] Координаты получены для {len(detected_chars)} букв: {sorted(detected_chars)}")

                        # Сбрасываем stuck_counter чтобы дать AI шанс
                        stuck_counter = max(0, stuck_counter - 2)

                        # === Ввод слов ===
                        level_cleared = False
                        swiped_count = 0
                        skipped_count = 0
                        group_size = config.SWIPE_GROUP_SIZE if config.SWIPE_GROUP_SIZE else len(solutions)

                        for g_start in range(0, len(solutions), group_size):
                            group = solutions[g_start:g_start + group_size]
                            
                            g_idx = 0
                            while g_idx < len(group):
                                sub_group = group[g_idx:]
                                swiped_count, skipped_count, popup_detected, last_idx = swipe_word_group(
                                    d, sub_group, letters, len(solutions), swiped_count, skipped_count
                                )
                                if popup_detected:
                                    g_idx += last_idx
                                    continue
                                else:
                                    break

                            state, button_pos, button_name = check_game_state(d)
                            if state == "tap_continue":
                                print(f"[+] Промежуточная кнопка ({button_name}). Кликаем...")
                                with device_lock:
                                    d.click(button_pos[0], button_pos[1])
                                time.sleep(1.5)
                                state, button_pos, button_name = check_game_state(d)
                            if state == "next_level":
                                print(f"[+] Уровень завершен через AI! Кнопка ({button_name}). Кликаем {button_pos}...")
                                with device_lock:
                                    d.click(button_pos[0], button_pos[1])
                                if current_level is not None:
                                    current_level += 1
                                    print(f"[+] Переход на следующий уровень: {current_level}")
                                    _save_level_state(current_level)
                                level_cleared = True
                                stuck_counter = 0
                                _wait_for_button_gone(d)
                                break

                        if not level_cleared:
                            stuck_counter += 1
                            print(f"[AI Healing] AI тоже не помог пройти уровень. (stuck={stuck_counter}, swiped={swiped_count}, skipped={skipped_count})")
                            if stuck_counter >= config.STUCK_AI_HEALING_LIMIT + 3:
                                print("[AI Healing] Все стратегии исчерпаны. Сброс и ожидание...")
                                current_level = None
                                mismatch_counter = 0
                                stuck_counter = 0
                                time.sleep(5.0)
                        continue
                    else:
                        print("[AI Healing] AI не смог сгенерировать слова.")
                else:
                    print("[AI Healing] AI не смог распознать буквы.")

                # AI не помог — сброс
                if stuck_counter >= config.STUCK_AI_HEALING_LIMIT + 3:
                    print("[!] Полный сброс после неудачных попыток AI.")
                    current_level = None
                    mismatch_counter = 0
                    stuck_counter = 0
                    time.sleep(5.0)
                    continue
                else:
                    stuck_counter += 1
                    time.sleep(2.0)
                    continue

            elif use_ai_healing and not ai_service.is_enabled:
                # AI отключён — сбрасываем и пересканируем
                print(f"[!] Бот застрял ({stuck_counter} попыток). AI Self-Healing недоступен (нет API ключа).")
                print("[!] Сброс уровня и пересканирование...")
                current_level = None
                mismatch_counter = 0
                stuck_counter = 0
                time.sleep(2.0)
                continue

            print("\n[*] Сканирование игрового поля (поиск букв)...")
            letters = detect_letters_on_screen(d, reader, expected_letters, screen_bgr=screen_bgr)
            
            if not letters:
                print("[?] Буквы на экране не найдены. Возможно, идет катсцена или анимация. Ждем...")
                time.sleep(config.ACTION_DELAY)
                continue
                
            detected_chars = [item[0] for item in letters]
            print(f"[+] Найдено букв на экране: {len(detected_chars)} -> {sorted(detected_chars)}")

            # Валидация OCR: слишком много уникальных букв = мусор (текст рекламы)
            unique_chars = set(detected_chars)
            if len(unique_chars) > config.MAX_UNIQUE_LETTERS:
                print(f"[!] Слишком много уникальных букв ({len(unique_chars)} > {config.MAX_UNIQUE_LETTERS}). Вероятно, текст рекламы. Пропускаем...")
                time.sleep(1.5)
                continue
            
            # Проверяем, соответствуют ли распознанные буквы ответам уровня
            if expected_letters and solutions:
                if not utils.verify_words_match_letters(solutions, detected_chars):
                    mismatch_counter += 1
                    print(f"[!] Несовпадение ({mismatch_counter}/2): Буквы на экране {sorted(detected_chars)} не подходят к уровню {current_level}.")
                    # Сбрасываем гибридный режим и пересканируем чисто
                    solutions = []
                    expected_letters = None
                    screen_bgr_retry = take_screenshot(d)
                    letters = detect_letters_on_screen(d, reader, expected_letters=None, screen_bgr=screen_bgr_retry)
                    detected_chars = [item[0] for item in letters]
                    print(f"[*] Пересканировано без гибридного режима: {sorted(detected_chars)}")
                else:
                    mismatch_counter = 0
            
            if len(detected_chars) < 3:
                print("[!] Слишком мало распознанных букв (< 3). Ждем стабильного экрана...")
                time.sleep(config.ACTION_DELAY)
                continue
                
            # Шаг C. Генерация решений напрямую через локальный словарь
            print("[*] Запуск поиска анаграмм в локальном словаре...")
            solutions = utils.solve_anagrams(detected_chars, dictionary)
            print(f"[+] Сгенерировано {len(solutions)} возможных слов из локального словаря.")
            
            if not solutions:
                print("[!] Не удалось собрать слова из распознанных букв. Попробуем пересканировать через секунду...")
                time.sleep(1.0)
                continue
                
            # Шаг D. Ввод слов по очереди группами (Grouped Swiping)
            level_cleared = False
            swiped_count = 0
            skipped_count = 0
            
            group_size = config.SWIPE_GROUP_SIZE if config.SWIPE_GROUP_SIZE else len(solutions)
            
            for g_start in range(0, len(solutions), group_size):
                group = solutions[g_start:g_start + group_size]
                
                g_idx = 0
                while g_idx < len(group):
                    sub_group = group[g_idx:]
                    swiped_count, skipped_count, popup_detected, last_idx = swipe_word_group(
                        d, sub_group, letters, len(solutions), swiped_count, skipped_count
                    )
                    if popup_detected:
                        g_idx += last_idx
                        continue
                    else:
                        break
                
                # После ввода группы проверяем, не завершился ли уровень
                state, button_pos, button_name = check_game_state(d)
                
                if state == "tap_continue":
                    print(f"[+] Промежуточная кнопка ({button_name}). Кликаем и продолжаем...")
                    with device_lock:
                        d.click(button_pos[0], button_pos[1])
                    time.sleep(1.5)
                    state, button_pos, button_name = check_game_state(d)
                
                if state == "next_level":
                    print(f"[+] Уровень завершен! Кнопка перехода ({button_name}). Кликаем {button_pos}...")
                    with device_lock:
                        d.click(button_pos[0], button_pos[1])
                    if current_level is not None:
                        current_level += 1
                        print(f"[+] Переход на следующий уровень: {current_level}")
                        _save_level_state(current_level)
                    level_cleared = True
                    stuck_counter = 0
                    _wait_for_button_gone(d)
                    break
                
            if not level_cleared:
                stuck_counter += 1
                print(f"[*] Все слова введены, но уровень не пройден. (stuck={stuck_counter}, swiped={swiped_count}, skipped={skipped_count})")
                
                # Если слишком много слов не удалось свайпнуть — буквы неправильные
                if swiped_count == 0 or (skipped_count > swiped_count):
                    print(f"[!] Большинство слов не удалось свайпнуть — буквы на экране не совпадают с ответами.")
                    print(f"[!] Сбрасываем номер уровня и принудительно пересканируем с OCR.")
                    current_level = None
                    mismatch_counter = 0
                    stuck_counter = 0
                    time.sleep(config.ACTION_DELAY)
                    continue
                
                # Если застряли STUCK_RESET_LIMIT+ раза подряд — принудительный сброс
                if stuck_counter >= config.STUCK_RESET_LIMIT and stuck_counter < config.STUCK_AI_HEALING_LIMIT:
                    print(f"[!] Бот застрял ({stuck_counter} попыток подряд без прогресса).")
                    print(f"[!] Сбрасываем номер уровня и переходим на полное распознавание OCR.")
                    current_level = None
                    mismatch_counter = 0
                    # НЕ сбрасываем stuck_counter — он продолжит расти до STUCK_AI_HEALING_LIMIT
                
                time.sleep(config.ACTION_DELAY)
                
    except KeyboardInterrupt:
        print("\n[*] Получен сигнал остановки (Ctrl+C). Завершение работы...")
    finally:
        # Останавливаем фоновый поток
        stop_event.set()
        watchdog_thread.join(timeout=2.0)
        # Выключаем show_taps
        if config.SHOW_TAPS:
            _enable_show_taps(d, enable=False)
        # Сохраняем уровень
        if current_level is not None:
            _save_level_state(current_level)
        print("[+] Автокликер успешно остановлен.")


if __name__ == "__main__":
    main()
