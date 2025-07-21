import os
import discord
from discord.ext import commands
from collections import defaultdict
import sqlite3
from datetime import datetime

# Configuración
PREFIX = '!'
MAX_REPEATED_MSGS = 3
MAX_MENTIONS = 5
MAX_STRIKES = 3
BANNED_LINKS = ["http://malicioso.com", "phishing.com"]
BANNED_WORDS = ["palabra1", "palabra2"]

# Base de datos SQLite
conn = sqlite3.connect('spam_database.db')
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS strikes (
        user_id INTEGER PRIMARY KEY,
        strikes INTEGER,
        last_warning TEXT
    )
''')
conn.commit()

bot = commands.Bot(command_prefix=PREFIX, intents=discord.Intents.all())
user_message_count = defaultdict(list)


# --- Función mejorada para strikes ---
async def add_strike(user: discord.Member):
    cursor.execute('SELECT strikes FROM strikes WHERE user_id = ?',
                   (user.id, ))
    result = cursor.fetchone()
    current_strikes = result[
        0] + 1 if result else 1  # Definimos current_strikes aquí

    cursor.execute(
        '''
        INSERT OR REPLACE INTO strikes (user_id, strikes, last_warning)
        VALUES (?, ?, ?)
    ''', (user.id, current_strikes, str(datetime.now())))
    conn.commit()

    if current_strikes >= MAX_STRIKES:
        await user.send(
            f"🔴 Has sido expulsado por acumular {MAX_STRIKES} strikes.")
        await user.kick(reason="Spam excesivo")
        cursor.execute('DELETE FROM strikes WHERE user_id = ?', (user.id, ))
        conn.commit()

    return current_strikes  # Retornamos el valor para usarlo en los mensajes


# --- Detección de embeds maliciosos ---
def has_malicious_embed(message):
    for embed in message.embeds:
        if embed.url and any(link in embed.url.lower()
                             for link in BANNED_LINKS):
            return True
    return False


# --- Evento on_message corregido ---
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    user_id = message.author.id
    content = message.content.lower()

    # 1. Mensajes repetidos (flood)
    user_message_count[user_id].append(content)
    if len(user_message_count[user_id]) >= MAX_REPEATED_MSGS:
        if all(msg == content
               for msg in user_message_count[user_id][-MAX_REPEATED_MSGS:]):
            await message.delete()
            current_strikes = await add_strike(message.author
                                               )  # Usamos el valor retornado
            warning = await message.channel.send(
                f"⚠️ {message.author.mention}, ¡Stop spamming! (Strike: {current_strikes}/{MAX_STRIKES})"
            )
            await warning.delete(delay=5.0)
            user_message_count[user_id].clear()

    # 2. Menciones excesivas
    mentions = len(message.mentions) + len(message.role_mentions)
    if mentions > MAX_MENTIONS:
        await message.delete()
        current_strikes = await add_strike(message.author)
        await message.channel.send(
            f"⚠️ {message.author.mention}, ¡No menciones a tantos! (Strike: {current_strikes}/{MAX_STRIKES})",
            delete_after=5.0)

    # 3. Enlaces prohibidos (texto o embed)
    if any(link in content
           for link in BANNED_LINKS) or has_malicious_embed(message):
        await message.delete()
        current_strikes = await add_strike(message.author)
        await message.author.send("🔴 Enlace malicioso detectado.")

    # 4. Palabras prohibidas
    if any(word in content for word in BANNED_WORDS):
        await message.delete()
        current_strikes = await add_strike(message.author)
        await message.channel.send(
            f"⚠️ {message.author.mention}, ¡Palabra prohibida! (Strike: {current_strikes}/{MAX_STRIKES})",
            delete_after=5.0)

    await bot.process_commands(message)


# --- Comandos ---
@bot.command()
@commands.has_permissions(manage_messages=True)
async def strikes(ctx, user: discord.Member):
    cursor.execute(
        'SELECT strikes, last_warning FROM strikes WHERE user_id = ?',
        (user.id, ))
    result = cursor.fetchone()
    if result:
        await ctx.send(
            f"🔴 {user.mention}: {result[0]} strikes (Última advertencia: {result[1]})"
        )
    else:
        await ctx.send(f"🟢 {user.mention} no tiene strikes.")


@bot.command()
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int):
    await ctx.channel.purge(limit=amount + 1)
    await ctx.send(f"🗑️ {amount} mensajes borrados.", delete_after=3.0)

TOKEN = os.environ.get('TOKEN')
bot.run(TOKEN)
