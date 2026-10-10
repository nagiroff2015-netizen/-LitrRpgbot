import os
import json
import random
import sqlite3
import telebot
import requests
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
    return "ЛитРПГ Бот на гибридном неубиваемом движке запущен!"

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

# Локальный резервный генератор сюжета, если внешний ИИ перегружен
def generate_fallback_story(p_name, p_loc, p_lvl, p_hp, p_mp, p_gold, p_inv, user_action):
    encounters = [
        "Внезапно из тени вековых деревьев на вас устремляется разъяренный Гоблин-Налетчик [Ур.2], размахивая зазубренным клинком!",
        "Вы натыкаетесь на заброшенную стоянку рыцарей ордена Сияющей Зари. Среди потухших углей что-то слабо поблескивает.",
        "Перед вами появляется загадочный бродячий маг в разорванной мантии. Он предлагает вам сыграть в кости на крупицу тайных знаний.",
        "Вы исследуете местность и замечаете скрытый под корнями старого дуба сундук, опутанный светящимися магическими рунами.",
        "Тропа резко обрывается. Вы упираетесь в массивные кованые врата, ведущие вглубь заброшенных гномьих шахт."
    ]
    outcomes = [
        "Мгновенно среагировав, вы совершаете обманный маневр! Враг повержен, а ваша сумка пополняется ценными трофеями.",
        "Внимательно осмотрев окружение, вы успешно избегаете скрытой ловушки-растяжки и находите мешочек со старыми монетами.",
        "Происходит неожиданный магический резонанс! Волна чистой энергии отбрасывает вас назад, заставляя кровь бурлить от прилива сил.",
        "Ваши действия привлекают внимание невидимого духа этих мест. Он одобряет вашу решимость и дарует легкое благословение.",
        "Удача на вашей стороне! Вы находите тайный лаз и успешно продвигаетесь вперед, собирая по пути полезные ресурсы."
    ]
    
    change_hp = random.randint(-15, 10)
    change_gold = random.randint(2, 8)
    new_hp = max(10, min(100, int(p_hp) + change_hp))
    new_gold = max(0, int(p_gold) + change_gold)
    new_lvl = int(p_lvl)
    
    if random.random() > 0.85:
        new_lvl += 1
        lvl_up = f"\n\n✨ **ВНИМАНИЕ: Ваш уровень повысился! Теперь вы {new_lvl} уровня!** ✨"
    else:
        lvl_up = ""
        
    locations = ["Стартовая деревня", "Мрачный лес", "Древние руины", "Пещера гоблинов", "Забытый тракт"]
    new_loc = random.choice(locations) if "идти" in user_action.lower() or "шаг" in user_action.lower() else p_loc

    story = (
        f"📖 **Гейм-Мастер ведет повествование:**\nВы решили совершить действие: *\"{user_action}\"* в локации **{p_loc}**.\n\n"
        f"🧭 {random.choice(encounters)}\n\n"
        f"⚔️ {random.choice(outcomes)}{lvl_up}\n\n"
        f"UPDATE_DATA: {{\"level\": {new_lvl}, \"hp\": {new_hp}, \"mp\": {p_mp}, \"gold\": {new_gold}, \"inventory\": \"{p_inv}\", \"location\": \"{new_loc}\"}}"
    )
    return story

# ГИБРИДНАЯ ФУНКЦИЯ: Пытается вызвать ИИ, но если он лежит — САМА мгновенно генерирует ролевой ответ
def ask_free_rpg_ai(system_prompt, user_action, player_fallback_data):
    try:
        url = "https://pollinations.ai"
        payload = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_action}
            ],
            "model": "openai-gpt-4o",
            "jsonMode": False
        }
        res = requests.post(url, json=payload, timeout=12)
        
        # Если ИИ ответил успешно — отдаем его ответ
        if res.status_code == 200 and len(res.text.strip()) > 20:
            return res.text.strip()
            
        # Если ИИ прислал ошибку или перегружен — включаем внутренний игровой движок
        return generate_fallback_story(*player_fallback_data, user_action)
    except Exception:
        # При любом сетевом сбое или тайм-ауте игра продолжается на локальных рельсах
        return generate_fallback_story(*player_fallback_data, user_action)
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
            bot.reply_to(message, "❌ Пожалуйста, сначала подключиться к миру командой:\n`/join мир1 Хаус`")
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

        cursor.execute('SELECT username, level, hp, location FROM players WHERE world_id = ?', (world_id,))
        players_info = "\n".join([f"- {row['username']} (Ур. {row['level']}, HP: {row['hp']}, {row['location']})" for row in cursor.fetchall()])
        
        cursor.execute('SELECT entry FROM logs WHERE world_id = ? ORDER BY id DESC LIMIT 5', (world_id,))
        world_history = "\n".join([str(l['entry']) for l in reversed(cursor.fetchall())])
        conn.close()

        system_prompt = (
            "Ты продвинутый Гейм-Мастер многопользовательской ЛитРПГ игры. Твоя задача — реагировать на действия игрока, "
            "генерировать глубокий, связный, интересный сюжет в стиле фэнтези на русском языке. Будь креативным и пиши развернутые ответы.\n\n"
            "Текущие игроки в мире:\n" + players_info + "\nИстория событий:\n" + world_history + "\n"
            "Ходит: " + p_name + " (Ур " + p_lvl + ", HP: " + p_hp + "/" + p_max_hp + ", MP: " + p_mp + "/" + p_max_mp + ", Золото: " + p_gold + ", Инв: " + p_inv + ", Лок: " + p_loc + ").\n"
            "Действие игрока: \"" + action + "\"\n\n"
            "В самом конце твоего художественного ответа обязательно добавь СТРОГО на новой строке системный блок в следующем формате:\n"
            "UPDATE_DATA: {\"level\": 1, \"hp\": 100, \"mp\": 50, \"gold\": 10, \"inventory\": \"кинжал\", \"location\": \"Деревня\"}\n"
            "Изменяй значения в JSON в зависимости от происходящего в сюжете."
        )

        # Собираем кортеж данных для локального генератора, если ИИ будет недоступен
        fallback_data = (p_name, p_loc, p_lvl, p_hp, p_mp, p_gold, p_inv)

        # Пытаемся вызвать ИИ. Если он недоступен, подставится локальный генератор
        ai_reply = ask_free_rpg_ai(system_prompt, action, fallback_data)

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
        bot.reply_to(message, f"⚠️ Ошибка обработки хода. Попробуйте еще раз.")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
