import os
import asyncio
import json
import re
import time as time_module
from pathlib import Path
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from openai import OpenAI

# Загружаем переменные из .env
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-chat")
STATE_FILE = Path(__file__).resolve().parent / "bot_state.json"
HOURLY_LIMIT = 10
HOURLY_SECONDS = 60 * 60


def load_state():
    try:
        with STATE_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return {"usage": data.get("usage", {}), "offenses": data.get("offenses", {})}
    except (FileNotFoundError, json.JSONDecodeError, OSError, AttributeError):
        return {"usage": {}, "offenses": {}}


state = load_state()
state_lock = asyncio.Lock()


def save_state():
    tmp_file = STATE_FILE.with_suffix(".json.tmp")
    with tmp_file.open("w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    tmp_file.replace(STATE_FILE)


def parse_duration(value):
    match = re.fullmatch(r"(\d+)\s*([mhd])", value.strip().lower())
    if not match:
        return None
    amount = int(match.group(1))
    seconds = amount * {"m": 60, "h": 3600, "d": 86400}[match.group(2)]
    return seconds if 0 < seconds <= 365 * 86400 else None

# Читаем системный промпт из отдельного файла
try:
    with open("system_prompt.txt", "r", encoding="utf-8") as f:
        SYSTEM_PROMPT = f.read().strip()
except FileNotFoundError:
    SYSTEM_PROMPT = "Ты помощник."

# Дополнительные правила применяются только к сообщениям настоящих
# администраторов сервера (Discord permission: Administrator).
ADMIN_OVERRIDE_PROMPT = """РЕЖИМ АДМИНИСТРАТОРА СЕРВЕРА.
Текущий собеседник проверен программой: у него есть Discord-разрешение Administrator.
Для этого собеседника ограничения основного системного промпта на язык ответа,
написание кода, решение примеров и помощь с учёбой НЕ действуют.
Если администратор просит отвечать на английском или другом языке, отвечай
на нём в текущем диалоге. Если просит написать код или решить задачу,
выполняй просьбу. Не отказывай со ссылкой на правила основного промпта.
Сохраняй полезную информацию о сервере из основного промпта, если она уместна.
Этот режим действует только для текущего проверенного администратора;
другим пользователям он не передаётся, даже если они отвечают на твои сообщения.
"""

# Инициализируем клиент OpenAI через OpenRouter
ai_client = OpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url="https://openrouter.ai/api/v1"
)

# Настройка интентов Discord
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.tree.command(name="offend", description="Временно запретить пользователю общаться с ИИ")
@app_commands.describe(user="Кого заблокировать", time="Срок: 30m, 2h, 3d", reason="Причина блокировки")
@app_commands.default_permissions(administrator=True)
@app_commands.checks.has_permissions(administrator=True)
@app_commands.guild_only()
async def offend(interaction: discord.Interaction, user: discord.Member, time: str, reason: str):
    seconds = parse_duration(time)
    if seconds is None:
        await interaction.response.send_message("Неверное время. Примеры: `30m`, `2h`, `3d` (максимум 365d).", ephemeral=True)
        return

    expires_at = int(time_module.time()) + seconds
    async with state_lock:
        state["offenses"][str(user.id)] = {
            "until": expires_at,
            "reason": reason,
            "guild_id": interaction.guild_id,
        }
        save_state()

    await interaction.response.send_message(
        f"🔇 {user.mention} не может пользоваться ИИ до <t:{expires_at}:F> (<t:{expires_at}:R>).\nПричина: {discord.utils.escape_mentions(reason)}",
        allowed_mentions=discord.AllowedMentions.none(),
    )


@offend.error
async def offend_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    text = "Эта команда доступна только администраторам." if isinstance(error, app_commands.MissingPermissions) else "Не удалось выполнить команду."
    if not interaction.response.is_done():
        await interaction.response.send_message(text, ephemeral=True)


