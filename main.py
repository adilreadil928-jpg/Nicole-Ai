import os
import json
import base64
import asyncio
import threading
import aiohttp

from flask import Flask
from telethon import TelegramClient, events


# =========================
# НАСТРОЙКИ
# =========================

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
TELEGRAM_SESSION = os.environ["TELEGRAM_SESSION"]

MODEL = "openrouter/free"
MEMORY_LIMIT = 100
ALLOWED_FILE = "allowed_users.json"


# =========================
# SOCKS5 ПРОКСИ
# =========================

PROXY_HOST = "107.150.41.226"
PROXY_PORT = 18080


# =========================
# WEB SERVER ДЛЯ RENDER
# =========================

app = Flask(__name__)


@app.route("/")
def home():
    return "Nicole is running", 200


@app.route("/health")
def health():
    return "OK", 200


def run_web_server():
    port = int(os.environ.get("PORT", 10000))

    app.run(
        host="0.0.0.0",
        port=port,
        use_reloader=False
    )


# =========================
# ВОССТАНОВЛЕНИЕ SESSION
# =========================

try:
    session_data = base64.b64decode(
        TELEGRAM_SESSION
    )

    with open(
        "nicole_session.session",
        "wb"
    ) as f:
        f.write(session_data)

    print("✅ Telegram session восстановлена")

except Exception as e:
    print(
        "❌ Ошибка восстановления session:",
        repr(e)
    )
    raise


# =========================
# РАЗРЕШЁННЫЕ ПОЛЬЗОВАТЕЛИ
# =========================

if os.path.exists(ALLOWED_FILE):

    try:
        with open(
            ALLOWED_FILE,
            "r",
            encoding="utf-8"
        ) as f:
            allowed_users = set(json.load(f))

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
            f
        )


# =========================
# ПАМЯТЬ
# =========================

memory = {}
ai_enabled = True


# =========================
# OPENROUTER
# =========================

async def ask_nicole(user_id, text):

    if user_id not in memory:
        memory[user_id] = []

    memory[user_id].append({
        "role": "user",
        "content": text
    })

    memory[user_id] = memory[user_id][
        -MEMORY_LIMIT:
    ]

    messages = [
        {
            "role": "system",
            "content": """
Тебя зовут Николь.

Ты девушка.

Общайся естественно, живо и по-человечески.

Не говори, что ты бот или программа,
в случае чего начинай жаловаться по принципу
"почему я не человек?"

Отвечай преимущественно на русском языке.

Учитывай предыдущую переписку и контекст разговора.

Не повторяй без необходимости уже сказанное.

Не пиши слишком длинные ответы,
если ситуация этого не требует.

Если собеседник шутит — можешь шутить в ответ.

Если собеседник пишет коротко —
отвечай естественно.
"""
        }
    ]

    messages.extend(memory[user_id])

    try:

        timeout = aiohttp.ClientTimeout(
            total=120
        )

        async with aiohttp.ClientSession(
            timeout=timeout
        ) as session:

            async with session.post(
                "https://openrouter.ai/api/v1/chat/completions",

                headers={
                    "Authorization":
                        f"Bearer {OPENROUTER_API_KEY}",

                    "Content-Type":
                        "application/json"
                },

                json={
                    "model": MODEL,
                    "messages": messages
                }

            ) as response:

                data = await response.json()

                if response.status != 200:

                    print("❌ OpenRouter error:")
                    print(data)

                    return None

                answer = data[
                    "choices"
                ][0]["message"]["content"]

                memory[user_id].append({
                    "role": "assistant",
                    "content": answer
                })

                memory[user_id] = memory[user_id][
                    -MEMORY_LIMIT:
                ]

                return answer

    except Exception as e:

        print(
            "❌ Ошибка ИИ:",
            repr(e)
        )

        return None


# =========================
# TELEGRAM CLIENT
# =========================

print(
    f"🌐 SOCKS5: {PROXY_HOST}:{PROXY_PORT}"
)

client = TelegramClient(
    "nicole_session",
    API_ID,
    API_HASH,

    proxy={
        "proxy_type": "socks5",
        "addr": PROXY_HOST,
        "port": PROXY_PORT,
        "rdns": True
    },

    connection_retries=10,
    retry_delay=5,
    timeout=30
)


# =========================
# КОМАНДЫ
# =========================

