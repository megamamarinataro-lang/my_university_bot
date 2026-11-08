import asyncio
import os
import sys
import time

from src.logger_config import calculate_accuracy, create_log_entry, save_log
from src.message_processor import UniversityBotCore

# Автоматически находим точный путь к файлу .env 
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")

if os.path.exists(env_path):
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            if line.strip() and not line.startswith("#"):
                key, val = line.strip().split("=", 1)
                os.environ[key] = val.strip()


async def main():
    """Главная пусковая функция текстового терминала цифрового помощника вуза."""
    bot = UniversityBotCore()
    
    # Замер времени обработки и вывод стартового приветствия системы
    start_time_welcome = time.time()
    welcome_text = bot.get_welcome_message()
    exec_time_welcome_ms = int((time.time() - start_time_welcome) * 1000)
    
    print(welcome_text)
    print("-" * 50)
    
    # Фиксация системного старта чат-бота в журнал продуктовой аналитики
    welcome_log = create_log_entry(
        session_id="Guest",
        user_message="старт_системы",
        intent="start_bot",
        is_success=True,
        response_text=str(welcome_text),
        confidence_score=1.0,
        response_time_ms=exec_time_welcome_ms
    )
    save_log(welcome_log)
    
    # Бесконечный интерактивный цикл опроса команд пользователя в консоли
    while True:
        try:
            user_input = input("⌨️ Вы: ")
            
            # Принудительное завершение сессии с выводом продуктовых метрик точности
            if user_input.strip().lower() in ["выход", "exit", "stop"]:
                calculate_accuracy()  # Генерация итоговой таблицы Accuracy
                print("🤖 Тестирование завершено. Сессия успешно закрыта!")
                break
                
            # 1. Точечный ИАР-мониторинг времени отклика СУБД SQLite в миллисекундах
            start_time = time.time()
            response = bot.process_request(str(user_input))
            response_time_ms = int((time.time() - start_time) * 1000)
            
            # Защита от нулевого времени выполнения
            if response_time_ms == 0:
                response_time_ms = 1
            
            print(f"Бот: {response}")
            print("-" * 50)
            
            # 2. Вычисление параметров успешности распознавания интента чат-бота
            is_success = (
                True if response 
                and "не понял" not in response.lower() 
                and "не распознана" not in response.lower() 
                else False
            )
            confidence = 1.0 if is_success else 0.0
            
            # Извлечение текущего контекстного состояния автомата
            intent_name = bot.current_state if hasattr(bot, 'current_state') else "unknown"
            if not is_success:
                intent_name = "unknown"
                
            # Динамическое определение уникального идентификатора сессии (ID)
            session_id = getattr(bot, 'user_group', 'Guest')
            if not session_id and getattr(bot, 'saved_username', None):
                session_id = bot.saved_username
            elif not session_id:
                session_id = "Guest"
                
            # 3. Формирование структурированной лог-записи
            log_entry = create_log_entry(
                session_id=str(session_id),
                user_message=str(user_input),
                intent=str(intent_name),
                is_success=is_success,
                response_text=str(response),
                confidence_score=confidence,
                response_time_ms=response_time_ms
            )
            
            # 4. Сохранение метрики в JSON-журнал с автоматическим форматированием отступов
            save_log(log_entry)
            
        except (KeyboardInterrupt, EOFError):
            print("\n🤖 Программа принудительно завершена пользователем.")
            break


if __name__ == "__main__":
    asyncio.run(main())
