import discord
from discord.ext import commands
import yt_dlp
import asyncio
import urllib.request
import re
import os
from telethon import TelegramClient
from dotenv import load_dotenv

# ==========================================
# 1. CARICAMENTO DATI SENSIBILI
# ==========================================
# Questa funzione legge automaticamente il file .env nascosto nella cartella
load_dotenv()

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
TELEGRAM_API_ID = int(os.getenv('TELEGRAM_API_ID')) # Convertito in numero interno (int)
TELEGRAM_API_HASH = os.getenv('TELEGRAM_API_HASH')
PHONE_NUMBER = os.getenv('PHONE_NUMBER')
TARGET_TG_BOT = os.getenv('TARGET_TG_BOT')

# Controllo di sicurezza: se manca un dato, il bot si ferma e ti avvisa
if not all([DISCORD_TOKEN, TELEGRAM_API_ID, TELEGRAM_API_HASH, PHONE_NUMBER, TARGET_TG_BOT]):
    raise ValueError("❌ Errore: Mancano alcuni dati nel file .env! Controlla di aver compilato tutto.")

# ==========================================
# 2. INIZIALIZZAZIONE
# ==========================================
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
bot.remove_command('help') 

tg_client = TelegramClient('my_session', TELEGRAM_API_ID, TELEGRAM_API_HASH)

song_queue = []

YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'default_search': 'auto'
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

# ==========================================
# 3. COMANDI MUSICALI
# ==========================================
async def play_next_song(ctx):
    if not ctx.voice_client:
        return

    if len(song_queue) > 0:
        next_track = song_queue.pop(0)
        webpage_url = next_track['webpage_url']
        title = next_track['title']
        
        try:
            loop = asyncio.get_event_loop()
            with yt_dlp.YoutubeDL(YTDL_OPTIONS) as ydl:
                info = await loop.run_in_executor(None, lambda: ydl.extract_info(webpage_url, download=False))
                
                if 'entries' in info:
                    info = info['entries'][0]
                audio_url = info['url']
                
            source = discord.FFmpegPCMAudio(audio_url, **FFMPEG_OPTIONS)
            ctx.voice_client.play(source, after=lambda e: bot.loop.create_task(play_next_song(ctx)))
            await ctx.send(f"🎶 Ora in riproduzione dalla coda: **{title}**")
            
        except Exception as e:
            print(f"Errore durante la riproduzione dalla coda: {e}")
            await ctx.send("❌ Errore con la traccia in coda. Passo alla successiva...")
            bot.loop.create_task(play_next_song(ctx))
    else:
        await ctx.send("📁 La coda è vuota! Riproduzione terminata.")

@bot.event
async def on_ready():
    print(f"Bot online e operativo! Acceduto come: {bot.user}")

@bot.command()
async def play(ctx, *, search: str):
    if not ctx.author.voice:
        await ctx.send("Devi prima entrare in un canale vocale!")
        return

    voice_channel = ctx.author.voice.channel

    if not ctx.voice_client:
        await voice_channel.connect()
    elif ctx.voice_client.channel != voice_channel:
        await ctx.voice_client.move_to(voice_channel)

    if "spotify.com" in search:
        try:
            req = urllib.request.Request(search, headers={'User-Agent': 'Mozilla/5.0'})
            loop = asyncio.get_event_loop()
            html = await loop.run_in_executor(None, lambda: urllib.request.urlopen(req).read().decode('utf-8'))
            
            title_match = re.search(r'<title>(.*?)</title>', html)
            if title_match:
                raw_title = title_match.group(1)
                clean_title = raw_title.replace(" | Spotify", "").replace(" - song and lyrics by ", " ")
                search = f"{clean_title} audio"
                await ctx.send(f"🟢 Link Spotify rilevato! Cerco su YouTube: `{search}`...")
            else:
                raise Exception("Impossibile estrarre il titolo.")
        except Exception as e:
            await ctx.send("❌ Impossibile leggere il link Spotify.")
            print(e)
            return
    else:
        await ctx.send(f"🔎 Cerco `{search}`...")

    try:
        loop = asyncio.get_event_loop()
        with yt_dlp.YoutubeDL(YTDL_OPTIONS) as ydl:
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(search, download=False))
            if 'entries' in info:
                info = info['entries'][0]
                
            audio_url = info['url']
            title = info['title']
            webpage_url = info.get('webpage_url', search) 
    except Exception as e:
        await ctx.send("❌ Impossibile trovare o estrarre questa traccia.")
        print(e)
        return

    track = {'webpage_url': webpage_url, 'title': title, 'audio_url': audio_url}

    if ctx.voice_client.is_playing() or ctx.voice_client.is_paused():
        song_queue.append(track)
        await ctx.send(f"📁 **{title}** è stata aggiunta alla coda! (Posizione: #{len(song_queue)})")
    else:
        try:
            source = discord.FFmpegPCMAudio(audio_url, **FFMPEG_OPTIONS)
            ctx.voice_client.play(source, after=lambda e: bot.loop.create_task(play_next_song(ctx)))
            await ctx.send(f"🎶 Ora in riproduzione: **{title}**")
        except Exception as e:
            await ctx.send("❌ Impossibile avviare la riproduzione audio.")
            print(e)

