from datetime import datetime
import os
import json
import time

LOG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bot_metrics.json")


def create_log_entry(session_id, user_message, intent, is_success, response_text, confidence_score, response_time_ms):
    """Создает словарь с лог-записью."""
    return {
        "timestamp": datetime.now().isoformat(),
        "session_id": session_id,      # Здесь будет храниться роль (Студент/Преподаватель/Абитуриент) или группа
        "user_message": user_message,  # Что ввел пользователь
        "intent": intent,              # Какое намерение распознано (расписание, дз, курсы)
        "is_success": is_success,      # Успешно ли ответил бот
        "response_text": response_text,# Текст ответа из базы/схемы
        "confidence_score": confidence_score,
        "response_time_ms": response_time_ms  # Время отклика процессора в миллисекундах
    }

def process_user_input(user_message, session_id):
    """
    Обрабатывает сообщение пользователя на основе реальных интентов вуза:
    1. Распознает намерение (Расписание, ДЗ, Подготовительные курсы).
    2. Формирует каноничные ответы.
    3. Замеряет время работы в мс.
    4. Возвращает готовую запись.
    """
    start_time = time.time()
    
    msg = user_message.strip().lower()
    intent = "unknown"
    response_text = "Извините, я вас не понял. Пожалуйста, выберите одну из доступных команд. 🤖"
    is_success = False
    confidence_score = 0.0

    # Определение базовых интентов чат-бота:
    if "расписание" in msg or "пара" in msg or "1" == msg:
        intent = "просмотр_расписания"
        response_text = "📅 Расписание группы АКТ-26: Пара №1: Актёрское мастерство, Пара №2: Сценическая речь."
        is_success = True
        confidence_score = 1.0
        
    elif "домашнее" in msg or "задание" in msg or "дз" in msg or "2" == msg:
        intent = "просмотр_домашнего_задания"
        response_text = "🎒 Домашнее задание: Подготовить монолог Хлестакова из комедии 'Ревизор'."
        is_success = True
        confidence_score = 0.95
        
    elif "подготовительные" in msg or "курсы" in msg or "абитуриент" in msg:
        intent = "узнать_подготовительные_курсы"
        response_text = "🎭 Открыт приём на подготовительные курсы по Актёрскому мастерству и Сценической речи!"
        is_success = True
        confidence_score = 0.98

    # Вычисляем точное время ответа в миллисекундах
    response_time_ms = int((time.time() - start_time) * 1000)
    if response_time_ms == 0:
        response_time_ms = 1  # Чтобы не было 0 мс на быстрых SSD

    return create_log_entry(session_id, user_message, intent, is_success, response_text, confidence_score, response_time_ms)

def save_log(event_data, filename=LOG_FILE):
    """Записывает структурированную транзакцию метрик в журнал JSON"""
    
    logs = []
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    logs = json.loads(content)
        except Exception:
            logs = []
            
    logs.append(event_data)
    
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    # 2. Фиксация транзакции в текстовый журнал для отладки (app.log)
    app_log_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.log")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
    
    log_line = (
        f"{timestamp} - [INFO] - [src.message_processor] - "
        f"Пользователь вызвал интент: '{event_data.get('intent', 'unknown')}'. "
        f"Успешность: {event_data.get('is_success', True)}. "
        f"Время отклика: {event_data.get('response_time_ms', 0)} ms\n"
    )
    
    try:
        with open(app_log_path, "a", encoding="utf-8") as f:
            f.write(log_line)
    except Exception:
        pass

def calculate_accuracy(filename=LOG_FILE):
    """Рассчитывает и выводит итоговую точность ответов бота."""
    if not os.path.exists(filename):
        print("📊 Аналитика: Логов пока нет.")
        return
        
    with open(filename, "r", encoding="utf-8") as f:
        try:
            logs = json.loads(f.read())
        except json.JSONDecodeError:
            print("📊 Аналитика: Ошибка чтения JSON.")
            return

    total = len(logs)
    if total == 0:
        print("📊 Аналитика: Записей нет.")
        return

    successful = sum(1 for log in logs if log.get("is_success", False))
    unsuccessful = total - successful
    accuracy = (successful / total) * 100

    print("\n==================================================")
    print("📊 РЕЗУЛЬТАТЫ АНАЛИЗА ПРОДУКТОВЫХ МЕТРИК ВУЗА:")
    print(f"🔹 Всего тестовых сессий обработано: {total}")
    print(f"✅ Успешно распознано интентов: {successful}")
    print(f"❌ Ошибок распознавания (unknown): {unsuccessful}")
    print(f"🎯 Итоговая точность ответов (Accuracy): {accuracy:.2f}%")
    print("==================================================")

#  Автономное тестирование распознования интентов системы
if __name__ == "__main__":
    if os.path.exists(LOG_FILE):
        os.remove(LOG_FILE)
        
    # Набор тестовых сценариев:
    test_sessions = [
        ("Студент_Иванов", "1"),  # Нажимает Просмотр расписания
        ("Студент_Иванов", "2"),  # Нажимает Домашнее задание
        ("Абитуриент_Гость", "Я абитуриент"),  # Переходит к курсам
        ("Студент_Петров", "1"),  # Снова проверяет расписание
        ("Неизвестный_Ввод", "Какая погода на завтра?")  # Ошибочный интент для теста точности
    ]
    
    print("🚀 Запуск автономного тестирования интентов ")
    print("--------------------------------------------------")
    
    for session_id, msg in test_sessions:
        log_entry = process_user_input(msg, session_id)
        save_log(log_entry)
        print(f"Обработан запрос от {session_id}: {msg[:35]}...")
    
    calculate_accuracy()
