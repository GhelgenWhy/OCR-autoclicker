# -*- coding: utf-8 -*-
"""
Скрипт калибровки calibrate.py.
Используется для проверки подключения к устройству, настройки области поиска букв (ROI),
проверки точности поиска контуров букв и создания скриншотов для вырезания шаблонов кнопок.
"""

import sys
import os
import cv2
import numpy as np
import uiautomator2 as u2
import config

def connect_device():
    """Подключается к Android-устройству через uiautomator2."""
    print("[*] Подключение к устройству...")
    try:
        if config.DEVICE_SERIAL:
            d = u2.connect(config.DEVICE_SERIAL)
        else:
            d = u2.connect()  # Автоматическое подключение
        
        info = d.info
        print(f"[+] Подключение установлено успешно!")
        print(f"    Модель устройства: {info.get('productName', 'Неизвестно')}")
        print(f"    Разрешение экрана: {info.get('displayWidth', 0)}x{info.get('displayHeight', 0)}")
        return d
    except Exception as e:
        print(f"[!] Ошибка подключения к устройству: {e}")
        print("    Убедитесь, что отладка по USB включена на телефоне,")
        print("    телефон подключен к ПК и запущен ADB сервер (`adb devices`).")
        sys.exit(1)

def run_calibration(d):
    """Выполняет захват скриншота, кроп области букв и поиск контуров с отрисовкой."""
    print("\n[*] Запуск калибровки области букв...")
    
    # 1. Получение скриншота
    try:
        pil_img = d.screenshot()
        # Превращаем PIL Image в OpenCV BGR формат
        screen_bgr = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    except Exception as e:
        print(f"[!] Ошибка захвата экрана: {e}")
        return

    # Сохраняем полный скриншот на случай, если пользователю нужно вырезать шаблоны
    full_screen_path = os.path.join(config.SCREENSHOTS_DIR, "full_screen.png")
    cv2.imwrite(full_screen_path, screen_bgr)
    print(f"[+] Полный скриншот экрана сохранен в: {full_screen_path}")
    print("    (Используйте его, чтобы вырезать шаблоны кнопок в папку templates/)")

    # 2. Вырезаем область круга с буквами (ROI)
    x, y, w, h = config.CIRCLE_ROI["x"], config.CIRCLE_ROI["y"], config.CIRCLE_ROI["w"], config.CIRCLE_ROI["h"]
    
    # Проверка на выход за границы экрана
    screen_h, screen_w = screen_bgr.shape[:2]
    if x + w > screen_w or y + h > screen_h:
        print(f"[WARNING] Область CIRCLE_ROI ({x}+{w}, {y}+{h}) выходит за рамки экрана ({screen_w}x{screen_h})!")
        print("          Пожалуйста, скорректируйте параметры в config.py.")
        
    roi = screen_bgr[y:y+h, x:x+w].copy()
    
    # 3. Обработка изображения для поиска контуров
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    
    # Бинаризация (порог берется из конфигурации)
    # Попробуем обычную бинаризацию и инвертированную (в зависимости от цвета букв)
    _, thresh = cv2.threshold(blurred, config.BINARY_THRESHOLD, 255, cv2.THRESH_BINARY_INV)
    
    # Также сохраним изображение порога для отладки
    thresh_debug_path = os.path.join(config.SCREENSHOTS_DIR, "debug_threshold.png")
    cv2.imwrite(thresh_debug_path, thresh)
    print(f"[+] Бинаризованное изображение круга сохранено в: {thresh_debug_path}")
    
    # Находим внешние контуры
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    letters_count = 0
    vis_roi = roi.copy()
    
    print("\n[*] Результаты поиска контуров букв:")
    for i, c in enumerate(contours):
        area = cv2.contourArea(c)
        # Фильтруем контуры по площади, чтобы оставить только буквы
        if config.MIN_LETTER_AREA <= area <= config.MAX_LETTER_AREA:
            # Вычисляем моменты для нахождения центра тяжести (centroid)
            M = cv2.moments(c)
            if M["m00"] != 0:
                cx_local = int(M["m10"] / M["m00"])
                cy_local = int(M["m01"] / M["m00"])
                
                # Абсолютные координаты на всем экране
                cx_global = x + cx_local
                cy_global = y + cy_local
                
                letters_count += 1
                print(f"  Буква #{letters_count}: Площадь контура = {int(area)} px, "
                      f"Локальные коорд. = ({cx_local}, {cy_local}), "
                      f"Абсолютные коорд. экрана = ({cx_global}, {cy_global})")
                
                # Рисуем контур буквы зеленым цветом
                cv2.drawContours(vis_roi, [c], -1, (0, 255, 0), 2)
                # Рисуем перекрестие и точку в центре
                cv2.drawMarker(vis_roi, (cx_local, cy_local), (0, 0, 255), 
                               markerType=cv2.MARKER_CROSS, markerSize=15, thickness=2)
                # Рисуем кружок
                cv2.circle(vis_roi, (cx_local, cy_local), 5, (255, 0, 0), -1)
                # Пишем индекс
                cv2.putText(vis_roi, str(letters_count), (cx_local + 10, cy_local - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
                
    # Сохраняем результат разметки
    calibration_path = os.path.join(config.SCREENSHOTS_DIR, "debug_calibration.png")
    cv2.imwrite(calibration_path, vis_roi)
    print(f"\n[+] Изображение калибровки сохранено в: {calibration_path}")
    print(f"[+] Всего найдено букв по фильтру площади: {letters_count}")
    
    # Попытка показать GUI окно (если запущено не в headless-среде)
    try:
        # Рисуем рамку ROI на оригинальном скриншоте для наглядности
        vis_full = screen_bgr.copy()
        cv2.rectangle(vis_full, (x, y), (x+w, y+h), (0, 255, 255), 3)
        cv2.putText(vis_full, "CIRCLE ROI AREA", (x, y - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
        
        cv2.imwrite(os.path.join(config.SCREENSHOTS_DIR, "debug_roi_placement.png"), vis_full)
        print(f"[+] Изображение с размещением ROI сохранено в debug_roi_placement.png")
        
        print("\nПопытка отобразить результаты в окне OpenCV (нажмите ЛЮБУЮ КЛАВИШУ для закрытия)...")
        # Уменьшаем картинку для вывода на экран, если она слишком большая
        cv2.imshow("Calibration ROI (Detected Letters)", vis_roi)
        cv2.waitKey(0)
        cv2.destroyAllWindows()
    except Exception:
        print("[!] Интерфейс вывода OpenCV недоступен (headless-режим).")
        print("    Пожалуйста, откройте изображения в папке `debug_screenshots/` вручную:")
        print(f"    1. `debug_roi_placement.png` - проверить положение рамки круга.")
        print(f"    2. `debug_threshold.png` - проверить качество бинаризации.")
        print(f"    3. `debug_calibration.png` - проверить, что центры букв найдены верно.")

if __name__ == "__main__":
    d = connect_device()
    run_calibration(d)
