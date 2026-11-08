import os
import sys
from flask import Flask, jsonify, request

app = Flask(__name__)

# Железобетонный сквозной поиск файла .env в корневой папке проекта
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(CURRENT_DIR, ".env")

if os.path.exists(env_path):
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            if line.strip() and not line.startswith("#"):
                key, val = line.strip().split("=", 1)
                os.environ[key] = val.strip()

# Подключение ядра обработки конечного автомата чат-бота
from src.message_processor import UniversityBotCore
bot = UniversityBotCore()

# Финальный HTML-шаблон с обновлённым пунктом меню №3 по PEP 8
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>БВШМТИ — Цифровой помощник</title>
    <style>
        body { font-family: Arial, sans-serif; background-color: #f7f5f0; margin: 0; height: 100vh; position: relative; }
        
        /* Позиционирование смартфона в нижнем правом углу экрана */
        .phone-frame { 
            width: 360px; 
            height: 600px; 
            background: white; 
            border: 8px solid #333; 
            border-radius: 36px; 
            box-shadow: 0 20px 40px rgba(0,0,0,0.3); 
            overflow: hidden; 
            display: flex; 
            flex-direction: column; 
            position: fixed;
            bottom: 20px;
            right: 20px;
            z-index: 9999;
        }
        
        .header { background-color: #7a0026; color: white; padding: 15px; text-align: center; font-weight: bold; font-size: 16px; }
        .content { padding: 20px; flex: 1; display: flex; flex-direction: column; justify-content: space-between; box-sizing: border-box; overflow: hidden; }
        .status-box { background: #fdfdfd; border: 1px solid #ddd; border-radius: 12px; padding: 15px; text-align: left; font-size: 14px; color: #333; height: 440px; overflow-y: auto; white-space: pre-line; box-sizing: border-box; }
        .chat-input { width: 100%; padding: 12px; border: 1px solid #ccc; border-radius: 12px; box-sizing: border-box; font-size: 14px; margin-top: 15px; }
    </style>
</head>
<body>

<div class="phone-frame">
    <div class="header">🎭 БВШМТИ — Цифровой помощник</div>
    <div class="content">
        <div id="status" class="status-box">🤖 Вас приветствует цифровой помощник БВШМТИ (Филиал РГИСИ)!

Напишите свою роль в строку ввода, чтобы начать работу:
🔹 студент
🔹 преподаватель
🔹 абитуриент</div>

        <input type="text" id="userInput" class="chat-input" placeholder="Введите ваш ответ или команду..." onkeypress="handleKey(event)">
    </div>
</div>

<script>
    function sendData(textMessage) {
        const statusDiv = document.getElementById('status');
        const originalMsg = textMessage.trim();
        const checkExit = originalMsg.toLowerCase();
        
        statusDiv.innerText = "⏳ Обработка...";
        
        // Экстренный сброс сессии
        if (checkExit === 'выход' || checkExit === 'выйти' || checkExit === 'exit' || checkExit === 'stop') {
            fetch('/process', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: 'выход' })
            })
            .then(() => {
                statusDiv.innerText = "🤖 Сессия успешно завершена.\\n\\nНапишите свою роль в строку ввода, чтобы начать работу:\\n🔹 студент\\n🔹 преподаватель\\n🔹 абитуриент";
            });
            return;
        }

        fetch('/process', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: originalMsg })
        })
        .then(response => response.json())
        .then(data => {
            let finalResponse = data.response;
            
            // 1. Стартовый вывод подсказок при первичном входе в личные кабинеты
            if (finalResponse.includes('Доступные разделы:') && !finalResponse.includes('ведите номер интересующего раздела')) {
                if (finalResponse.includes('кабинет студента')) {
                    finalResponse += "\\n\\n👉 Пожалуйста, выберите раздел цифрой (1 или 2):\\n1. 📅 Расписание\\n2. 🎒 Домашнее задание";
                } else if (finalResponse.includes('кабинет Преподавателя')) {
                    finalResponse += "\\n\\n👉 Пожалуйста, выберите раздел цифрой (от 1 до 4):\\n1. 📅 Просмотр расписания групп\\n2. ❌ Отмена / Перенос занятия\\n3. 🏛️ Забронировать зал\\n4. 🗄️ Мои бронирования";
                }
            }
            
            // 2. Разделение шпаргалок ролей при любых возвратах по коду автомата
            if (finalResponse.includes('возвращены в главное меню')) {
                if (finalResponse.includes('проверить расписание (1)')) {
                    finalResponse += "\\n\\nℹ️ Шпаргалка меню студента (введите 1 или 2):\\n1. 📅 Расписание\\n2. 🎒 Домашнее задание";
                } else {
                    finalResponse = finalResponse.replace(/\\(1, 2 или 3\\):/g, ":");
                    finalResponse = finalResponse.replace(/\\(1, 2 или 3\\)/g, "");
                    finalResponse += "\\n\\nℹ️ Шпаргалка меню преподавателя (введите цифру от 1 до 4):\\n1. 📅 Просмотр расписания групп\\n2. ❌ Отмена / Перенос занятия\\n3. 🏛️ Забронировать зал\\n4. 🗄️ Мои бронирования";
                }
            }
            
            statusDiv.innerText = finalResponse;
            statusDiv.scrollTop = 0;
        })
        .catch(error => {
            statusDiv.innerText = "⚠️ Ошибка связи с сервером Flask.";
            console.error('Error:', error);
        });
    }

    function handleKey(event) {
        if (event.key === 'Enter') {
            const inputField = document.getElementById('userInput');
            const text = inputField.value;
            if (text) {
                sendData(text);
                inputField.value = '';
            }
        }
    }
</script>

</body>
</html>
"""

@app.route("/")
def index():
    return HTML_TEMPLATE

@app.route("/process", methods=["POST"])
def process():
    data = request.get_json()
    user_message = data.get("message", "")
    
    # Жесткий ИАР-сброс состояний на уровне бэкенда
    if user_message.lower().strip() in ['выход', 'выйти', 'exit', 'stop']:
        bot.current_state = "STATE_START"
        bot.current_role = None
        bot.user_group = None
        bot.saved_username = None
        return jsonify({"response": "reset"})
        
    bot_response = bot.process_request(user_message)
    return jsonify({"response": bot_response})

if __name__ == "__main__":
    app.run(debug=False, port=5000)
