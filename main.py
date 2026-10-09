import os
import json
import random
import sqlite3
import telebot
from flask import Flask, request

# =====================================================================
# ВШИТ ТОЛЬКО ТОКЕН БОТА (КЛЮЧИ ИИ БОЛЬШЕ ВООБЩЕ НЕ НУЖНЫ!)
TELEGRAM_BOT_TOKEN = os.environ.get("BOT_TOKEN")
# =====================================================================

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN, threaded=False)
app = Flask('')

def get_db_connection():
    conn = sqlite3.connect('litrpg_game.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def home():
    return "ЛитРПГ Бот на встроенном игровом движке запущен!"

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

# Локальный игровой движок вместо ломающихся внешних ИИ
def generate_game_response(p_name, p_loc, p_lvl, p_hp, p_mp, p_gold, p_inv, user_action):
    # Наборы случайных художественных событий
    encounters = [
        "Вы встречаете бродячего торговца редкими эликсирами. Он предлагает вам сделку, но внезапно в кустах раздается шорох.",
        "Перед вами раскинулись древние руины, покрытые светящимся мхом. Из темноты доносится эхо шагов.",
        "Навстречу вам выскакивает свирепый Гоблин-Налётчик [Ур.2], размахивая ржавым тесаком!",
        "Вы находите спрятанный под корнями старого дуба сундук, на котором мерцают магические руны.",
        "Вы натыкаетесь на заброшенный лагерь авантюристов. Костер еще тлеет, а на земле видны следы спешного отступления."
    ]
    
    outcomes = [
        "Благодаря вашей бдительности, вы успешно справляетесь с угрозой! Враг повержен, а вы собираете трофеи.",
        "Вы аккуратно исследуете окружение, избегая скрытых ловушек, и находите ценные ресурсы.",
        "Внезапная вспышка магии отбрасывает вас назад! Вы теряете немного сил, но получаете крупицу опыта.",
        "Ваше действие привлекает внимание местного духа-хранителя. Он одобряет вашу смелость и дарует благословение.",
        "Происходит неожиданное: земля уходит из-под ног, и вы скатываетесь в скрытую подземную пещеру!"
    ]
    
    # Случайным образом рассчитываем изменение характеристик
    change_hp = random.randint(-15, 10)
    change_gold = random.randint(2, 8)
    change_mp = random.randint(-5, 5)
    
    new_hp = max(10, min(100, int(p_hp) + change_hp))
    new_gold = max(0, int(p_gold) + change_gold)
    new_mp = max(0, min(50, int(p_mp) + change_mp))
    new_lvl = int(p_lvl)
    
    # Небольшой шанс поднять уровень
    if random.random() > 0.8:
        new_lvl += 1
        level_up_msg = f"\n\n✨ **ВНИМАНИЕ: УРОВЕНЬ ПОВЫШЕН! Теперь вы {new_lvl} уровня!** ✨"
    else:
        level_up_msg = ""
        
    locations = ["Стартовая деревня", "Мрачный лес", "Древние руины", "Пещера гоблинов", "Торговый тракт"]
    new_loc = random.choice(locations) if "идти" in user_action.lower() or "идти" in user_action.lower() else p_loc

    story = (
        f"📖 **Событие:** Вы решили: *\"{user_action}\"* в локации **{p_loc}**.\n\n"
        f"🧭 {random.choice(encounters)}\n"
        f"⚔️ {random.choice(outcomes)}"
        f"{level_up_msg}\n\n"
        f"📊 **Изменения:** HP: {change_hp:+} | Золото: {change_gold:+}💰"
    )
    
    # Возвращаем художественный текст и готовый словарь для базы данных
    db_data = {
        "level": new_lvl,
        "hp": new_hp,
        "mp": new_mp,
        "gold": new_gold,
        "inventory": p_inv,
        "location": new_loc
    }
    
    return story, db_data
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

        conn = get_db_connection()
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
        conn = get_db_connection()
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
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM players WHERE user_id = ?', (user_id,))
        player = cursor.fetchone()
        
        if not player:
            bot.reply_to(message, "❌ Пожалуйста, сначала подключитесь к миру командой:\n`/join мир1 Хаус`")
            conn.close()
            return
        
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
        conn.close()

        # Генерируем ответ локально на сервере БЕЗ ЗАПРОСОВ К ИИ
        display_text, data_parsed = generate_game_response(p_name, p_loc, p_lvl, p_hp, p_mp, p_gold, p_inv, action)

        # Обновляем базу данных
        conn = sqlite3.connect('litrpg_game.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE players SET level=?, hp=?, mp=?, gold=?, inventory=?, location=? WHERE user_id=?', 
                       (data_parsed['level'], data_parsed['hp'], data_parsed['mp'], data_parsed['gold'], data_parsed['inventory'], data_parsed['location'], user_id))
        cursor.execute('INSERT INTO logs (world_id, entry) VALUES (?, ?)', (world_id, f"[{data_parsed['location']}] {p_name}: {action}"))
        conn.commit()
        conn.close()
        
        bot.reply_to(message, display_text, parse_mode='Markdown')

    except Exception as e:
        print(f"Общая ошибка: {str(e)}")
        bot.reply_to(message, f"⚠️ Не удалось обработать действие.\nОшибка: {str(e)}")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
