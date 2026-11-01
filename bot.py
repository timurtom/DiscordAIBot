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

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name} (ID: {bot.user.id}) через OpenRouter 🚀")

@bot.event
async def on_message(message):
    # Игнорируем сообщения от самого бота
    if message.author == bot.user:
        return

    # Проверяем пинг бота
    if bot.user in message.mentions:
        # Очищаем пинг из текста
        prompt = message.content.replace(f"<@{bot.user.id}>", "").replace(f"<@!{bot.user.id}>", "").strip()
        
        if not prompt:
            await message.reply("вась")
            return

        async with message.channel.typing():
            try:
                # Запрос через OpenRouter (формат OpenAI API)
                response = ai_client.chat.completions.create(
                    model=OPENROUTER_MODEL,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt}
                    ]
                )
                
                reply_text = response.choices[0].message.content

                # Делим длинные ответы (лимит Discord — 2000 символов)
                if len(reply_text) > 2000:
                    for i in range(0, len(reply_text), 2000):
                        await message.channel.send(reply_text[i:i+2000])
                else:
                    await message.reply(reply_text)

            except Exception as e:
                print(f"Error communicating with OpenRouter: {e}")
                await message.reply("чет сломалось 😭")

    await bot.process_commands(message)

bot.run(DISCORD_TOKEN)