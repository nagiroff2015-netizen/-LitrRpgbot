import os
import json
import sqlite3
import telebot
import requests
from flask import Flask, request

# =====================================================================
# ВСТАВЛЕН СВЕЖИЙ РАБОЧИЙ КЛЮЧ НЕЙРОСЕТИ С ЛИМИТАМИ:
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
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        bot.reply_to(message, "⚠️ Пишите так: `/join <ID_мира> <Название_Мира>`")
        return
    
    world_id = args[1].lower()
    world_name = args[2]
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name

    conn = sqlite3.connect('litrpg_game.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM worlds WHERE world_id = ?', (world_id,))
    if not cursor.fetchone():
        cursor.execute('INSERT INTO worlds (world_id, name, lore) VALUES (?, ?, ?)', (world_id, world_name, f"Мир {world_name}"))
        cursor.execute('INSERT INTO logs (world_id, entry) VALUES (?, ?)', (world_id, f"Мир {world_name} создан."))

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
    bot.reply_to(message, f"✨ Вы вошли в мир **{world_name}**! Напишите любое действие, чтобы начать.")

@bot.message_handler(commands=['status'])
def show_status(message):
    user_id = message.from_user.id
    conn = sqlite3.connect('litrpg_game.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM players WHERE user_id = ?', (user_id,))
    p = cursor.fetchone()
    conn.close()
    if not p:
        bot.reply_to(message, "❌ Используйте /join")
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
        bot.reply_to(message, "❌ Используйте /join")
        conn.close()
        return
    
    world_id = player[2]
    cursor.execute('SELECT username, level, hp, location FROM players WHERE world_id = ?', (world_id,))
    players_info = "\n".join([f"- {p[0]} (Ур. {p[1]}, HP: {p[2]}, Локация: {p[3]})" for p in cursor.fetchall()])
    cursor.execute('SELECT entry FROM logs WHERE world_id = ? ORDER BY id DESC LIMIT 5', (world_id,))
    world_history = "\n".join([l[0] for l in reversed(cursor.fetchall())])
    conn.close()

    system_prompt = (
        f"Ты Гейм-Мастер ЛитРПГ игры. Текущие игроки в мире:\n{players_info}\nИстория последних событий:\n{world_history}\n"
        f"Ходит: {player[1]} (Ур {player[3]}, HP: {player[4]}/{player[5]}, MP: {player[6]}/{player[7]}, Золото: {player[8]}, Инв: {player[9]}, Лок: {player[10]}).\nДействие: \"{action}\"\n"
        "Опиши художественно последствия на русском языке. В самом конце ответа добавь строго системный блок в таком JSON-формате:\n"
        f"UPDATE_DATA: {{\"level\": {player[3]}, \"hp\": {player[4]}, \"mp\": {player[6]}, \"gold\": {player[8]}, \"inventory\": \"{player[9]}\", \"location\": \"{player[10]}\"}}\n"
        "Изменяй значения в JSON в зависимости от происходящего в мире (получил опыт/урон, нашел золото, сменил локацию)."
    )

    try:
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}", 
            "Content-Type": "application/json", 
            "HTTP-Referer": "https://localhost",
            "X-Title": "RPG Bot"
        }
        data = {"model": MODEL_NAME, "messages": [{"role": "user", "content": system_prompt}]}
        response = requests.post("https://openrouter.ai", headers=headers, json=data)
        
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
                cursor.execute('INSERT INTO logs (world_id, entry) VALUES (?, ?)', (world_id, f"[{data_parsed['location']}] {player[1]}: {action}"))
                conn.commit()
                conn.close()
            except Exception as e:
                print("Ошибка БД:", e)
        bot.send_message(message.chat.id, display_text)
    except Exception as e: 
        bot.send_message(message.chat.id, f"📴 Сбой ИИ (сервер перегружен, попробуйте еще раз).")

if __name__ == '__main__':
    bot.remove_webhook()
    if RENDER_EXTERNAL_URL:
        bot.set_webhook(url=RENDER_EXTERNAL_URL + '/' + TELEGRAM_BOT_TOKEN)
    
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