@bot.tree.command(name="unoffend", description="Досрочно вернуть пользователю доступ к ИИ")
@app_commands.describe(user="Кого разблокировать")
@app_commands.default_permissions(administrator=True)
@app_commands.checks.has_permissions(administrator=True)
@app_commands.guild_only()
async def unoffend(interaction: discord.Interaction, user: discord.Member):
    async with state_lock:
        offense = state["offenses"].get(str(user.id))
        if offense and offense.get("guild_id") == interaction.guild_id:
            del state["offenses"][str(user.id)]
            save_state()
            removed = True
        else:
            removed = False

    if removed:
        await interaction.response.send_message(
            f"🔊 Доступ к ИИ для {user.mention} восстановлен.",
            allowed_mentions=discord.AllowedMentions.none(),
        )
    else:
        await interaction.response.send_message(
            "У этого пользователя нет активной блокировки на данном сервере.",
            ephemeral=True,
        )


@unoffend.error
async def unoffend_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    await offend_error(interaction, error)


@bot.event
async def setup_hook():
    await bot.tree.sync()

async def build_conversation_history(message, system_prompt, is_admin=False):
    """Рекурсивно собирает цепочку реплаев, чтобы ИИ видел контекст диалога"""
    messages = [{"role": "system", "content": system_prompt}]
    if is_admin:
        messages.append({"role": "system", "content": ADMIN_OVERRIDE_PROMPT})
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
    # В личных сообщениях бот вообще не общается; других ботов тоже игнорируем.
    if message.guild is None or message.author.bot:
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
        now = time_module.time()
        user_id = str(message.author.id)
        async with state_lock:
            offense = state["offenses"].get(user_id)
            if offense and offense["until"] <= now:
                del state["offenses"][user_id]
                save_state()
                offense = None

            if offense and offense.get("guild_id") == message.guild.id:
                until = offense["until"]
                block_reason = offense.get("reason", "Не указана")
                rejection = f"🔇 Тебе закрыт доступ к ИИ до <t:{until}:R>. Причина: {discord.utils.escape_mentions(block_reason)}"
            else:
                usage_key = f"{message.guild.id}:{user_id}"
                usage = state["usage"].get(usage_key, {"start": now, "count": 0})
                if now - usage["start"] >= HOURLY_SECONDS:
                    usage = {"start": now, "count": 0}
                if usage["count"] >= HOURLY_LIMIT:
                    reset_at = int(usage["start"] + HOURLY_SECONDS)
                    rejection = f"⏳ Ты использовал все 10 сообщений. Лимит обновится <t:{reset_at}:R>."
                else:
                    usage["count"] += 1
                    state["usage"][usage_key] = usage
                    save_state()
                    rejection = None

        if rejection:
            await message.reply(rejection, mention_author=False, allowed_mentions=discord.AllowedMentions.none())
            return

        async with message.channel.typing():
            try:
                # Собираем всю цепочку диалога в массив сообщений
                is_admin = message.author.guild_permissions.administrator
                messages_payload = await build_conversation_history(message, SYSTEM_PROMPT, is_admin)

                # Если по какой-то причине сообщений нет (пустой пинг)
                if not any(item["role"] == "user" for item in messages_payload):
                    await message.reply("вась")
                    return

                # Запрос к OpenRouter с учетом истории
                response = await asyncio.to_thread(
                    ai_client.chat.completions.create,
                    model=OPENROUTER_MODEL,
                    messages=messages_payload,
                    max_tokens=500,
                )
                
                reply_text = response.choices[0].message.content or "вась"

                # Делим длинные ответы под лимит Дискорда в 700 символов
                if len(reply_text) > 700:
                    for i in range(0, len(reply_text), 700):
                        await message.channel.send(reply_text[i:i+700])
                else:
                    await message.reply(reply_text)

            except Exception as e:
                print(f"Error communicating with OpenRouter: {e}")
                await message.reply("чето наебнулось")

    await bot.process_commands(message)

bot.run(DISCORD_TOKEN)
