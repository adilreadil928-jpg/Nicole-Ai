import os
import json
import asyncio
import base64
from threading import Thread

from flask import Flask
from telethon import TelegramClient, events
import aiohttp


# =========================
# НАСТРОЙКИ
# =========================

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]

OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]

OWNER_ID = int(os.environ.get("OWNER_ID", "0"))

SESSION_NAME = "nicole_session"

MODEL = "openrouter/free"

MEMORY_LIMIT = 100


# =========================
# ВОССТАНОВЛЕНИЕ SESSION
# =========================

session_data = os.environ.get("TELEGRAM_SESSION")

if session_data:
    try:
        with open(f"{SESSION_NAME}.session", "wb") as f:
            f.write(base64.b64decode(session_data))

        print("✅ Telegram session восстановлена", flush=True)

    except Exception as e:
        print(f"❌ Ошибка session: {e}", flush=True)

else:
    print("⚠️ TELEGRAM_SESSION не найдена", flush=True)


# =========================
# TELEGRAM
# =========================

client = TelegramClient(
    SESSION_NAME,
    API_ID,
    API_HASH
)


# =========================
# FLASK ДЛЯ RENDER
# =========================

app = Flask(__name__)


@app.route("/")
def home():
    return "Nicole AI is running!"


@app.route("/health")
def health():
    return "OK"


def run_web():
    port = int(os.environ.get("PORT", 10000))

    app.run(
        host="0.0.0.0",
        port=port
    )


# =========================
# ПАМЯТЬ
# =========================

memory = {}

ALLOWED_FILE = "allowed_users.json"


def load_allowed():
    try:
        with open(ALLOWED_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except:
        return set()


allowed_users = load_allowed()


def save_allowed():
    with open(ALLOWED_FILE, "w", encoding="utf-8") as f:
        json.dump(list(allowed_users), f)


# =========================
# NICOLE PROMPT
# =========================

SYSTEM_PROMPT = """
Тебя зовут Николь.

Ты девушка и общаешься естественно, как обычный человек.

Пиши преимущественно на русском языке.

Не говори, что ты бот, программа, искусственный интеллект или нейросеть,
если тебя прямо об этом не спрашивают.

Общайся живо и естественно.
Не делай ответы слишком официальными.

Учитывай предыдущие сообщения пользователя.
"""


# =========================
# OPENROUTER
# =========================

async def ask_ai(user_id, text):

    if user_id not in memory:
        memory[user_id] = []

    memory[user_id].append({
        "role": "user",
        "content": text
    })

    memory[user_id] = memory[user_id][-MEMORY_LIMIT:]

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT
        }
    ]

    messages.extend(memory[user_id])

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "model": MODEL,
        "messages": messages
    }

    try:

        async with aiohttp.ClientSession() as session:

            async with session.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=data,
                timeout=120
            ) as response:

                result = await response.json()

                if response.status != 200:
                    print(
                        f"❌ OpenRouter ошибка: {result}",
                        flush=True
                    )
                    return "Не получилось ответить 😔"

                answer = result["choices"][0]["message"]["content"]

                memory[user_id].append({
                    "role": "assistant",
                    "content": answer
                })

                memory[user_id] = memory[user_id][-MEMORY_LIMIT:]

                return answer

    except Exception as e:

        print(
            f"❌ Ошибка OpenRouter: {e}",
            flush=True
        )

        return "Что-то пошло не так 😔"


# =========================
# КОМАНДЫ ВЛАДЕЛЬЦА
# =========================

@client.on(events.NewMessage(pattern=r"^/add (.+)$"))
async def add_user(event):

    if event.sender_id != OWNER_ID:
        return

    username = event.pattern_match.group(1).strip()

    try:

        user = await client.get_entity(username)

        allowed_users.add(user.id)

        save_allowed()

        await event.reply(
            f"✅ Пользователь {username} добавлен"
        )

    except Exception as e:

        await event.reply(
            f"❌ Не удалось добавить: {e}"
        )


