import os
import json
import asyncio
import base64
import socket
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

# SOCKS5
PROXY_HOST = "185.87.255.54"
PROXY_PORT = 1080

SESSION_FILE = "nicole_session.session"
ALLOWED_FILE = "allowed_users.json"

OWNER_ID = int(os.environ.get("OWNER_ID", "0"))

MODEL = "openrouter/free"
MAX_MEMORY = 100


# =========================
# FLASK ДЛЯ RENDER
# =========================

app = Flask(__name__)


@app.route("/")
def home():
    return "NICOLE AI is running"


@app.route("/health")
def health():
    return "OK"


def run_web():
    port = int(os.environ.get("PORT", 10000))

    app.run(
        host="0.0.0.0",
        port=port,
        use_reloader=False
    )


# =========================
# ВОССТАНОВЛЕНИЕ SESSION
# =========================

if not os.path.exists(SESSION_FILE):

    session_b64 = os.environ.get(
        "TELEGRAM_SESSION",
        ""
    ).strip()

    if session_b64:

        try:

            session_data = base64.b64decode(
                session_b64
            )

            with open(
                SESSION_FILE,
                "wb"
            ) as f:

                f.write(session_data)

            print(
                "✅ Telegram session восстановлена"
            )

        except Exception as e:

            print(
                f"❌ Ошибка восстановления session: {e}"
            )

    else:

        print(
            "⚠️ TELEGRAM_SESSION не найден"
        )

else:

    print(
        "✅ Telegram session уже существует"
    )


# =========================
# ALLOWED USERS
# =========================

if os.path.exists(ALLOWED_FILE):

    try:

        with open(
            ALLOWED_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            allowed_users = set(
                json.load(f)
            )

    except Exception:

        allowed_users = set()

else:

    allowed_users = set()


def save_allowed():

    with open(
        ALLOWED_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            list(allowed_users),
            f,
            ensure_ascii=False,
            indent=2
        )


# =========================
# ПАМЯТЬ
# =========================

memory = {}


# =========================
# SYSTEM PROMPT
# =========================

SYSTEM_PROMPT = """
Тебя зовут Николь.

Ты девушка и общаешься естественно, как обычный человек.
Пиши преимущественно на русском языке.

Не говори, что ты бот, программа, искусственный интеллект,
нейросеть или языковая модель.

Отвечай живо и естественно.
Не используй слишком официальный стиль.

Если собеседник пишет коротко — отвечай тоже относительно коротко.
Если разговор серьёзный — отвечай серьёзно.
"""


# =========================
# TELEGRAM CLIENT
# =========================

client = TelegramClient(
    SESSION_FILE,
    API_ID,
    API_HASH,

    proxy={
        "proxy_type": "socks5",
        "addr": PROXY_HOST,
        "port": PROXY_PORT,
        "rdns": True
    },

    connection_retries=3,
    retry_delay=3,
    timeout=15
)


# =========================
# ДИАГНОСТИКА SOCKS5
# =========================

def check_proxy_tcp():

    print()
    print("=" * 50)
    print(
        f"🔎 Проверяю SOCKS5: "
        f"{PROXY_HOST}:{PROXY_PORT}"
    )
    print("=" * 50)

    try:

        print(
            "🔌 Пытаюсь открыть TCP-соединение..."
        )

        sock = socket.create_connection(
            (
                PROXY_HOST,
                PROXY_PORT
            ),
            timeout=10
        )

        print(
            "✅ TCP-порт SOCKS5 доступен из Render"
        )

        print(
            f"📡 Удалённый адрес: "
            f"{PROXY_HOST}:{PROXY_PORT}"
        )

        sock.close()

        print(
            "🔌 TCP-соединение закрыто"
        )

        return True

    except socket.timeout:

        print(
            "❌ TCP-проверка: TIMEOUT"
        )

        print(
            "⚠️ Render не получил ответ "
            "от SOCKS5 за 10 секунд"
        )

        return False

    except ConnectionRefusedError:

        print(
            "❌ TCP-проверка: CONNECTION REFUSED"
        )

        print(
            "⚠️ Сервер отклонил подключение "
            "к SOCKS5"
        )

        return False

    except OSError as e:

        print(
            f"❌ TCP-проверка: OS ERROR: {e}"
        )

        return False

    except Exception as e:

        print(
            f"❌ TCP-проверка: ERROR: {e}"
        )

        return False


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

    memory[user_id] = (
        memory[user_id][-MAX_MEMORY:]
    )

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT
        }
    ]

    messages.extend(
        memory[user_id]
    )

    headers = {
        "Authorization":
            f"Bearer {OPENROUTER_API_KEY}",

        "Content-Type":
            "application/json"
    }

    data = {
        "model": MODEL,
        "messages": messages
    }

    try:

        timeout = aiohttp.ClientTimeout(
            total=120
        )

        async with aiohttp.ClientSession(
            timeout=timeout
        ) as session:

            async with session.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=data
            ) as response:

                result = await response.json()

                if response.status != 200:

                    print(
                        f"❌ OpenRouter: {result}"
                    )

                    return (
                        "Извини, у меня сейчас "
                        "что-то не работает."
                    )

                answer = (
                    result["choices"][0]
                    ["message"]["content"]
                )

                memory[user_id].append({
                    "role": "assistant",
                    "content": answer
                })

                memory[user_id] = (
                    memory[user_id][-MAX_MEMORY:]
                )

                return answer

    except Exception as e:

        print(
            f"❌ Ошибка OpenRouter: {e}"
        )

        return (
            "Что-то пошло не так, "
            "попробуй ещё раз."
        )


