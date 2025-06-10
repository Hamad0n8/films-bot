import telebot
from telebot import types
import json
import os
import re
import time
import threading
import flask

# --- ТАНЗИМОТ ---

# Токени ботро аз тағирёбандаҳои муҳит (Environment Variables) дар Render мегирем
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    print("!!! Хатогӣ: Токени бот (BOT_TOKEN) дар тағирёбандаҳои муҳит ёфт нашуд!")
    exit()

bot = telebot.TeleBot(BOT_TOKEN)

# Номи домейни вебии шумо дар Render (масалан, your-bot-name.onrender.com)
# Онро дар тағирёбандаҳои муҳит дар Render муқаррар кунед
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")

# Роҳ барои диски доимӣ дар Render
# Мо маълумотро дар ин ҷо нигоҳ медорем, то гум нашавад
DATA_DIR = "/var/data"
SETTINGS_FILE = os.path.join(DATA_DIR, "group_settings.json")

# Агар папка вуҷуд надошта бошад, онро эҷод мекунем
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)


# Канали муқарраршуда барои истисно
ALLOWED_CHANNEL = "@VOLFHA"

# --- СИНФИ ТАНЗИМОТ (бе тағйир, вале роҳи файл иваз шуд) ---
class GroupSettings:
    def __init__(self):
        self.load_settings()
    
    def load_settings(self):
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                self.settings = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.settings = {}
    
    def save_settings(self):
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.settings, f, ensure_ascii=False, indent=2)
    
    def get_group_settings(self, group_id):
        group_id = str(group_id)
        if group_id not in self.settings:
            self.settings[group_id] = {
                'required_channels': [],
                'banned_words': [],
                'links_only_admin': True
            }
            self.save_settings()
        return self.settings[group_id]
    
    def add_required_channel(self, group_id, channel):
        group_settings = self.get_group_settings(group_id)
        if channel not in group_settings['required_channels']:
            group_settings['required_channels'].append(channel)
            self.save_settings()
            return True
        return False
    
    def remove_required_channel(self, group_id, channel):
        group_settings = self.get_group_settings(group_id)
        if channel in group_settings['required_channels']:
            group_settings['required_channels'].remove(channel)
            self.save_settings()
            return True
        return False
    
    def add_banned_word(self, group_id, word):
        group_settings = self.get_group_settings(group_id)
        if word.lower() not in group_settings['banned_words']:
            group_settings['banned_words'].append(word.lower())
            self.save_settings()
            return True
        return False
    
    def remove_banned_word(self, group_id, word):
        group_settings = self.get_group_settings(group_id)
        if word.lower() in group_settings['banned_words']:
            group_settings['banned_words'].remove(word.lower())
            self.save_settings()
            return True
        return False

settings = GroupSettings()

# --- ФУНКСИЯҲОИ ЁРИРАСОН (бе тағйирот) ---

GROUP_ANONYMOUS_BOT_ID = 1087968824

