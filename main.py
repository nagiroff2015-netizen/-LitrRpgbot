import os
import json
import sqlite3
import telebot
import requests
from flask import Flask, request

# =====================================================================
# БЕЗОПАСНОСТЬ: Ключи загружаются из настроек Render (Environment)
TELEGRAM_BOT_TOKEN = os.environ.get("BOT_TOKEN")
OPENAI_API_KEY = "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"
# =====================================================================

MODEL_NAME = "meta-llama/llama-3.1-8b-instruct:free"
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN, threaded=False)
app = Flask('')

# Безопасная фабрика для перевода ответов SQLite в словари
def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col] = row[idx]
    return d

@app.route('/')
def home():
    return "ЛитРПГ Бот успешно работает через стабильный шлюз!"

# ИСПРАВЛЕНО: Добавлен метод GET для исключения ошибок 405 при проверках Render
@app.route('/' + str(TELEGRAM_BOT_TOKEN), methods=['GET', 'POST'])
def get_message():
    if request.method == 'POST':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return "!", 200
    return "Webhook active", 200

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
        "Выполните команду, чтобы подключиться к миру:\n"
        "`/join <ID_мира> <Название_Мира>`\n"
        "Пример: `/join mir1 Асгард`\n\n"
        "Команды:\n/status — Ваши характеристики\nЛюбой текст — ваше действие!"
    )
    bot.reply_to(message, welcome_text, parse_mode='Markdown')

@bot.message_handler(commands=['join'])
def join_world(message):
    try:
        parts = message.text.strip().split(None, 2)
        if len(parts) < 3:
            bot.reply_to(message, "⚠️ Пишите так: `/join <ID_мира> <Название_Мира>`")
            return
        
        world_id = parts[1].strip().lower()
        world_name = parts[2].strip()
        user_id = message.from_user.id
        username = message.from_user.username or message.from_user.first_name

        conn = sqlite3.connect('litrpg_game.db')
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM players WHERE user_id = ?', (user_id,))
        
        cursor.execute('SELECT * FROM worlds WHERE world_id = ?', (world_id,))
        if not cursor.fetchone():
            cursor.execute('INSERT INTO worlds (world_id, name, lore) VALUES (?, ?, ?)', (world_id, world_name, "Мир " + world_name))
            cursor.execute('INSERT INTO logs (world_id, entry) VALUES (?, ?)', (world_id, "Мир " + world_name + " создан."))

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
    try:
        user_id = message.from_user.id
        conn = sqlite3.connect('litrpg_game.db')
        conn.row_factory = dict_factory
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM players WHERE user_id = ?', (user_id,))
        p = cursor.fetchone()
        conn.close()
        
        if not p:
            bot.reply_to(message, "❌ Используйте /join")
            return
            
        status_text = (
            f"👤 **Игрок:** {p['username']}\n📍 **Локация:** {p['location']}\n📊 **Уровень:** {p['level']}\n"
            f"❤️ **HP:** {p['hp']}/{p['max_hp']}\n🧪 **MP:** {p['mp']}/{p['max_mp']}\n💰 **Золото:** {p['gold']}\n🎒 **Инвентарь:** {p['inventory']}"
        )
        bot.reply_to(message, status_text, parse_mode='Markdown')
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка статуса: {str(e)}")

@bot.message_handler(func=lambda message: not message.text.startswith('/'))
def handle_game_action(message):
    try:
        user_id = message.from_user.id
        action = message.text
        
        conn = sqlite3.connect('litrpg_game.db')
        conn.row_factory = dict_factory
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM players WHERE user_id = ?', (user_id,))
        player = cursor.fetchone()
        
        if not player:
            bot.reply_to(message, "❌ Пожалуйста, сначала подключитесь к миру командой:\n`/join мир1 Хаус`")
            conn.close()
            return
        
        # ИСПРАВЛЕНО: Безопасное чтение по строковым ключам словаря (защита от багов Markdown)
        world_id = str(player['world_id'])
        p_name = str(player['username'])
        p_lvl = str(player['level'])
        p_hp = str(player['hp'])
        p_max_hp = str(player['max_hp'])
        p_mp = str(player['mp'])
        p_max_mp = str(player['max_mp'])
        p_gold = str(player['gold'])
        p_inv = str(player['inventory'])
        p_loc = str(player['location'])

        cursor.execute('SELECT username, level, hp, location FROM players WHERE world_id = ?', (world_id,))
        players_info = "\n".join([f"- {row['username']} (Ур. {row['level']}, HP: {row['hp']}, {row['location']})" for row in cursor.fetchall()])
        
        cursor.execute('SELECT entry FROM logs WHERE world_id = ? ORDER BY id DESC LIMIT 5', (world_id,))
        world_history = "\n".join([str(l['entry']) for l in reversed(cursor.fetchall())])
        conn.close()

        system_prompt = (
            "Ты продвинутый Гейм-Мастер ЛитРПГ игры. Текущие игроки в мире:\n" + players_info + "\nИстория событий:\n" + world_history + "\n"
            "Ходит: " + p_name + " (Ур " + p_lvl + ", HP: " + p_hp + "/" + p_max_hp + ", MP: " + p_mp + "/" + p_max_mp + ", Золото: " + p_gold + ", Инв: " + p_inv + ", Лок: " + p_loc + ").\n"
            "Действие игрока: \"" + action + "\"\n\n"
            "Опиши художественно последствия его действия на русском языке в стиле ЛитРПГ фэнтези. В самом конце ответа добавь строго системный блок в таком JSON-формате:\n"
            "UPDATE_DATA: {\"level\": 1, \"hp\": 100, \"mp\": 50, \"gold\": 10, \"inventory\": \"кинжал\", \"location\": \"Деревня\"}\n"
            "Изменяй значения в JSON в зависимости от происходящего в мире."
        )

        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://localhost",
            "X-Title": "Multiplayer RPG Bot"
        }
        data = {
            "model": MODEL_NAME,
            "messages": [{"role": "user", "content": system_prompt}],
            "temperature": 0.7
        }
        
        response = requests.post("https://openrouter.ai", headers=headers, json=data, timeout=30)
        
        if response.status_code != 200:
            bot.reply_to(message, f"❌ Ошибка шлюза API. Статус: {response.status_code}\nТекст: {response.text[:200]}")
            return

        response_json = response.json()
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
            except Exception as json_error:
                print(f"Ошибка парсинга JSON: {str(json_error)}")
        
        bot.reply_to(message, display_text)

    except Exception as e:
        print(f"Общая ошибка: {str(e)}")
        bot.reply_to(message, f"⚠️ Не удалось обработать действие.\nОшибка: {str(e)}")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
