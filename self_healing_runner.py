# -*- coding: utf-8 -*-
"""
Self-Healing runner для автокликера.
Запускает бота как подпроцесс, отслеживает его вывод и при падении (Traceback)
автоматически вызывает OpenRouter/Gemini API для исправления багов в коде,
после чего перезапускает бота с примененными исправлениями.
"""

import sys
import os
import subprocess
import time
import re
import urllib.request
import urllib.error
import json

# Импортируем конфигурацию
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import config

def call_ai_to_fix(traceback_str, filename, file_content):
    """
    Вызывает API OpenRouter для исправления кода файла.
    """
    if not config.OPENROUTER_API_KEY:
        print("[Self-Healing Runner] Ошибка: OPENROUTER_API_KEY не задан в .env/config.py.")
        return None

    print(f"[Self-Healing Runner] Отправка запроса к AI для исправления {os.path.basename(filename)}...")
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/GhelgenWhy/OCR-autoclicker",
        "X-Title": "Word City Autoclicker Self-Healer"
    }
    
    prompt = (
        f"You are a self-healing software engineer assistant.\n"
        f"The python script crashed with the following traceback:\n"
        f"```\n{traceback_str}\n```\n\n"
        f"The crash happened in the file: {filename}\n\n"
        f"Here is the complete original code of {filename}:\n"
        f"```python\n{file_content}\n```\n\n"
        f"TASK: Fix the bug causing this crash. Make sure your changes are syntactically and logically correct.\n"
        f"Ensure you preserve the rest of the file exactly. Return ONLY the complete corrected python code. "
        f"Do NOT include markdown formatting, backticks, or any explanation text. Return the raw code ready to be saved."
    )
    
    payload = {
        "model": config.AI_HEALING_MODEL,
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }
    
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=45) as response:
            result = json.loads(response.read().decode("utf-8"))
            choices = result.get("choices", [])
            if choices:
                fixed_code = choices[0].get("message", {}).get("content", "")
                
                # Очистка от возможной markdown разметки
                fixed_code = fixed_code.strip()
                if fixed_code.startswith("```python"):
                    fixed_code = fixed_code[9:]
                elif fixed_code.startswith("```"):
                    fixed_code = fixed_code[3:]
                if fixed_code.endswith("```"):
                    fixed_code = fixed_code[:-3]
                
                return fixed_code.strip()
    except Exception as e:
        print(f"[Self-Healing Runner] Ошибка при вызове AI API: {e}")
    return None

def run_bot():
    workspace_dir = os.path.dirname(os.path.abspath(__file__))
    cmd = [sys.executable, "bot.py"]
    
    print("\n" + "="*60)
    print(f"[Self-Healing Runner] Запуск бота: {' '.join(cmd)}")
    print("="*60 + "\n")
    
    try:
        # Запускаем bot.py, объединяя stdout и stderr
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=workspace_dir
        )
        
        output_buffer = []
        # Читаем вывод построчно в реальном времени
        while True:
            line = process.stdout.readline()
            if not line:
                break
            sys.stdout.write(line)
            sys.stdout.flush()
            output_buffer.append(line)
            
        process.wait()
        return process.returncode, "".join(output_buffer)
    except KeyboardInterrupt:
        print("\n[Self-Healing Runner] Получен сигнал прерывания (Ctrl+C).")
        return -1, "KeyboardInterrupt"
    except Exception as e:
        print(f"[Self-Healing Runner] Ошибка выполнения процесса: {e}")
        return -1, str(e)

def main():
    workspace_dir = os.path.dirname(os.path.abspath(__file__))
    
    while True:
        returncode, output = run_bot()
        
        if returncode == 0:
            print("[Self-Healing Runner] Бот завершил работу без ошибок.")
            break
        elif "KeyboardInterrupt" in output or returncode == -1073741510:
            print("[Self-Healing Runner] Выход из раннера по Ctrl+C.")
            break
            
        # Ищем traceback
        if "Traceback (most recent call last):" in output:
            print("\n[Self-Healing Runner] Обнаружено критическое падение бота (Traceback)!")
            
            # Извлекаем пути до файлов в трейсбэке
            matches = re.findall(r'File "([^"]+)", line (\d+)', output)
            local_files = []
            for filepath, line_num in matches:
                abs_path = os.path.abspath(os.path.join(workspace_dir, filepath))
                if abs_path.startswith(workspace_dir) and os.path.exists(abs_path):
                    local_files.append((abs_path, int(line_num)))
            
            if local_files:
                # Берем самый последний файл из стека вызовов в нашей директории
                target_file, crash_line = local_files[-1]
                print(f"[Self-Healing Runner] Сбой произошел в файле {os.path.basename(target_file)} на строке {crash_line}.")
                
                try:
                    with open(target_file, "r", encoding="utf-8") as f:
                        file_content = f.read()
                except Exception as e:
                    print(f"[Self-Healing Runner] Не удалось прочитать файл {target_file}: {e}")
                    time.sleep(5)
                    continue
                
                # Вызываем AI для авто-исправления
                fixed_code = call_ai_to_fix(output, target_file, file_content)
                
                if fixed_code and len(fixed_code) > 100:  # Базовая проверка валидности кода
                    # Создаем бэкап перед изменением
                    backup_file = target_file + ".bak"
                    try:
                        with open(backup_file, "w", encoding="utf-8") as f:
                            f.write(file_content)
                        
                        # Перезаписываем оригинальный файл исправленным кодом
                        with open(target_file, "w", encoding="utf-8") as f:
                            f.write(fixed_code)
                            
                        print(f"[Self-Healing Runner] Исправление успешно применено! Бэкап сохранен в {os.path.basename(backup_file)}")
                        print("[Self-Healing Runner] Перезапуск через 3 секунды...")
                        time.sleep(3)
                        continue
                    except Exception as e:
                        print(f"[Self-Healing Runner] Не удалось применить изменения к файлу {target_file}: {e}")
                else:
                    print("[Self-Healing Runner] Не удалось получить корректные исправления от AI.")
            else:
                print("[Self-Healing Runner] Не удалось определить целевой файл падения из трейсбэка.")
        
        print("[Self-Healing Runner] Перезапуск бота через 5 секунд...")
        time.sleep(5)

if __name__ == "__main__":
    main()
