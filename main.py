import os
import json
import sqlite3
import telebot
import requests
from flask import Flask, request

# =====================================================================
# ВАШИ ЖИВЫЕ КЛЮЧИ НАМЕРТВО ВШИТЫ СЮДА:
TELEGRAM_BOT_TOKEN = os.environ.get("BOT_TOKEN")
SAMBANOVA_API_KEY = "3cb477c6-85c4-4392-bd94-f3df9c74911b"
# =====================================================================

MODEL_NAME = "meta-llama/Llama-3.1-8B-Instruct"
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN, threaded=False)
app = Flask('')

RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL")

@app.route('/')
def home():
    return "ЛитРПГ Бот успешно работает на SambaNova!"

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
        "Вы можете играть в одном мире с друзьями независимо с разных устройств!\n\n"
        "Выполните команду, чтобы подключиться к миру:\n"
        "`/join <ID_мира> <Название_Мира>`\n"
        "Пример: `/join mir1 Асгард`\n\n"
        "Команды:\n/status — Ваши характеристики\nЛюбой текст — ваше действие!"
    )
    bot.reply_to(message, welcome_text, parse_mode='Markdown')

@bot.message_handler(commands=['join'])
def join_world(message):
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        bot.reply_to(message, "⚠️ Пишите так: `/join <ID_мира> <Название_Мира>`")
        return
    
    world_id = args.strip().lower()
    world_name = args.strip()
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
    bot.reply_to(message, f"✨ Вы успешно вошли в мир **{world_name}**! Напишите любое действие, чтобы начать.")

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
        f"👤 **Игрок:** {p}\n📍 **Локация:** {p}\n📊 **Уровень:** {p}\n"
        f"❤️ **HP:** {p}/{p}\n🧪 **MP:** {p}/{p}\n💰 **Золото:** {p}\n🎒 **Инвентарь:** {p}"
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
    
    world_id = player
    cursor.execute('SELECT username, level, hp, location FROM players WHERE world_id = ?', (world_id,))
    players_info = "\n".join([f"- {p} (Ур. {p}, HP: {p}, Локация: {p})" for p in cursor.fetchall()])
    cursor.execute('SELECT entry FROM logs WHERE world_id = ? ORDER BY id DESC LIMIT 5', (world_id,))
    world_history = "\n".join([l for l in reversed(cursor.fetchall())])
    conn.close()

    system_prompt = (
        f"Ты продвинутый Гейм-Мастер ЛитРПГ игры. Текущие игроки в мире:\n{players_info}\nИстория последних событий:\n{world_history}\n"
        f"Ходит: {player} (Ур {player}, HP: {player}/{player}, MP: {player}/{player}, Золото: {player}, Инв: {player}, Лок: {player}).\nДействие: \"{action}\"\n"
        "Опиши художественно последствия его действия на русском языке в стиле ЛитРПГ фэнтези. В самом конце ответа добавь строго системный блок в таком JSON-формате:\n"
        f"UPDATE_DATA: {{\"level\": {player}, \"hp\": {player}, \"mp\": {player}, \"gold\": {player}, \"inventory\": \"{player}\", \"location\": \"{player}\"}}\n"
        "Изменяй значения в JSON в зависимости от происходящего в мире (получил опыт/урон, нашел золото, сменил локацию)."
    )

    try:
        headers = {
            "Authorization": f"Bearer {SAMBANOVA_API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": MODEL_NAME,
            "messages": [{"role": "user", "content": system_prompt}],
            "temperature": 0.7
        }
        response = requests.post("https://sambanova.ai", headers=headers, json=data)
        response_json = response.json()
        ai_reply = response_json['choices']['message']['content']
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
                cursor.execute('INSERT INTO logs (world_id, entry) VALUES (?, ?)', (world_id, f"[{data_parsed['location']}] {player}: {action}"))
                conn.commit()
                conn.close()
            except Exception as e:
                print("Ошибка БД:", e)
        bot.send_message(message.chat.id, display_text)
    except Exception as e: 
        bot.send_message(message.chat.id, f"📴 Ошибка обработки мира ИИ. Попробуйте еще раз.")

if __name__ == '__main__':
    bot.remove_webhook()
    if RENDER_EXTERNAL_URL:
        bot.set_webhook(url=RENDER_EXTERNAL_URL + '/' + TELEGRAM_BOT_TOKEN)
    
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
