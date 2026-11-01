import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from openai import OpenAI

# Загружаем переменные из .env
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-chat")

# Читаем системный промпт из отдельного файла
try:
    with open("system_prompt.txt", "r", encoding="utf-8") as f:
        SYSTEM_PROMPT = f.read().strip()
except FileNotFoundError:
    SYSTEM_PROMPT = "Ты помощник."

# Инициализируем клиент OpenAI через OpenRouter
ai_client = OpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url="https://openrouter.ai/api/v1"
)

# Настройка интентов Discord
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

async def build_conversation_history(message, system_prompt):
    """Рекурсивно собирает цепочку реплаев, чтобы ИИ видел контекст диалога"""
    messages = [{"role": "system", "content": system_prompt}]
    thread_messages = []
    
    current_msg = message
    # Собираем историю по цепочке ответов (ограничим до 10 сообщений в глубину, чтобы не раздувать токен)
    depth = 0
    while current_msg and depth < 10:
        role = "assistant" if current_msg.author == bot.user else "user"
        
        # Очищаем пинг бота из текста сообщения, если он там есть
        content = current_msg.content.replace(f"<@{bot.user.id}>", "").replace(f"<@!{bot.user.id}>", "").strip()
        if content:
            thread_messages.append({"role": role, "content": content})
            
        # Проверяем, есть ли реплай на предыдущее сообщение
        if current_msg.reference and current_msg.reference.message_id:
            try:
                current_msg = await current_msg.channel.fetch_message(current_msg.reference.message_id)
            except discord.NotFound:
                break
        else:
            break
        depth += 1

    # Разворачиваем список, чтобы хронология шла от старых к новым
    thread_messages.reverse()
    messages.extend(thread_messages)
    return messages

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name} (ID: {bot.user.id})")

@bot.event
async def on_message(message):
    # Игнорируем сообщения от самого бота
    if message.author == bot.user:
        return

    is_mentioned = bot.user in message.mentions
    is_reply_to_bot = False

    # Проверяем, является ли сообщение ответом (реплаем) на сообщение именно нашего бота
    if message.reference and message.reference.message_id:
        try:
            replied_msg = await message.channel.fetch_message(message.reference.message_id)
            if replied_msg.author == bot.user:
                is_reply_to_bot = True
        except discord.NotFound:
            pass

    # Триггеримся, если есть пинг ИЛИ реплай на бота
    if is_mentioned or is_reply_to_bot:
        async with message.channel.typing():
            try:
                # Собираем всю цепочку диалога в массив сообщений
                messages_payload = await build_conversation_history(message, SYSTEM_PROMPT)

                # Если по какой-то причине сообщений нет (пустой пинг)
                if len(messages_payload) <= 1:
                    await message.reply("вась")
                    return

                # Запрос к OpenRouter с учетом истории
                response = ai_client.chat.completions.create(
                    model=OPENROUTER_MODEL,
                    messages=messages_payload
                )
                
                reply_text = response.choices[0].message.content

                # Делим длинные ответы под лимит Дискорда в 2000 символов
                if len(reply_text) > 2000:
                    for i in range(0, len(reply_text), 2000):
                        await message.channel.send(reply_text[i:i+2000])
                else:
                    await message.reply(reply_text)

            except Exception as e:
                print(f"Error communicating with OpenRouter: {e}")
                await message.reply("чето наебнулось")

    await bot.process_commands(message)

bot.run(DISCORD_TOKEN)