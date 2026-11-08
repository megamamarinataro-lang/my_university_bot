import hashlib
import json
import logging
import os
import re
import sqlite3
import time
import smtplib
from email.mime.text import MIMEText
from email.header import Header
import datetime
from datetime import datetime, timedelta
from functools import lru_cache

logger = logging.getLogger("__main__")

STATE_START = "STATE_START"
STATE_WAITING_LOGIN = "STATE_WAITING_LOGIN"
STATE_WAITING_PASSWORD = "STATE_WAITING_PASSWORD"

# Ожидание согласия на персональные данные
STATE_WAITING_FZ152 = "STATE_WAITING_FZ152"    

# Главные контекстные меню личных кабинетов системы
STATE_TEACHER_MENU = "STATE_TEACHER_MENU"      # Главное меню преподавателя
STATE_STUDENT_MENU = "STATE_STUDENT_MENU" # Главное меню студента
STATE_APPLICANT_MENU = "STATE_APPLICANT_MENU"

STATE_WAITING_DAY = "STATE_WAITING_DAY"   # Ожидание выбора дня недели
STATE_WAITING_ROOM_DATE = "STATE_WAITING_ROOM_DATE"  # Ожидание даты для проверки залов
STATE_TEACHER_WAITING_GROUP = "STATE_TEACHER_WAITING_GROUP" #  выбор целевой группы
STATE_WAITING_CANCEL_DAY = "STATE_WAITING_CANCEL_DAY" #  выбор дня для удаления пары
STATE_TEACHER_CANCEL_LESSON = "STATE_TEACHER_CANCEL_LESSON" #удаление пары
STATE_TEACHER_BOOK_DATE = "STATE_TEACHER_BOOK_DATE" # ввод дпты бронирования
STATE_TEACHER_BOOK_ROOM = "STATE_TEACHER_BOOK_ROOM" # выбор сцены или аудитории
STATE_TEACHER_BOOK_LESSON = "STATE_TEACHER_BOOK_LESSON" #  Фиксация номера пары