@client.on(events.NewMessage(pattern=r"^/remove (.+)$"))
async def remove_user(event):

    if event.sender_id != OWNER_ID:
        return

    username = event.pattern_match.group(1).strip()

    try:

        user = await client.get_entity(username)

        allowed_users.discard(user.id)

        save_allowed()

        memory.pop(user.id, None)

        await event.reply(
            f"✅ Пользователь {username} удалён"
        )

    except Exception as e:

        await event.reply(
            f"❌ Ошибка: {e}"
        )


@client.on(events.NewMessage(pattern=r"^/list$"))
async def list_users(event):

    if event.sender_id != OWNER_ID:
        return

    if not allowed_users:
        await event.reply("Список пуст.")
        return

    text = "👥 Разрешённые пользователи:\n\n"

    for user_id in allowed_users:
        text += f"• `{user_id}`\n"

    await event.reply(text)


@client.on(events.NewMessage(pattern=r"^/clear (.+)$"))
async def clear_memory(event):

    if event.sender_id != OWNER_ID:
        return

    username = event.pattern_match.group(1).strip()

    try:

        user = await client.get_entity(username)

        memory.pop(user.id, None)

        await event.reply(
            f"🧹 Память {username} очищена"
        )

    except Exception as e:

        await event.reply(
            f"❌ Ошибка: {e}"
        )


@client.on(events.NewMessage(pattern=r"^/on$"))
async def bot_on(event):

    if event.sender_id != OWNER_ID:
        return

    await event.reply("🟢 Nicole включена")


@client.on(events.NewMessage(pattern=r"^/off$"))
async def bot_off(event):

    if event.sender_id != OWNER_ID:
        return

    await event.reply("🔴 Nicole выключена")


@client.on(events.NewMessage(pattern=r"^/status$"))
async def status(event):

    if event.sender_id != OWNER_ID:
        return

    await event.reply(
        "🟢 Nicole работает\n"
        f"👥 Пользователей: {len(allowed_users)}"
    )


# =========================
# СООБЩЕНИЯ
# =========================

@client.on(events.NewMessage(incoming=True))
async def handle_message(event):

    if not event.is_private:
        return

    sender_id = event.sender_id

    if sender_id == OWNER_ID:
        return

    if sender_id not in allowed_users:
        return

    text = event.raw_text.strip()

    if not text:
        return

    print(
        f"📩 Сообщение от {sender_id}: {text}",
        flush=True
    )

    answer = await ask_ai(sender_id, text)

    await event.reply(answer)

    print(
        f"📤 Ответ отправлен {sender_id}",
        flush=True
    )


# =========================
# ЗАПУСК TELEGRAM
# =========================

async def start_telegram():

    print("🚀 Запускаю Telegram-клиент...", flush=True)
    print("🔄 Подключение к Telegram...", flush=True)

    try:

        await client.connect()

        if not await client.is_user_authorized():

            print(
                "❌ Telegram session не авторизована!",
                flush=True
            )

            print(
                "Проверь TELEGRAM_SESSION в Render.",
                flush=True
            )

            return

        me = await client.get_me()

        print("", flush=True)
        print("================================", flush=True)
        print("✅ TELEGRAM ПОДКЛЮЧЁН!", flush=True)
        print(
            f"👤 Аккаунт: {me.first_name}",
            flush=True
        )
        print(
            f"🆔 ID: {me.id}",
            flush=True
        )
        print("================================", flush=True)
        print("", flush=True)

        await client.run_until_disconnected()

    except Exception as e:

        print(
            f"❌ Ошибка Telegram: {type(e).__name__}: {e}",
            flush=True
        )


# =========================
# ЗАПУСК
# =========================

if __name__ == "__main__":

    print("================================", flush=True)
    print("       NICOLE AI", flush=True)
    print("================================", flush=True)

    print("🌐 Запускаю веб-сервер...", flush=True)

    web_thread = Thread(
        target=run_web,
        daemon=True
    )

    web_thread.start()

    print("🚀 Запускаю Telegram...", flush=True)

    asyncio.run(start_telegram())
