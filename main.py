import os
import json
import asyncio
import aiohttp

from telethon import TelegramClient, events

# =========================
# НАСТРОЙКИ
# =========================

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]

MODEL = "openrouter/free"

MEMORY_LIMIT = 100

ALLOWED_FILE = "allowed_users.json"

# =========================
# ДАННЫЕ
# =========================

if os.path.exists(ALLOWED_FILE):
    with open(ALLOWED_FILE, "r", encoding="utf-8") as f:
        allowed_users = set(json.load(f))
else:
    allowed_users = set()

memory = {}

ai_enabled = True


# =========================
# СОХРАНЕНИЕ СПИСКА
# =========================

def save_allowed():
    with open(ALLOWED_FILE, "w", encoding="utf-8") as f:
        json.dump(list(allowed_users), f)


# =========================
# ИИ НИКОЛЬ
# =========================

async def ask_nicole(user_id, text):

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
            "content": (
                "Тебя зовут Николь. "
                "Ты девушка и общаешься естественно, дружелюбно и живо. "
                "Не говори, что ты бот или программа, если тебя прямо не спрашивают. "
                "Отвечай на русском языке, если собеседник пишет на русском. "
                "Учитывай контекст предыдущей переписки. "
                "Не пиши слишком длинные ответы без необходимости."
            )
        }
    ]

    messages.extend(memory[user_id])

    try:
        async with aiohttp.ClientSession() as session:

            async with session.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": MODEL,
                    "messages": messages
                },
                timeout=120
            ) as response:

                data = await response.json()

                if response.status != 200:
                    print("OpenRouter error:", data)
                    return None

                answer = data["choices"][0]["message"]["content"]

                memory[user_id].append({
                    "role": "assistant",
                    "content": answer
                })

                memory[user_id] = memory[user_id][-MEMORY_LIMIT:]

                return answer

    except Exception as e:
        print("AI error:", e)
        return None


# =========================
# TELEGRAM
# =========================

client = TelegramClient(
    "nicole_session",
    API_ID,
    API_HASH
)


# =========================
# КОМАНДЫ В ИЗБРАННОМ
# =========================

@client.on(events.NewMessage(incoming=True))
async def commands(event):

    global ai_enabled

    me = await client.get_me()

    if event.sender_id != me.id:
        return

    text = event.raw_text.strip()

    if text.startswith("/add "):

        username = text[5:].strip().replace("@", "")

        try:
            user = await client.get_entity(username)

            allowed_users.add(user.id)
            save_allowed()

            await event.respond(
                f"✅ {username} добавлен. Николь теперь может ему отвечать."
            )

        except Exception as e:
            await event.respond(
                f"❌ Не удалось найти пользователя: {e}"
            )

    elif text == "/list":

        if not allowed_users:
            await event.respond("Список разрешённых пользователей пуст.")

        else:
            result = []

            for user_id in allowed_users:
                try:
                    user = await client.get_entity(user_id)
                    name = getattr(user, "username", None)

                    if name:
                        result.append("@" + name)
                    else:
                        result.append(str(user_id))

                except:
                    result.append(str(user_id))

            await event.respond(
                "👥 Разрешённые пользователи:\n\n"
                + "\n".join(result)
            )

    elif text.startswith("/remove "):

        username = text[8:].strip().replace("@", "")

        try:
            user = await client.get_entity(username)

            allowed_users.discard(user.id)
            save_allowed()

            await event.respond(
                f"❌ {username} удалён."
            )

        except:
            await event.respond("❌ Пользователь не найден.")

    elif text == "/on":

        ai_enabled = True
        await event.respond("🟢 Николь включена.")

    elif text == "/off":

        ai_enabled = False
        await event.respond("🔴 Николь выключена.")

    elif text == "/status":

        await event.respond(
            f"🤖 Николь: {'🟢 включена' if ai_enabled else '🔴 выключена'}\n"
            f"👥 Разрешённых пользователей: {len(allowed_users)}\n"
            f"🧠 Память: {MEMORY_LIMIT} сообщений"
        )

    elif text.startswith("/clear "):

        username = text[7:].strip().replace("@", "")

        try:
            user = await client.get_entity(username)

            memory.pop(user.id, None)

            await event.respond(
                f"🧹 Память переписки с @{username} очищена."
            )

        except:
            await event.respond("❌ Пользователь не найден.")


# =========================
# АВТООТВЕТ
# =========================

@client.on(events.NewMessage(incoming=True))
async def ai_handler(event):

    global ai_enabled

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

    print(f"Сообщение от {sender_id}: {text}")

    answer = await ask_nicole(sender_id, text)

    if answer:
        await event.respond(answer)


# =========================
# ЗАПУСК
# =========================

async def main():

    print("Николь запускается...")

    await client.start()

    me = await client.get_me()

    print(
        f"✅ Николь запущена как: "
        f"@{me.username if me.username else me.first_name}"
    )

    print("Ожидание сообщений...")

    await client.run_until_disconnected()


asyncio.run(main())