class UniversityBotCore:  #  Главное ядро обработки логики и состояний чат-бота
    def __init__(self):
        self.current_state = STATE_START
        self.current_role = "guest"
        self.saved_username = None
        
    def get_welcome_message(self):  # Возвращает стартовое приветствие системы
        welcome_text = (
            "🤖 Вас приветствует цифровой помощник вуза! Выберите свою роль "
            "или задайте свой вопрос ниже:\n\n"
            "🔘 [Я преподаватель]\n"
            "🔘 [Я студент]\n"
            "🔘 [Я абитуриент]"
        )
        return welcome_text
    
    def _handle_start_state(self, command):
        """Обрабатывает выбор самой первой кнопки ролей на старте."""
        if "абитуриент" in command or "3" in command:
            self.current_role = "applicant"
            self.current_state = STATE_APPLICANT_MENU  # Переключаем состояние на меню абитуриента
            return (
                "🎒 Вы перешли в Личный кабинет Абитуриента.\n"
                "1. Кафедры вуза\n"
                "2. Вступительные экзамены на зачисление\n"
                "3. Подготовительные курсы\n"
                "4. Документы на зачисление\n"
                "5. Афиша мероприятий и Учебный театр\n"
                "6. FAQ (5 частых вопросов и ответов)\n"
                "7. Контакты деканата\n\n"
                "Пожалуйста, введите цифру нужного пункта (от 1 до 7):"
            )
      
        elif "студент" in command or "преподаватель" in command:
            self.current_state = STATE_WAITING_LOGIN
            self.current_role = "student" if "студент" in command else "teacher"
            return "🔐 Личный кабинет: Пожалуйста, введите ваш логин сайта вуза:"
        
        #  сброс системы при некорректном вводе текстовых команд    
        return "🤖 Извините, я вас не понял. Пожалуйста, напишите вашу роль в строку ввода ниже 👇"

    @lru_cache(maxsize=128)
    def _get_cached_schedule(self, group_name, target_day):
        """Извлекает расписание из базы данных по имени группы и дню недели с кэшированием."""
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "university.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        #  Реляционный SQL-запрос с объединением таблиц JOIN и сортировкой по номерам пар
        cursor.execute('''
            SELECT s.lesson_number, s.subject, c.name 
            FROM schedule s
            JOIN classrooms c ON s.classroom_id = c.id
            WHERE s.group_name = ? AND LOWER(s.day_of_week) = LOWER(?)
            ORDER BY s.lesson_number
        ''', (group_name, target_day.strip()))
        
        rows = cursor.fetchall()
        conn.close()
        return rows

    def _get_week_schedule(self, group_name):
        """Извлекает из базы данных полное расписание группы на всю неделю."""
        #  Определение абсолютного пути к файлу реляционной базы данных
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "university.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        #  # SQL-выборка с кастомным хронологическим ранжированием дней недели через оператор CASE
        cursor.execute('''
            SELECT s.day_of_week, s.lesson_number, s.subject, c.name 
            FROM schedule s
            JOIN classrooms c ON s.classroom_id = c.id
            WHERE s.group_name = ?
            ORDER BY 
                CASE s.day_of_week 
                    WHEN 'понедельник' THEN 1 
                    WHEN 'вторник' THEN 2 
                    WHEN 'среда' THEN 3 
                    WHEN 'четверг' THEN 4 
                    WHEN 'пятница' THEN 5 
                    WHEN 'суббота' THEN 6 
                END, s.lesson_number
        ''', (group_name,))
        
        rows = cursor.fetchall()
        conn.close()
        return rows
    
    def process_request(self, user_input):
        """Главный диспетчер сценариев бота: обрабатывает клики и сообщения с сайта."""
        command = user_input.strip().lower()
        
        # Шаг 1. Стартовый экран ролей
        if self.current_state == STATE_START:
            return self._handle_start_state(command)
            
        # Шаг 2. Получение и сохранение логина
        elif self.current_state == STATE_WAITING_LOGIN:
            self.saved_username = user_input.strip()
            self.current_state = STATE_WAITING_PASSWORD
            return f"👤 Логин '{self.saved_username}' принят. Теперь введите ваш пароль:"
            
        # Шаг 3. Ожидание пароля и проверка по  базе данных
        elif self.current_state == STATE_WAITING_PASSWORD:
            password_input = user_input.strip()
            
            #  Перевод пароля в криптографический SHA-256 хеш
            password_input = hashlib.sha256(password_input.encode('utf-8')).hexdigest()
           
            db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "university.db")
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Безопасный SQL-запрос для извлечения захешированного пароля и флага ФЗ-152
            cursor.execute("SELECT password, group_name, has_accepted_fz152 FROM users WHERE username = ? AND role LIKE ?", 
                          (self.saved_username, self.current_role)
            )
            result = cursor.fetchone()
            conn.close()

            # Финальная логика сверки хэш-сумм и проверки прав доступа
            if result and result[0] == password_input:
                self.user_group = result[1]
                fz152_flag = result[2]
                
                # Если флаг в базе данных равен 0 — вход блокирется и выводится сообщение о необходимости согласия
                if fz152_flag == 0:
                    self.current_state = STATE_WAITING_FZ152
                    return (
                        f"📜 ЮРИДИЧЕСКОЕ СОГЛАШЕНИЕ (ФЗ-152):\n"
                        f"Уважаемый пользователь {self.saved_username}, для продолжения работы на сайте вуза "
                        f"необходимо дать согласие на обработку персональных данных.\n\n"
                        f"В чате введите цифру '1', чтобы поставить виртуальную галочку:\n"
                        f"1. 🔘 Принимаю условия соглашения\n"
                        f"2. ❌ Отклонить"
                    )
                
                # Если в базе уже стоит 1 (согласие дано ранее) — сразу пускаем в меню
                return self._open_user_menu()
            
            else:
                self.current_state = STATE_START
                return "❌ Ошибка! Неверный пароль или учетная запись не найдена. Попробуйте войти заново."

        # Шаг 3.5. Обработка сценария ФЗ-152 и фиксация согласия в СУБД SQLite
        elif self.current_state == STATE_WAITING_FZ152:
            if command == "1" or "принимаю" in command:
                #  Фиксация юридического согласия в реляционной базе данных
                db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "university.db")
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                
                #  Атомарное обновление флага безопасности для текущего пользователя
                cursor.execute("UPDATE users SET has_accepted_fz152 = 1 WHERE username = ?", (self.saved_username,))
                conn.commit()
                conn.close()
                
                return self._open_user_menu()
            
            else:
                self.current_state = STATE_START
                return "❌ Вход заблокирован! Вы отклонили согласие ФЗ-152. Авторизация сброшена."
        
         # Шаг 4. Обработка главного меню студента
        elif self.current_state == STATE_STUDENT_MENU:
            #  Сценарий 1: Переключение автомата на выбор дня расписания
            if "расписание" in command or "1" in command:
                self.current_state = STATE_WAITING_DAY
                return "📅 Выберите день недели для просмотра расписания (например: Понедельник, Вторник):"
            
            #  Сценарий 2: Интеллектуальный вывод актуальных домашних заданий из СУБД SQLite
            elif "домашнее" in command or "задание" in command or "2" in command:
                    # УМНЫЙ ВЫВОД ПРЕДСТОЯЩИХ ДОМАШНИХ ЗАДАНИЙ ИЗ СУБД
                    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "university.db")
                    conn = sqlite3.connect(db_path)
                    cursor = conn.cursor()
                    
                    #  Извлечение всех заданий, привязанных к академической группе авторизованного студента
                    cursor.execute(
                        "SELECT subject, task_text, deadline_date FROM homework WHERE group_name = ?;", 
                        (self.user_group,)
                    )
                    all_tasks = cursor.fetchall()
                    conn.close()
                    
                    if not all_tasks:
                        return f"📦 Для группы {self.user_group} в базе данных пока нет ни одного домашнего задания. Вы свободны!"
                    
                    # Фиксация текущей даты для фильтрации прошлых дедлайнов
                    from datetime import datetime
                    today = datetime.now()


                    reply = f"📦 СПИСОК АКТУАЛЬНЫХ ПРЕДСТОЯЩИХ ДОМАШНИХ ЗАДАНИЙ ({self.user_group}):\n\n"
                    has_active_tasks = False
                    
                    for row in all_tasks:
                        subject, task_text, deadline_str = row
                        
                        try:
                            # Переводим текстовую дату из базы в объект времени для точного сравнения
                            deadline_date = datetime.strptime(deadline_str, "%d.%m.%Y")
                            
                            # ФИЛЬТР: Если дедлайн больше или равен сегодняшнему дню — задание актуально!
                            if deadline_date >= today:
                                reply += f"📖 Предмет: {subject}\n"
                                reply += f"📝 Задание: {task_text}\n"
                                reply += f"📅 Сдать до: {deadline_str}\n"
                                reply += "--------------------------------------------------\n"
                                has_active_tasks = True
                        except Exception:
                            continue
                            
                    if not has_active_tasks:
                        return f"🟢 Все прошлые дедлайны завершены, новых предстоящих заданий для группы {self.user_group} нет! Отдыхайте.\n\nВы можете выбрать другой пункт меню (1, 2):"
                        
                    reply += "\nВы можете выбрать другой пункт меню (1, 2) или написать 'выход':"
                    return reply

            return "🤖 Пожалуйста, выберите пункт '1' (Расписание) или '2' (Домашнее задание) ниже 👇"    
        
        # Шаг 4.7. Сценарий преподавателя. Обработка ввода даты для проверки залов
        elif self.current_state == STATE_WAITING_ROOM_DATE:
            self.current_state = STATE_TEACHER_MENU
            
            db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "university.db")
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            #  Реляционный SQL-запрос с JOIN для извлечения информации о бронированиях
            cursor.execute('''
                SELECT c.name, b.teacher_username, b.lesson_number 
                FROM bookings b
                JOIN classrooms c ON b.classroom_id = c.id
                WHERE b.date = ?
            ''', (user_input.strip(),))
            
            booked_rooms = cursor.fetchall()
            conn.close()
            
            if not booked_rooms:
                return f"🏛️ Статус залов на {user_input}: Все творческие аудитории СВОБОДНЫ для репетиций! 🎉"
                
            reply = f"🏛️ Занятость залов на {user_input}:\n"
            for room in booked_rooms:
                room_name = room[0]
                teacher = room[1]
                lesson_num = room[2]
                #  Перевод номеров учебных пар в реальные часы вуза           
                if lesson_num == 1:
                    time_slot = "09:00 - 10:30"
                elif lesson_num == 2:
                    time_slot = "10:40 - 12:10"
                elif lesson_num == 3:
                    time_slot = "12:40 - 14:10"  
                elif lesson_num == 4:
                    time_slot = "14:20 - 15:50"
                elif lesson_num == 5:
                    time_slot = "16:00 - 17:30"
                else:
                    time_slot = "Время уточняется"
 
                reply += f"🔴 Аудитория '{room_name}': Занята преподавателем {teacher} на пару №{lesson_num} ({time_slot})\n"


        
        # Шаг 4.5. Главное меню преподавателя (Обработка контекстных команд)
        elif self.current_state == STATE_TEACHER_MENU:
            # ПУНКТ 1 НА ЭКРАНЕ: Просмотр личного расписания на неделю
            if "групп" in command or "расписание" in command or "1" in command:
                db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "university.db")
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()

                cursor.execute('''
                    SELECT s.day_of_week, s.lesson_number, s.subject, c.name 
                    FROM schedule s
                    JOIN classrooms c ON s.classroom_id = c.id
                    WHERE LOWER(s.teacher_username) = LOWER(?)
                    ORDER BY 
                        CASE LOWER(s.day_of_week)
                            WHEN 'понедельник' THEN 1 
                            WHEN 'вторник' THEN 2 
                            WHEN 'среда' THEN 3 
                            WHEN 'четверг' THEN 4
                            WHEN 'пятница' THEN 5
                            WHEN 'суббота' THEN 6
                        END, s.lesson_number
                ''', (self.saved_username,))
                rows = cursor.fetchall()
                conn.close()
                
                reply = f"📋 ПОЛНОЕ УЧЕБНОЕ РАСПИСАНИЕ ПРЕПОДАВАТЕЛЯ {self.saved_username} НА НЕДЕЛЮ:\n"
                current_day = ""
                for row in rows:
                    day, num, subj, room = row
                    if day.capitalize() != current_day:
                        current_day = day.capitalize()
                        reply += f"\n🗓️ {current_day}:\n"
                    reply += f"  🔹 Пара №{num}: {subj} — {room}\n"
                reply += "\nВы возвращены в главное меню. Выберите пункт (1, 2 или 3):"
                return reply
                
            #  Переход к сценарию отмены занятия
            elif "отмена" in command or "2" in command:
                self.current_state = STATE_WAITING_CANCEL_DAY
                return "❌ Отмена занятия: Пожалуйста, введите день недели, в который хотите отменить пару (например: Понедельник):"
   
            # ПУНКТ 3 Интерактивное бронирование залов
            elif "забронировать" in command or "зал" in command or "3" in command:
                self.current_state = STATE_TEACHER_BOOK_DATE
                return "🏛️ Бронирование залов: Пожалуйста, введите дату репетиции (например: 07.11.2026):"
            
            # ПУНКТ 4: Извлечение списка всех активных броней текущего сотрудника
            elif "бронирован" in command or "4" in command:
                # Настоящий SQL-запрос с JOIN: связываем таблицы bookings и classrooms
                db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "university.db")
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()

                # SQL-запрос с JOIN: связываем таблицы активных бронирований и залов
                cursor.execute('''
                    SELECT b.date, b.lesson_number, c.name 
                    FROM bookings b 
                    JOIN classrooms c ON b.classroom_id = c.id 
                    WHERE LOWER(b.teacher_username) = LOWER(?)
                    ORDER BY b.date, b.lesson_number;
                ''', (self.saved_username,))
                user_bookings = cursor.fetchall()
                conn.close()
                
                if not user_bookings:
                    return "🗄️ У вас пока нет активных бронирований залов под репетиции в таблице `bookings`.\n\nВы можете выбрать другой пункт меню (1, 2, 3, 4):"
                
                reply = f"🗄️ СПИСОК ВАШИХ АКТИВНЫХ БРОНИРОВАНИЙ ЗАЛОВ:\n"
                for row in user_bookings:
                    b_date, b_num, room_name = row
                    reply += f" 🎭 Зал: '{room_name}' | 📅 Дата: {b_date} | ⏰ Пара №{b_num}\n"
                reply += "\nВы можете выбрать другой пункт меню (1, 2, 3, 4) или написать 'выход':"
                return reply

            return "🤠 Пожалуйста, выберите пункт '1', '2', '3' или '4' ниже 👇"

        # Шаг 4.6. Отмена занятия: Сканирование базы и формирование списка пар
        elif self.current_state == STATE_WAITING_CANCEL_DAY:
            day_to_cancel = command.strip().lower()
            self.saved_cancel_day = day_to_cancel # Сохраняем день в память бота

            # Подключение к реляционной базе данных для проверки расписания
            db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "university.db")
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            #  Поиск учебных занятий преподавателя на конкретный день недели
            cursor.execute('''
                SELECT s.lesson_number, s.subject, s.group_name 
                FROM schedule s
                WHERE LOWER(s.day_of_week) = ? AND LOWER(s.teacher_username) = LOWER(?)
                ORDER BY s.lesson_number
            ''', (day_to_cancel, self.saved_username))
            rows = cursor.fetchall()
            conn.close()

            #  Защитный механизм: Сброс автомата при отсутствии занятий в СУБД
            if not rows:
                self.current_state = STATE_TEACHER_MENU
                return f"⚠️ В базе данных не найдено ваших занятий на день: '{day_to_cancel.capitalize()}'.\n\nВы возвращены в главное меню."
            
            #  Динамическая сборка интерактивного списка найденных пар для вывода
            reply = f"🔍 Найдено занятий на {day_to_cancel.capitalize()}:\n"
            for row in rows:
                num, subj, group = row
                reply += f"🔹 Пара №{num}: {subj} (Группа {group})\n"
                
            reply += "\nПожалуйста, введите номер пары, которую необходимо точечно отменить (цифрой от 1 до 5):"
            self.current_state = STATE_TEACHER_CANCEL_LESSON
            return reply

        # Шаг 4.6.5. Отмена занятия: Точечное удаление строки из базы и ИАР-триггер
        elif self.current_state == STATE_TEACHER_CANCEL_LESSON:
            self.current_state = STATE_TEACHER_MENU # В любом случае возвращаем в меню
            
            try:
                lesson_to_delete = int(command.strip())
            except ValueError:
                return "⚠️ Ошибка: Номер пары должен быть числом. Отмена прервана. Вы возвращены в меню."
                
            db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "university.db")
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Проверяем, существует ли такая пара у преподавателя
            cursor.execute('''
                SELECT group_name FROM schedule 
                WHERE LOWER(day_of_week) = ? AND LOWER(teacher_username) = LOWER(?) AND lesson_number = ?
            ''', (self.saved_cancel_day, self.saved_username, lesson_to_delete))
            row = cursor.fetchone()
            
            if not row:
                conn.close()
                return f"⚠️ Пара №{lesson_to_delete} на {self.saved_cancel_day.capitalize()} не найдена. Вы возвращены в главное меню."
                
            target_group = row[0]
            
            #  1. Извлекаем реальный E-mail студента Иванова из СУБД по его группе
            cursor.execute("SELECT email FROM users WHERE group_name = ? AND role = 'student' LIMIT 1;", (target_group,))
            email_row = cursor.fetchone()
            recipient_email = email_row[0] if email_row and email_row[0] else None
            
            # 2. Удаляем отменяемую пару из таблицы расписания СУБД SQLite
            cursor.execute('''
                DELETE FROM schedule
                WHERE LOWER(day_of_week) = ? AND LOWER(teacher_username) = LOWER(?) AND lesson_number = ?
            ''', (self.saved_cancel_day, self.saved_username, lesson_to_delete))
            
            conn.commit()
            conn.close()

            trigger_status = "ℹ️ Рассылка пропущена (E-mail адрес студента не найден в базе данных СУБД)."

            # 3.  Безопасная отправка письма через Mail.ru
            if recipient_email:
                #  Чтение секретных ключей авторизации из переменных окружения .env
                sender_email = os.environ.get("SENDER_EMAIL", "vasha_pochta@mail.ru")
                sender_password = os.environ.get("SENDER_PASSWORD", "")

                # Формируем контент электронного письма для студента Иванова
                msg_text = (
                    f"Уважаемый студент Иванов И.И.!\n\n"
                    f"Сообщаем, что Преподаватель отменил пару № {lesson_to_delete} "
                    f"в день недели: {self.saved_cancel_day.capitalize()}.\n"
                    f"Занятие автоматически удалено из расписания ."
                )
                msg = MIMEText(msg_text, "plain", "utf-8")
                msg["Subject"] = Header(f"🚨 ИАР-ОПОВЕЩЕНИЕ: Отмена пары №{lesson_to_delete}", "utf-8")
                msg["From"] = sender_email
                msg["To"] = recipient_email

                # Сетевое подключение к защищенному SSL-порту Mail.ru
                try:
                    server = smtplib.SMTP_SSL("smtp.mail.ru", 465, timeout=5)
                    server.login(sender_email, sender_password)
                    server.sendmail(sender_email, [recipient_email], msg.as_string())
                    server.quit()
                    trigger_status = f"📬 [РЕАЛЬНЫЙ ТРИГГЕР ИАР]: Живое электронное письмо успешно отправлено на почту {recipient_email}!"
                except Exception as e:
                    trigger_status = f"⚠️ [СБОЙ СЕТИ]: Не удалось отправить E-mail через Mail.ru. Техническая ошибка: {e}"

            # Возвращаем структурированный ответ в чат бота
                return (
                f"❌ Запрос на отмену занятия принят!\n"
                f"⚡ ИНТЕНТ: Отмена пары №{lesson_to_delete} у группы {target_group}.\n\n"
                f"{trigger_status}\n\n"
                f"Вы возвращены в главное меню преподавателя (1, 2 или 3):"
            )

        # Шаг 4.7. Сценарий Преподавателя: Вывод списка творческих залов для бронирования
        elif self.current_state == STATE_TEACHER_BOOK_DATE:
                date_input = user_input.strip()

                #  Проверка входящего формата даты с помощью регулярных выражений
                if not re.match(r"^\d{2}\.\d{2}\.\d{4}$", date_input):
                    return "⚠️ Некорректный формат даты! Пожалуйста, введите дату строго в формате ДД.ММ.ГГГГ (например: 07.11.2026):"
                        
                self.booking_date = date_input

                #  Подключение к реляционной СУБД SQLite для чтения справочника залов
                db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "university.db")
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT id, name FROM classrooms;")
                rooms = cursor.fetchall()
                print("🔎 ДЕБАГ БАЗЫ ДАННЫХ (Таблица classrooms):", rooms)
                conn.close()
                        
                reply = "🎭 Шаг 2: Выберите и введите ЦИФРУ номера зала для бронирования:\n"
                for r in rooms:
                    reply += f"  🔢 [{r[0]}] — {r[1]}\n"  # Выведет: [1] — Учебная сцена №1, [3] — Тон-ателье
                reply += "\nПожалуйста, введите только цифру номера (например: 3 или 7):"
                        
                self.current_state = STATE_TEACHER_BOOK_ROOM
                return reply

       
        # Шаг  4.8. Бронирование зала: Поиск по цифровому ID и проверка занятости
        elif self.current_state == STATE_TEACHER_BOOK_ROOM:
            room_input = user_input.strip()
            
            db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "university.db")
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            #  Проверка входящего типа данных на строгое соответствие числу
            room_row = None
            if room_input.isdigit():
                cursor.execute("SELECT id, name FROM classrooms WHERE id = ?;", (int(room_input),))
                room_row = cursor.fetchone()

            #  Обработка некорректного выбора зала преподавателем
            if not room_row:
                cursor.execute("SELECT id, name FROM classrooms;")
                all_rooms = cursor.fetchall()
                conn.close()
                
                reply = "⚠️ Неверный выбор! Пожалуйста, введите только ЦИФРУ номера зала из списка:\n"
                for r in all_rooms:
                    reply += f"  🔢 [{r[0]}] — {r[1]}\n"
                return reply
                
            #  Распаковка валидных данных из реляционной СУБД SQLite
            self.booking_room_id = room_row[0]
            self.booking_room_name = room_row[1]
            
            #  Извлечение существующих репетиций из таблицы bookings
            cursor.execute('''
                SELECT lesson_number, teacher_username FROM bookings 
                WHERE date = ? AND classroom_id = ?
            ''', (self.booking_date, self.booking_room_id))
            booked_rows = cursor.fetchall()
            
            #  Вычисление текстового дня недели по календарной дате
            try:
                from datetime import datetime
                date_obj = datetime.strptime(self.booking_date, "%d.%m.%Y")
                days_ru = {
                    0: "понедельник", 1: "вторник", 2: "среда", 
                    3: "четверг", 4: "пятница", 5: "суббота", 6: "воскресенье"
                }
                day_of_week_ru = days_ru[date_obj.weekday()]
            except Exception:
                day_of_week_ru = ""

            cursor.execute('''
                SELECT lesson_number, group_name, subject FROM schedule 
                WHERE LOWER(day_of_week) = ? AND classroom_id = ?
            ''', (day_of_week_ru, self.booking_room_id))
            schedule_rows = cursor.fetchall()
            conn.close()
            
            #  Картирование занятых временных слотов (слияние расписания и броней)
            final_map = {}
            
            #  Интеграция учебных пар
            for s_row in schedule_rows:
                final_map[s_row[0]] = f"Учебная пара группы {s_row[1]} ({s_row[2]})"
                
            #  Интеграция ранее утвержденных репетиций сотрудников
            for b_row in booked_rows:
                final_map[b_row[0]] = f"Репетиция преп. {b_row[1]}"
            
            reply = f"🏛️ Выбран зал: '{self.booking_room_name}'\n"
            reply += f"🗓️ Статус занятости пар на дату {self.booking_date} ({day_of_week_ru.capitalize()}):\n"
            
            for i in range(1, 6):
                # Подставляем точное время творческого вуза
                if i == 1: time_slot = "09:00 - 10:30"
                elif i == 2: time_slot = "10:40 - 12:10"
                elif i == 3: time_slot = "12:40 - 14:10"
                elif i == 4: time_slot = "14:20 - 15:50"
                elif i == 5: time_slot = "16:00 - 17:30"
                
                if i in final_map:
                    reply += f"  ❌ Пара №{i} ({time_slot}): ЗАНЯТО — {final_map[i]}\n"
                else:
                    reply += f"  🟢 Пара №{i} ({time_slot}): СВОБОДНО\n"
                    
            reply += "\nПожалуйста, введите номер СВОБОДНОЙ пары для бронирования (цифрой от 1 до 5)или напишите 'назад' ('0') для возврата к выбору залов:"
            self.current_state = STATE_TEACHER_BOOK_LESSON
            return reply

        # Шаг 4.9. Бронирование зала: Фиксация транзакции записи в СУБД SQLite
        elif self.current_state == STATE_TEACHER_BOOK_LESSON:
            cmd = command.strip().lower()
            
            # ↩️ КНОПКА НАЗАД: возвращаем к выбору залов для этой же даты
            if cmd in ["назад", "0", "back"]:
                self.current_state = STATE_TEACHER_BOOK_ROOM
                
                db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "university.db")
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT id, name FROM classrooms;")
                rooms = cursor.fetchall()
                conn.close()
                
                reply = "↩️ Возврат на предыдущий шаг.\n"
                reply += f"🎭 Дата репетиции сохранена: {self.booking_date}\n"
                reply += "Пожалуйста, выберите и введите ЦИФРУ номера другого зала из списка:\n"
                for r in rooms:
                    reply += f"  🔢 [{r[0]}] — {r[1]}\n"
                reply += "\nПожалуйста, введите номер (или '0' для отмены):"
                return reply
            
            self.current_state = STATE_TEACHER_MENU  # Возвращаем в меню
            
            try:
                lesson_num = int(command.strip())
                if lesson_num < 1 or lesson_num > 5:
                    raise ValueError
            except ValueError:
                return "⚠️ Ошибка: Номер пары должен быть числом от 1 до 5. Вы возвращены в главное меню."
                
            db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "university.db")
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            #  Вычисление текстового дня недели для проверки учебного расписания
            try:
                from datetime import datetime
                date_obj = datetime.strptime(self.booking_date, "%d.%m.%Y")
                days_ru = {
                    0: "понедельник", 1: "вторник", 2: "среда", 
                    3: "четверг", 4: "пятница", 5: "суббота", 6: "воскресенье"
                }
                day_of_week_ru = days_ru[date_obj.weekday()]
            except Exception:
                conn.close()
                return "⚠️ Ошибка обработки даты. Бронирование отменено."
            
            #  Проверка 1: Поиск конфликтов с официальным расписанием студентов
            cursor.execute('''
                SELECT group_name, subject FROM schedule 
                WHERE LOWER(day_of_week) = ? AND classroom_id = ? AND lesson_number = ?
            ''', (day_of_week_ru, self.booking_room_id, lesson_num))
            schedule_conflict = cursor.fetchone()
            
            if schedule_conflict:
                conn.close()
                return (
                    f"❌ Отказано в бронировании! На дату {self.booking_date} ({day_of_week_ru.capitalize()}) "
                    f"в зале '{self.booking_room_name}' на пару №{lesson_num} по учебному расписанию стоит занятие:\n"
                    f"📖 '{schedule_conflict[1]}' у группы {schedule_conflict[0]}.\n\n"
                    f"Внеурочная деятельность не может пересекаться с учебным процессом вуза!"
                )

            #  Проверка 2: Поиск пересечений с репетициями других преподавателей
            cursor.execute('''
                SELECT id FROM bookings 
                WHERE date = ? AND classroom_id = ? AND lesson_number = ?
            ''', (self.booking_date, self.booking_room_id, lesson_num))
            already_booked = cursor.fetchone()
            
            if already_booked:
                conn.close()
                return f"❌ Отказано! Пара №{lesson_num} на дату {self.booking_date} уже занята другой репетицией в базе данных `bookings`."
                
            # Если оба канала чисты — делаем настоящую запись
            cursor.execute('''
                INSERT INTO bookings (teacher_username, classroom_id, date, lesson_number)
                VALUES (?, ?, ?, ?)
            ''', (self.saved_username, self.booking_room_id, self.booking_date, lesson_num))
            
            conn.commit()
            conn.close()
            
            # Перевод пары в часы
            if lesson_num == 1: time_slot = "09:00 - 10:30"
            elif lesson_num == 2: time_slot = "10:40 - 12:10"
            elif lesson_num == 3: time_slot = "12:40 - 14:10"
            elif lesson_num == 4: time_slot = "14:20 - 15:50"
            elif lesson_num == 5: time_slot = "16:00 - 17:30"
            
            return (
                f"✅ УСПЕШНО ЗАБРОНИРОВАНО СТРОГО!\n"
                f"🎭 Зал: {self.booking_room_name}\n"
                f"📅 Дата: {self.booking_date}\n"
                f"⏰ Время: Пара №{lesson_num} ({time_slot})\n"
                f"👤 Преподаватель: {self.saved_username}\n\n"
                f"Данные внесены. Вы возвращены в главное меню."
            )

        #  Шаг 5. Сценарий Абитуриента
        elif self.current_state == STATE_APPLICANT_MENU:
            cmd = command.strip().lower()
            
            #  Команда возврата к списку разделов справочника вуза
            if cmd in ["назад", "0", "back"]:
                return (
                    "🎒 Меню Абитуриента БВШМТИ (Филиал РГИСИ):\n"
                    "1. Кафедры вуза\n"
                    "2. Вступительные экзамены на зачисление\n"
                    "3. Подготовительные курсы\n"
                    "4. Документы на зачисление\n"
                    "5. Афиша мероприятий и Учебный театр\n"
                    "6. FAQ (5 частых вопросов и ответов)\n"
                    "7. Контакты деканата\n\n"
                    "Пожалуйста, введите цифру нужного пункта (от 1 до 7) или напишите 'выход':"
                )
                
            # Команда выход: Возвращаем абитуриента в самое главное стартовое меню выбора ролей
            elif cmd in ["выход", "exit", "quit"]:
                self.current_state = "STATE_WELCOME"
                self.current_role = None 
                return (
                    "🚪 Вы вышли из Личного кабинета Абитуриента.\n\n"
                    "🤖 Добро пожаловать в чат-бот БВШМТИ (Филиал РГИСИ) на Острове Октябрьском!\n"
                    "Пожалуйста, выберите вашу роль:\n"
                    "1. Я студент\n"
                    "2. Я преподаватель\n"
                    "3. Я абитуриент / Гость вуза\n\n"
                    "Введите цифру роли (1, 2 или 3):"
                )
                        
            #  Чтение справочного контента
            if self.current_state == STATE_APPLICANT_MENU and cmd.isdigit() and 1 <= int(cmd) <= 7:

                db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "university.db")
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                
                cursor.execute("SELECT content FROM applicant_info WHERE id = ?;", (int(cmd),))
                info_row = cursor.fetchone()
                conn.close()
                
                if info_row:
                    clean_text = info_row[0] 
                    return (
                        f"{clean_text}\n\n"
                        f"--------------------------------------------------\n"
                        f"🎒 Вы можете ввести цифру другого пункта (1-7), написать 'назад' ('0') для вывода меню или 'выход':"
                    )
                
        # Шаг 6. Сценарий Студента: Вывод учебного расписания на выбранный день
        elif self.current_state == STATE_WAITING_DAY:
            self.current_state = STATE_STUDENT_MENU  # Удерживаем пользователя в аккаунте
            
            # Отправляем запрос в базу по слову, которое ввёл студент ("Понедельник", "Среда")
            schedule_rows = self._get_cached_schedule(self.user_group, command)
            
            if not schedule_rows:
                return (
                    f"📅 Расписание на {user_input.strip()}: Занятий не найдено.\n\n"
                    "Вы возвращены в главное меню. Вы можете проверить расписание (1) или выйти. 🤖"
                )
                
            reply = f"📅 Расписание группы {self.user_group} на {user_input.strip()}:\n"
            for row in schedule_rows:
                lesson_num, subject, room = row
                reply += f"🔹 Пара №{lesson_num}: {subject} — {room}\n"
                
            reply += "\nВы возвращены в главное меню. Вы можете проверить расписание (1) или выйти. 🤖"
                    
            return reply
   
    def _open_user_menu(self):
        """Внутренний переключатель: открывает нужное меню в зависимости от роли."""
        if self.current_role == "student":
            self.current_state = STATE_STUDENT_MENU
            return (
                f"🎉 Успешный вход! Добро пожаловать в личный кабинет студента!\n"
                "Доступные разделы:\n"
                "1. 📅 Расписание\n"
                "2. 🎒 Домашнее задание"
            )
        else:
            self.current_state = STATE_TEACHER_MENU
            return (
                f"👨‍🏫 Успешный вход! Добро пожаловать в личный кабинет Преподавателя!\n"
                "Доступные разделы:\n"
                "1. 📅 Просмотр расписания\n"
                "2. ❌ Отмена / Перенос занятия\n"
                "3. 🏛️ Забронировать зал\n"
                "4. 🗄️ Мои бронирования"
            )
    