# =========================
# TELEGRAM COMMANDS
# =========================

@client.on(events.NewMessage(
    pattern=r"^/add (.+)$"
))
async def add_user(event):

    if event.sender_id != OWNER_ID:
        return

    username = (
        event.pattern_match
        .group(1)
        .strip()
    )

    try:

        user = await client.get_entity(
            username
        )

        allowed_users.add(
            user.id
        )

        save_allowed()

        await event.reply(
            f"✅ Пользователь добавлен: "
            f"{user.first_name or ''} "
            f"(ID: {user.id})"
        )

    except Exception as e:

        await event.reply(
            f"❌ Не удалось добавить пользователя:\n{e}"
        )


@client.on(events.NewMessage(
    pattern=r"^/remove (.+)$"
))
async def remove_user(event):

    if event.sender_id != OWNER_ID:
        return

    username = (
        event.pattern_match
        .group(1)
        .strip()
    )

    try:

        user = await client.get_entity(
            username
        )

        if user.id in allowed_users:

            allowed_users.remove(
                user.id
            )

            save_allowed()

            await event.reply(
                "✅ Пользователь удалён."
            )

        else:

            await event.reply(
                "⚠️ Пользователя нет в списке."
            )

    except Exception as e:

        await event.reply(
            f"❌ Ошибка:\n{e}"
        )


@client.on(events.NewMessage(
    pattern=r"^/list$"
))
async def list_users(event):

    if event.sender_id != OWNER_ID:
        return

    if not allowed_users:

        await event.reply(
            "📭 Список пуст."
        )

        return

    text = (
        "👥 Разрешённые пользователи:\n\n"
    )

    for user_id in allowed_users:

        try:

            user = await client.get_entity(
                user_id
            )

            name = (
                user.first_name
                or "Без имени"
            )

            username = (
                f"@{user.username}"
                if user.username
                else "без username"
            )

            text += (
                f"• {name} — "
                f"{username} — "
                f"`{user_id}`\n"
            )

        except:

            text += (
                f"• `{user_id}`\n"
            )

    await event.reply(text)


@client.on(events.NewMessage(
    pattern=r"^/clear (.+)$"
))
async def clear_memory(event):

    if event.sender_id != OWNER_ID:
        return

    username = (
        event.pattern_match
        .group(1)
        .strip()
    )

    try:

        user = await client.get_entity(
            username
        )

        memory.pop(
            user.id,
            None
        )

        await event.reply(
            f"🧹 Память пользователя "
            f"{username} очищена."
        )

    except Exception as e:

        await event.reply(
            f"❌ Ошибка:\n{e}"
        )