def is_admin(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    if user_id == GROUP_ANONYMOUS_BOT_ID:
        return True
    try:
        chat_member = bot.get_chat_member(chat_id, user_id)
        return chat_member.status in ['administrator', 'creator']
    except Exception as e:
        print(f"Хатогӣ ҳангоми санҷиши статуси админ: {e}")
        return False

def check_subscription(user_id, channels):
    for channel in channels:
        try:
            member = bot.get_chat_member(channel, user_id)
            if member.status in ['left', 'kicked']:
                return False, channel
        except:
            return False, channel
    return True, None

def contains_link(text):
    url_pattern = re.compile(
        r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
        r'|(?:^|[^@\w])@[a-zA-Z0-9_]{1,15}(?![a-zA-Z0-9_])'
        r'|(?:^|[^@\w])t\.me/[a-zA-Z0-9_]{1,32}'
    )
    return bool(url_pattern.search(text))

def is_from_allowed_channel(text):
    return ALLOWED_CHANNEL.lower() in text.lower()

def delete_message_after(delay, chat_id, message_id):
    def task():
        time.sleep(delay)
        try:
            bot.delete_message(chat_id, message_id)
        except:
            pass
    threading.Thread(target=task).start()

# --- ФАРМОНҲО (бе тағйирот) ---

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    if message.chat.type != 'private':
        return
    help_text = """
🤖 Боти идоракунии гурӯҳ

Фармонҳои админ:
/add_channel @channel - Илова кардани канал барои обуна
/remove_channel @channel - Хориҷ кардани канал
/list_channels - Рӯйхати каналҳо
/add_word калима - Илова кардани калимаи мамнӯъ
/remove_word калима - Хориҷ кардани калимаи мамнӯъ
/list_words - Рӯйхати калимаҳои мамнӯъ

Хусусиятҳо:
✅ Санҷиши обуна дар каналҳо
✅ Филтри калимаҳои мамнӯъ
✅ Маҳдудияти линк барои ғайриадминҳо
✅ Шинохтани админҳои беном ва паёмҳои канал
✅ Истиснои канали @VOLFHA
    """
    bot.reply_to(message, help_text)

@bot.message_handler(commands=['add_channel'])
def add_channel(message):
    if not is_admin(message):
        bot.reply_to(message, "❌ Танҳо администраторҳо ин фармонро истифода бурда метавонанд!")
        return
    try:
        channel = message.text.split()[1]
        if not channel.startswith('@'):
            channel = '@' + channel
        if settings.add_required_channel(message.chat.id, channel):
            bot.reply_to(message, f"✅ Канали {channel} илова карда шуд!")
        else:
            bot.reply_to(message, f"⚠️ Канали {channel} аллакай дар рӯйхат аст!")
    except IndexError:
        bot.reply_to(message, "❌ Истифода: /add_channel @channel_name")

@bot.message_handler(commands=['remove_channel'])
def remove_channel(message):
    if not is_admin(message):
        bot.reply_to(message, "❌ Танҳо администраторҳо ин фармонро истифода бурда метавонанд!")
        return
    try:
        channel = message.text.split()[1]
        if not channel.startswith('@'):
            channel = '@' + channel
        if settings.remove_required_channel(message.chat.id, channel):
            bot.reply_to(message, f"✅ Канали {channel} хориҷ карда шуд!")
        else:
            bot.reply_to(message, f"⚠️ Канали {channel} дар рӯйхат нест!")
    except IndexError:
        bot.reply_to(message, "❌ Истифода: /remove_channel @channel_name")

@bot.message_handler(commands=['list_channels'])
def list_channels(message):
    if not is_admin(message):
        bot.reply_to(message, "❌ Танҳо администраторҳо ин фармонро истифода бурда метавонанд!")
        return
    group_settings = settings.get_group_settings(message.chat.id)
    channels = group_settings['required_channels']
    if channels:
        channels_text = "\n".join([f"• {channel}" for channel in channels])
        bot.reply_to(message, f"📋 Каналҳои талабшуда:\n{channels_text}")
    else:
        bot.reply_to(message, "📋 Ягон канал танзим нашудааст!")

@bot.message_handler(commands=['add_word'])
def add_banned_word(message):
    if not is_admin(message):
        bot.reply_to(message, "❌ Танҳо администраторҳо ин фармонро истифода бурда метавонанд!")
        return
    try:
        word = ' '.join(message.text.split()[1:])
        if not word:
            raise IndexError
        if settings.add_banned_word(message.chat.id, word):
            bot.reply_to(message, f"✅ Калимаи '{word}' ба рӯйхати мамнӯъ илова карда шуд!")
        else:
            bot.reply_to(message, f"⚠️ Калимаи '{word}' аллакай дар рӯйхат аст!")
    except IndexError:
        bot.reply_to(message, "❌ Истифода: /add_word калимаи мамнӯъ")

@bot.message_handler(commands=['remove_word'])
def remove_banned_word(message):
    if not is_admin(message):
        bot.reply_to(message, "❌ Танҳо администраторҳо ин фармонро истифода бурда метавонанд!")
        return
    try:
        word = ' '.join(message.text.split()[1:])
        if not word:
            raise IndexError
        if settings.remove_banned_word(message.chat.id, word):
            bot.reply_to(message, f"✅ Калимаи '{word}' аз рӯйхати мамнӯъ хориҷ карда шуд!")
        else:
            bot.reply_to(message, f"⚠️ Калимаи '{word}' дар рӯйхат нест!")
    except IndexError:
        bot.reply_to(message, "❌ Истифода: /remove_word калимаи мамнӯъ")

@bot.message_handler(commands=['list_words'])
def list_banned_words(message):
    if not is_admin(message):
        bot.reply_to(message, "❌ Танҳо администраторҳо ин фармонро истифода бурда метавонанд!")
        return
    group_settings = settings.get_group_settings(message.chat.id)
    words = group_settings['banned_words']
    if words:
        words_text = "\n".join([f"• {word}" for word in words])
        bot.reply_to(message, f"🚫 Калимаҳои мамнӯъ:\n{words_text}")
    else:
        bot.reply_to(message, "🚫 Ягон калимаи мамнӯъ танзим нашудааст!")


# --- КОРКАРДИ ПАЁМҲО (бе тағйирот) ---

@bot.message_handler(content_types=['text', 'photo', 'video', 'document', 'audio', 'voice', 'sticker'])
def handle_all_messages(message):
    if message.chat.type == 'private':
        return
    if message.sender_chat:
        return
    if is_admin(message):
        return
    
    group_settings = settings.get_group_settings(message.chat.id)
    message_text = (message.text or message.caption or "").lower()
    
    required_channels = group_settings['required_channels']
    if required_channels:
        if message.from_user.id != GROUP_ANONYMOUS_BOT_ID:
            subscribed, missing_channel = check_subscription(message.from_user.id, required_channels)
            if not subscribed:
                try:
                    bot.delete_message(message.chat.id, message.message_id)
                    warning_msg = bot.send_message(
                        message.chat.id,
                        f"⚠️ @{message.from_user.username or message.from_user.first_name}, "
                        f"барои фиристодани паём бояд ба канали {missing_channel} обуна шавед!"
                    )
                    delete_message_after(10, message.chat.id, warning_msg.message_id)
                except:
                    pass
                return

    banned_words = group_settings['banned_words']
    for word in banned_words:
        if word in message_text:
            try:
                bot.delete_message(message.chat.id, message.message_id)
                warning_msg = bot.send_message(
                    message.chat.id,
                    f"⚠️ @{message.from_user.username or message.from_user.first_name}, "
                    f"истифодаи ин калима мамнӯъ аст!"
                )
                delete_message_after(5, message.chat.id, warning_msg.message_id)
            except:
                pass
            return
    
    if message.content_type == 'text' and contains_link(message.text):
        if not is_from_allowed_channel(message.text):
            try:
                bot.delete_message(message.chat.id, message.message_id)
                warning_msg = bot.send_message(
                    message.chat.id,
                    f"⚠️ @{message.from_user.username or message.from_user.first_name}, "
                    f"танҳо администраторҳо линк фиристода метавонанд!"
                )
                delete_message_after(5, message.chat.id, warning_msg.message_id)
            except:
                pass

@bot.message_handler(content_types=['new_chat_members'])
def welcome_new_members(message):
    if message.chat.type == 'private':
        return
    
    for new_member in message.new_chat_members:
        if new_member.id == bot.get_me().id:
            bot.send_message(
                message.chat.id,
                "🤖 Салом! Ман боти идоракунии гурӯҳ ҳастам.\n"
                "Администраторҳо метавонанд аз фармонҳои ман истифода баранд.\n"
                "Барои кӯмак /help-ро дар паёми хусусӣ фиристед."
            )
            continue
        
        name = new_member.first_name
        username = f"@{new_member.username}" if new_member.username else name
        welcome_text = f"🎉 Хӯш омадед, {username}!\n\n"
        group_settings = settings.get_group_settings(message.chat.id)
        required_channels = group_settings['required_channels']
        
        if required_channels:
            welcome_text += "📢 Барои иштирок дар муҳокимаҳо, лутфан ба каналҳои зерин обуна шавед:\n"
            for channel in required_channels:
                welcome_text += f"• {channel}\n"
            welcome_text += "\n"
        
        welcome_text += "📋 Қоидаҳои гурӯҳро мутолиа кунед ва онҳоро риоя намоед!"
        
        try:
            welcome_msg = bot.send_message(message.chat.id, welcome_text)
            delete_message_after(120, message.chat.id, welcome_msg.message_id)
        except:
            pass

# --- ҚИСМИ ВЕБ-СЕРВЕР (БАРОИ RENDER) ---

app = flask.Flask(__name__)

# Роҳ (route) барои қабули webhook аз Telegram
@app.route('/' + BOT_TOKEN, methods=['POST'])
def get_message():
    json_string = flask.request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return "!", 200

# Роҳи асосӣ барои санҷиш, ки сервер кор мекунад
@app.route('/')
def index():
    return "Bot is running...", 200

if __name__ == "__main__":
    if not WEBHOOK_URL:
        print("!!! Хатогӣ: WEBHOOK_URL дар тағирёбандаҳои муҳит ёфт нашуд!")
        print("Лутфан URL-и вебии худро дар Render муқаррар кунед.")
        exit()

    # Webhook-ро насб мекунем
    bot.remove_webhook()
    time.sleep(0.5)
    bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
    print(f"🤖 Webhook ба суроғаи {WEBHOOK_URL} насб карда шуд.")
    
    # Серверро оғоз мекунем
    # Render ба таври худкор портро муайян мекунад
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))    