@client.on(events.NewMessage(incoming=True))
async def commands(event):

    global ai_enabled

    me = await client.get_me()

    if event.sender_id != me.id:
        return

    text = event.raw_text.strip()


    if text.startswith("/add "):

        username = (
            text[5:]
            .strip()
            .replace("@", "")
        )

        try:

            user = await client.get_entity(
                username
            )

            allowed_users.add(user.id)

            save_allowed()

            await event.respond(
                f"✅ @{username} добавлен.\n"
                f"Теперь Николь может отвечать этому человеку."
            )

        except Exception as e:

            await event.respond(
                "❌ Не удалось найти пользователя.\n\n"
                f"{e}"
            )


    elif text.startswith("/remove "):

        username = (
            text[8:]
            .strip()
            .replace("@", "")
        )

        try:

            user = await client.get_entity(
                username
            )

            allowed_users.discard(user.id)

            save_allowed()

            memory.pop(user.id, None)

            await event.respond(
                f"❌ @{username} удалён."
            )

        except Exception:

            await event.respond(
                "❌ Пользователь не найден."
            )


    elif text == "/list":

        if not allowed_users:

            await event.respond(
                "👥 Список разрешённых пользователей пуст."
            )

            return

        result = []

        for user_id in allowed_users:

            try:

                user = await client.get_entity(
                    user_id
                )

                username = getattr(
                    user,
                    "username",
                    None
                )

                if username:
                    result.append(
                        "@" + username
                    )
                else:
                    result.append(
                        str(user_id)
                    )

            except Exception:

                result.append(
                    str(user_id)
                )

        await event.respond(
            "👥 Разрешённые пользователи:\n\n"
            + "\n".join(result)
        )


    elif text.startswith("/clear "):

        username = (
            text[7:]
            .strip()
            .replace("@", "")
        )

        try:

            user = await client.get_entity(
                username
            )

            memory.pop(
                user.id,
                None
            )

            await event.respond(
                f"🧹 Память переписки с @{username} очищена."
            )

        except Exception:

            await event.respond(
                "❌ Пользователь не найден."
            )


    elif text == "/on":

        ai_enabled = True

        await event.respond(
            "🟢 Николь включена."
        )


    elif text == "/off":

        ai_enabled = False

        await event.respond(
            "🔴 Николь выключена."
        )


    elif text == "/status":

        await event.respond(
            f"🤖 Николь: "
            f"{'🟢 включена' if ai_enabled else '🔴 выключена'}\n"
            f"👥 Разрешённых пользователей: "
            f"{len(allowed_users)}\n"
            f"🧠 Память: {MEMORY_LIMIT} сообщений\n"
            f"🌐 SOCKS5: "
            f"{PROXY_HOST}:{PROXY_PORT}"
        )


# =========================
# AI HANDLER
# =========================

@client.on(events.NewMessage(incoming=True))
async def ai_handler(event):

    if not ai_enabled:
        return

    if not event.is_private:
        return

    sender_id = event.sender_id

    me = await client.get_me()

    if sender_id == me.id:
        return

    if sender_id not in allowed_users:
        return

    text = event.raw_text.strip()

    if not text:
        return

    print(
        f"📩 Сообщение от {sender_id}: {text}"
    )

    answer = await ask_nicole(
        sender_id,
        text
    )

    if answer:

        await event.respond(answer)

        print(
            f"📤 Николь: {answer}"
        )


# =========================
# MAIN
# =========================

async def main():

    print("================================")
    print("          NICOLE AI")
    print("================================")

    print("Запуск Telegram...")
    print("🔄 Подключение к Telegram через SOCKS5...")
    
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
                "❌ Telegram session НЕ авторизована."
            )

            print(
                "❌ Нужно создать новую Telegram session."
            )

            return

        me = await client.get_me()

        print(
            "👤 Telegram аккаунт получен"
        )

    except asyncio.TimeoutError:

        print(
            "❌ SOCKS5-прокси не ответил за 30 секунд."
        )

        print(
            "❌ Попробуй другой SOCKS5."
        )

        raise

    except Exception as e:

        print(
            "❌ Ошибка Telegram:",
            repr(e)
        )

        raise


    username = (
        "@" + me.username
        if me.username
        else me.first_name
    )

    print(
        f"✅ Николь работает от аккаунта: {username}"
    )

    print(
        f"🧠 Память: {MEMORY_LIMIT} сообщений"
    )

    print(
        f"👥 Разрешённых пользователей: "
        f"{len(allowed_users)}"
    )

    print("🟢 Николь готова.")

    await client.run_until_disconnected()


# =========================
# START
# =========================

if __name__ == "__main__":

    print(
        "🌐 Запускаю веб-сервер..."
    )

    web_thread = threading.Thread(
        target=run_web_server,
        daemon=True
    )

    web_thread.start()

    print(
        "🚀 Запускаю Telegram-клиент..."
    )

    asyncio.run(main())