@bot.command(name="skip", aliases=["salta"])
async def skip(ctx, posizione: int = None):
    global song_queue

    if not ctx.voice_client or not (ctx.voice_client.is_playing() or ctx.voice_client.is_paused()):
        await ctx.send("Non c'è nessuna canzone in riproduzione da saltare.")
        return

    if posizione is not None:
        if posizione < 1 or posizione > len(song_queue):
            await ctx.send(f"❌ Numero non valido! La coda ha attualmente {len(song_queue)} canzoni.")
            return
        
        if posizione > 1:
            titolo_scelto = song_queue[posizione - 1]['title']
            del song_queue[:posizione - 1]
            await ctx.send(f"⏭️ Salto direttamente alla posizione #{posizione}: **{titolo_scelto}**")
        else:
            await ctx.send("⏭️ Salto alla prossima canzone in coda...")
    else:
        await ctx.send("⏭️ Traccia saltata!")

    ctx.voice_client.stop()

@bot.command(name="pausa")
async def pausa(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("⏸️ Musica messa in pausa. Usa `!riprendi` per continuare.")
    else:
        await ctx.send("Non c'è nessuna canzone in riproduzione al momento.")

@bot.command(name="riprendi")
async def riprendi(ctx):
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("▶️ Riproduzione ripresa!")
    else:
        await ctx.send("La musica non è in pausa.")

@bot.command(name="stop")
async def stop(ctx):
    global song_queue
    song_queue.clear()
    
    if ctx.voice_client and (ctx.voice_client.is_playing() or ctx.voice_client.is_paused()):
        ctx.voice_client.stop()
        await ctx.send("🛑 Riproduzione interrotta e coda svuotata con successo.")
    else:
        await ctx.send("La coda è stata resettata.")

@bot.command(name="coda")
async def mostra_coda(ctx):
    if len(song_queue) == 0:
        await ctx.send("📁 La coda è attualmente vuota.")
        return
        
    messaggio = "__**Prossime canzoni in coda:**__\n"
    for i, track in enumerate(song_queue[:10], 1):
        messaggio += f"{i}. **{track['title']}**\n"
        
    if len(song_queue) > 10:
        messaggio += f"...e altre {len(song_queue) - 10} canzoni."
        
    await ctx.send(messaggio)

@bot.command()
async def leave(ctx):
    global song_queue
    song_queue.clear()
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("Arrivederci! 👋")
    else:
        await ctx.send("Non sono in un canale vocale.")

# ==========================================
# 4. TELEGRAM BRIDGE
# ==========================================
@bot.command()
async def fetch(ctx, *, command_text: str):
    """Invia un comando a Telegram, attende e aggiorna un singolo messaggio con la risposta."""
    status_msg = await ctx.send(f"🔄 **[1/3]** Inviando il comando `{command_text}` a Telegram...")

    try:
        await tg_client.send_message(TARGET_TG_BOT, command_text)

        await status_msg.edit(content="⏳ **[2/3]** Attesa di 5 secondi per l'elaborazione del bot...")
        await asyncio.sleep(5)

        messages = await tg_client.get_messages(TARGET_TG_BOT, limit=2)
        messages.reverse() 
        
        found_reply = False
        final_text = ""
        file_path = None

        for msg in messages:
            if msg.out:
                continue 
                
            found_reply = True
            
            if msg.text:
                final_text += f"{msg.text}\n"

            if msg.media:
                await status_msg.edit(content="📥 **[3/3]** Scaricando il file da Telegram (potrebbe volerci un attimo)...")
                file_path = await tg_client.download_media(msg.media)

        if not found_reply:
            await status_msg.edit(content="❌ **Errore:** Il bot di Telegram non ha risposto entro 5 secondi.")
            return

        display_text = f"💬 **Risposta da Telegram:**\n{final_text}" if final_text else "✅ **File ricevuto da Telegram:**"

        if file_path:
            await status_msg.edit(content=display_text, attachments=[discord.File(file_path)])
            os.remove(file_path) 
        else:
            await status_msg.edit(content=display_text)

    except Exception as e:
        await status_msg.edit(content="❌ **Errore critico:** Si è verificato un problema di connessione con Telegram.")
        print(f"Error in fetch: {e}")

# ==========================================
# 5. MENU & STARTUP
# ==========================================
@bot.command(name="help", aliases=["aiuto", "comandi"])
async def help_command(ctx):
    embed = discord.Embed(
        title="🎵 Menu di Aiuto & Bridge",
        description="Ecco tutti i comandi che puoi utilizzare:",
        color=discord.Color.blue()
    )
    
    embed.add_field(name="▶️ !play <canzone o link>", value="Riproduce un brano o lo aggiunge alla coda (supporta YouTube e Spotify).", inline=False)
    embed.add_field(name="⏭️ !skip [numero]", value="Salta la traccia corrente o passa a una posizione esatta.", inline=False)
    embed.add_field(name="⏸️ !pausa / ▶️ !riprendi", value="Mette in pausa o riprende la musica.", inline=False)
    embed.add_field(name="🛑 !stop", value="Ferma la musica e svuota la coda.", inline=False)
    embed.add_field(name="📁 !coda", value="Mostra la lista delle prossime canzoni in attesa.", inline=False)
    embed.add_field(name="👋 !leave", value="Scollega il bot dal canale vocale.", inline=False)
    embed.add_field(name="🔄 !fetch <comando>", value="Invia una richiesta al bot di Telegram configurato e riporta il risultato qui.", inline=False)
    
    await ctx.send(embed=embed)

async def main():
    print("Avviando Telegram...")
    await tg_client.start(phone=PHONE_NUMBER)
    print("Telegram connesso con successo!")

    print("Avviando Discord...")
    async with bot:
        await bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())