@client.on(events.NewMessage(
    pattern=r"^/on$"
))
async def bot_on(event):

    if event.sender_id != OWNER_ID:
        return

    await event.reply(
        "🟢 Николь включена."
    )


@client.on(events.NewMessage(
    pattern=r"^/off$"
))
async def bot_off(event):

    if event.sender_id != OWNER_ID:
        return

    await event.reply(
        "🔴 Николь выключена."
    )


@client.on(events.NewMessage(
    pattern=r"^/status$"
))
async def status(event):

    if event.sender_id != OWNER_ID:
        return

    await event.reply(
        "🟢 Nicole AI работает\n"
        f"👥 Пользователей: "
        f"{len(allowed_users)}\n"
        f"🌐 SOCKS5: "
        f"{PROXY_HOST}:{PROXY_PORT}"
    )


# =========================
# СООБЩЕНИЯ ПОЛЬЗОВАТЕЛЕЙ
# =========================

@client.on(events.NewMessage(
    incoming=True
))
async def message_handler(event):

    if not event.is_private:
        return

    sender_id = event.sender_id

    if event.raw_text.startswith("/"):
        return

    if sender_id not in allowed_users:
        return

    text = event.raw_text.strip()

    if not text:
        return

    print(
        f"📩 Сообщение от "
        f"{sender_id}: {text}"
    )

    try:

        answer = await ask_ai(
            sender_id,
            text
        )

        await event.reply(
            answer
        )

        print(
            f"📤 Ответ пользователю "
            f"{sender_id}: {answer}"
        )

    except Exception as e:

        print(
            f"❌ Ошибка обработки "
            f"сообщения: {e}"
        )


# =========================
# ЗАПУСК TELEGRAM
# =========================

async def start_telegram():

    print()
    print("🚀 Запускаю Telegram-клиент...")
    print("NICOLE AI")
    print("Запуск Telegram...")

    print(
        f"🌐 SOCKS5: "
        f"{PROXY_HOST}:{PROXY_PORT}"
    )

    # ---------------------------------
    # TCP DIAGNOSTIC
    # ---------------------------------

    proxy_ok = await asyncio.to_thread(
        check_proxy_tcp
    )

    print()

    if not proxy_ok:

        print(
            "🛑 SOCKS5 не прошёл TCP-проверку."
        )

        print(
            "🛑 Telegram-клиент запускать "
            "не буду."
        )

        print(
            "💡 Попробуй другой IP:PORT."
        )

        return

    print(
        "✅ TCP-проверка пройдена."
    )

    print(
        "🔄 Подключение к Telegram "
        "через SOCKS5..."
    )

    # ---------------------------------
    # TELEGRAM
    # ---------------------------------

    try:

        await asyncio.wait_for(
            client.connect(),
            timeout=30
        )

        print(
            "🔗 Соединение с Telegram установлено"
        )

        authorized = (
            await client.is_user_authorized()
        )

        print(
            f"🔐 Авторизация: {authorized}"
        )

        if not authorized:

            print(
                "❌ Session не авторизована."
            )

            return

        me = await client.get_me()

        print(
            f"👤 Telegram аккаунт получен: "
            f"{me.first_name or ''} "
            f"{('@' + me.username) if me.username else ''}"
        )

        print()
        print("🟢 Николь готова.")
        print()

        await client.run_until_disconnected()

    except asyncio.TimeoutError:

        print()
        print(
            "❌ Telegram: TIMEOUT "
            "после 30 секунд."
        )

        print(
            "⚠️ TCP-порт был доступен, "
            "но SOCKS5/Telegram-соединение "
            "не завершилось."
        )

    except ConnectionError as e:

        print()
        print(
            f"❌ Telegram ConnectionError: {e}"
        )

    except Exception as e:

        print()
        print(
            f"❌ Ошибка подключения Telegram: {e}"
        )


# =========================
# MAIN
# =========================

if __name__ == "__main__":

    print("🚀 Запуск Nicole AI...")

    web_thread = Thread(
        target=run_web,
        daemon=True
    )

    web_thread.start()

    print(
        "🌐 Запускаю веб-сервер..."
    )

    asyncio.run(
        start_telegram()
    )
