import os
import json
import sqlite3
import telebot
import requests
from threading import Thread
from flask import Flask, request

# =====================================================================
# ВАШИ ЖИВЫЕ КЛЮЧИ АВТОМАТИЧЕСКИ ПОДТЯГИВАЮТСЯ:
TELEGRAM_BOT_TOKEN = os.environ.get("BOT_TOKEN")
OPENAI_API_KEY = "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"
# =====================================================================

MODEL_NAME = "google/gemini-2.5-flash"
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN, threaded=False)
app = Flask('')

RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL")

@app.route('/')
def home():
    return "ЛитРПГ Бот успешно работает через Webhook!"

@app.route('/' + TELEGRAM_BOT_TOKEN, methods=['POST'])
def get_message():
    json_string = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return "!", 200

def init_db():
    conn = sqlite3.connect('litrpg_game.db')
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS worlds (world_id TEXT PRIMARY KEY, name TEXT, lore TEXT)')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS players (
            user_id INTEGER PRIMARY KEY, username TEXT, world_id TEXT, level INTEGER,
            hp INTEGER, max_hp INTEGER, mp INTEGER, max_mp INTEGER, gold INTEGER, inventory TEXT, location TEXT
        )
    ''')
    cursor.execute('CREATE TABLE IF NOT EXISTS logs (id INTEGER PRIMARY KEY AUTOINCREMENT, world_id TEXT, entry TEXT)')
    conn.commit()
    conn.close()

init_db()

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = (
        "⚔️ **Добро пожаловать в многопользовательскую ЛитРПГ песочницу!** ⚔️\n\n"
        "Вы можете играть в одном мире с друзьями со своих устройств независимо!\n\n"
        "Выполните команду, чтобы подключиться к миру:\n"
        "`/join <ID_мира> <Название_Мира>`\n"
        "Пример: `/join mir1 Асгард` (все, кто введут один ID, окажутся вместе)\n\n"
        "Команды:\n/status — Ваши характеристики\nЛюбой текст — ваше действие!"
    )
    bot.reply_to(message, welcome_text, parse_mode='Markdown')

@bot.message_handler(commands=['join'])
def join_world(message):
    try:
        args = message.text.split(maxsplit=2)
        if len(args) < 3:
            bot.reply_to(message, "⚠️ Пишите так: `/join <ID_мира> <Название_Мира>`")
            return
        
        world_id = args[1].strip().lower()
        world_name = args[2].strip()
        user_id = message.from_user.id
        username = message.from_user.username or message.from_user.first_name

        conn = sqlite3.connect('litrpg_game.db')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM worlds WHERE world_id = ?', (world_id,))
        if not cursor.fetchone():
            cursor.execute('INSERT INTO worlds (world_id, name, lore) VALUES (?, ?, ?)', (world_id, world_name, "Мир " + world_name))
            cursor.execute('INSERT INTO logs (world_id, entry) VALUES (?, ?)', (world_id, "Мир " + world_name + " создан."))

        cursor.execute('SELECT * FROM players WHERE user_id = ?', (user_id,))
        if cursor.fetchone():
            cursor.execute('UPDATE players SET world_id = ? WHERE user_id = ?', (world_id, user_id))
        else:
            cursor.execute('''
                INSERT INTO players (user_id, username, world_id, level, hp, max_hp, mp, max_mp, gold, inventory, location)
                VALUES (?, ?, ?, 1, 100, 100, 50, 50, 10, '📜 Карта, 🗡️ Кинжал', 'Стартовая деревня')
            ''', (user_id, username, world_id))
        conn.commit()
        conn.close()
        bot.reply_to(message, f"✨ Вы успешно вошли в мир **{world_name}**! Напишите любое действие, чтобы начать.")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка при входе в мир: {str(e)}")

@bot.message_handler(commands=['status'])
def show_status(message):
    user_id = message.from_user.id
    conn = sqlite3.connect('litrpg_game.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM players WHERE user_id = ?', (user_id,))
    p = cursor.fetchone()
    conn.close()
    if not p:
        bot.reply_to(message, "❌ Вы не вошли в мир. Используйте /join")
        return
    status_text = (
        f"👤 **Игрок:** {p[1]}\n📍 **Локация:** {p[10]}\n📊 **Уровень:** {p[3]}\n"
        f"❤️ **HP:** {p[4]}/{p[5]}\n🧪 **MP:** {p[6]}/{p[7]}\n💰 **Золото:** {p[8]}\n🎒 **Инвентарь:** {p[9]}"
    )
    bot.reply_to(message, status_text, parse_mode='Markdown')

@bot.message_handler(func=lambda message: not message.text.startswith('/'))
def handle_game_action(message):
    user_id = message.from_user.id
    action = message.text
    
    conn = sqlite3.connect('litrpg_game.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM players WHERE user_id = ?', (user_id,))
    player = cursor.fetchone()
    
    if not player:
        bot.reply_to(message, "❌ Пожалуйста, сначала подключиться к миру командой:\n`/join мир1 Хаус`")
        conn.close()
        return
    
    world_id = player[2]
    p_name = player[1]
    p_lvl = player[3]
    p_hp = player[4]
    p_max_hp = player[5]
    p_mp = player[6]
    p_max_mp = player[7]
    p_gold = player[8]
    p_inv = player[9]
    p_loc = player[10]

    cursor.execute('SELECT username, level, hp, location FROM players WHERE world_id = ?', (world_id,))
    players_info = "\n".join([f"- {p[0]} (Ур. {p[1]}, HP: {p[2]}, Локация: {p[3]})" for p in cursor.fetchall()])
    cursor.execute('SELECT entry FROM logs WHERE world_id = ? ORDER BY id DESC LIMIT 5', (world_id,))
    world_history = "\n".join([l[0] for l in reversed(cursor.fetchall())])
    conn.close()

    system_prompt = (
        "Ты продвинутый Гейм-Мастер ЛитРПГ игры. Текущие игроки в мире:\n" + players_info + "\nИстория событий:\n" + world_history + "\n"
        f"Ходит: {p_name} (Ур {p_lvl}, HP: {p_hp}/{p_max_hp}, MP: {p_mp}/{p_max_mp}, Золото: {p_gold}, Инв: {p_inv}, Лок: {p_loc}).\n"
        f"Действие: \"{action}\"\n\n"
        "Опиши художественно последствия его действия на русском языке в стиле ЛитРПГ фэнтези. В самом конце ответа добавь строго системный блок в таком JSON-формате:\n"
        "UPDATE_DATA: {\"level\": 1, \"hp\": 100, \"mp\": 50, \"gold\": 10, \"inventory\": \"кинжал\", \"location\": \"Деревня\"}\n"
        "Изменяй значения в JSON в зависимости от происходящего в мире (нанесение урона, изменение золота или локации)."
    )

    try:
        headers = {
            "Authorization": "Bearer " + OPENAI_API_KEY, 
            "Content-Type": "application/json",
            "HTTP-Referer": "https://localhost",
            "X-Title": "Multiplayer RPG Bot"
        }
        data = {"model": MODEL_NAME, "messages": [{"role": "user", "content": system_prompt}]}
        
        response = requests.post("https://openrouter.ai", headers=headers, json=data, timeout=30)
        
        # ДИАГНОСТИКА: Проверяем статус ответа сервера
        if response.status_code != 200:
            bot.send_message(message.chat.id, f"❌ Ошибка сервера OpenRouter (Код {response.status_code}):\n{response.text[:200]}")
            return
            
        try:
            response_json = response.json()
        except Exception:
            bot.send_message(message.chat.id, f"❌ Ошибка разбора ответа. Сервер вернул текст вместо JSON:\n{response.text[:200]}")
            return
        
        ai_reply = response_json['choices'][0]['message']['content']
        display_text = ai_reply

        if "UPDATE_DATA:" in ai_reply:
            try:
                start_idx = ai_reply.find("{")
                end_idx = ai_reply.rfind("}") + 1
                json_str = ai_reply[start_idx:end_idx]
                display_text = ai_reply[:ai_reply.find("UPDATE_DATA:")].strip()
                
                data_parsed = json.loads(json_str)
                conn = sqlite3.connect('litrpg_game.db')
                cursor = conn.cursor()
                cursor.execute('UPDATE players SET level=?, hp=?, mp=?, gold=?, inventory=?, location=? WHERE user_id=?', 
                               (data_parsed['level'], data_parsed['hp'], data_parsed['mp'], data_parsed['gold'], data_parsed['inventory'], data_parsed['location'], user_id))
                cursor.execute('INSERT INTO logs (world_id, entry) VALUES (?, ?)', (world_id, f"[{data_parsed['location']}] {p_name}: {action}"))
                conn.commit()
                conn.close()
            except Exception as e:
                print("Ошибка БД:", e)
        
        bot.send_message(message.chat.id, display_text)
    except Exception as e: 
        bot.send_message(message.chat.id, f"📴 Сбой в коде: {str(e)}")

if __name__ == '__main__':
    bot.remove_webhook()
    if RENDER_EXTERNAL_URL:
        bot.set_webhook(url=RENDER_EXTERNAL_URL + '/' + TELEGRAM_BOT_TOKEN)
    
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
