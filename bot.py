import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from google import genai
from google.genai import types

# Загружаем переменные из .env
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Инициализируем клиент Gemini
ai_client = genai.Client(api_key=GEMINI_API_KEY)

# Настройка интентов Discord
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name} (ID: {bot.user.id}) 🚀")

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
                # Передаем системное правило через config
                response = ai_client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=(
                            "Ты дискорд-бот. Твоё главное и нерушимое правило: "
                            "НИКОГДА И НИ ПРИ КАКИХ ОБСТОЯТЕЛЬСТВАХ НЕ ПИШИ КОД. "
                            "Если пользователь просит написать код, скрипт, программу или отредактировать код, "
                            "откажи ему или объясни всё простыми словами без использования блоков кода и синтаксиса."
                        )
                    )
                )
                
                reply_text = response.text

                # Делим длинные ответы (лимит Discord — 2000 символов)
                if len(reply_text) > 2000:
                    for i in range(0, len(reply_text), 2000):
                        await message.channel.send(reply_text[i:i+2000])
                else:
                    await message.reply(reply_text)

            except Exception as e:
                print(f"Error communicating with Gemini: {e}")
                await message.reply("damn, something broke trying to reach the AI 😭")

    await bot.process_commands(message)

bot.run(DISCORD_TOKEN)