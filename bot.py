import sys
import asyncio

if sys.version_info >= (3, 10):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

import os
import socket
from aiohttp import web
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

old_getaddrinfo = socket.getaddrinfo
socket.getaddrinfo = lambda *a, **kw: [r for r in old_getaddrinfo(*a, **kw) if r[0] == socket.AF_INET]

# Dados fixos integrados
API_ID = 37157305
API_HASH = "bc217a1d9e670ff5fb875a04e6667e39"
LINK_DESTINO = "https://t.me/+ucAti-Hjh-c1Njcx"
MEU_ID = 7711945457
NOME_TOPICO_ORIGEM = "#vazados"

app = Client(
    "minha_conta",
    api_id=API_ID,
    api_hash=API_HASH,
    sleep_threshold=60
)

bot_ligado = False

async def handle_ping(request):
    status = "LIGADO e Operacional" if bot_ligado else "DESLIGADO (Aguardando Comando)"
    return web.Response(text=f"Bot TeraBox Manager - Status: {status}")

async def start_web_server():
    web_app = web.Application()
    web_app.router.add_get("/", handle_ping)
    runner = web.AppRunner(web_app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"🌐 Servidor web ativo na porta {port} para o UptimeRobot.")

@app.on_message(filters.user(MEU_ID) & filters.private)
async def painel_controle(client: Client, message: Message):
    global bot_ligado
    
    texto = message.text.lower() if message.text else ""
    
    if "/ligar" in texto or texto == "ligar":
        bot_ligado = True
        await message.reply_text("🟢 **Bot LIGADO com sucesso!** Pronto para disparar mídias.")
        return
    elif "/desligar" in texto or texto == "desligar":
        bot_ligado = False
        await message.reply_text("🔴 **Bot DESLIGADO!** Envios pausados.")
        return
    
    status_atual = "🟢 LIGADO" if bot_ligado else "🔴 DESLIGADO"
    teclado = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🟢 Ligar Disparos", callback_data="ligar_bot"),
            InlineKeyboardButton("🔴 Desligar", callback_data="desligar_bot")
        ]
    ])
    await message.reply_text(
        f"🤖 **Painel de Controle - TeraBox (Render)**\n\n"
        f"Status atual: {status_atual}\n\n"
        f"Use os botões abaixo para controlar quando o bot pode enviar mídias para o grupo.",
        reply_markup=teclado
    )

@app.on_callback_query(filters.user(MEU_ID))
async def callback_handler(client, callback_query):
    global bot_ligado
    data = callback_query.data
    
    if data == "ligar_bot":
        bot_ligado = True
        await callback_query.answer("Bot LIGADO com sucesso!", show_alert=True)
        await callback_query.message.edit_text(
            "🟢 **Painel de Controle - TeraBox**\n\n"
            "Status atual: 🟢 LIGADO\n\n"
            "Agora as mídias que você enviar serão disparadas para o grupo."
        )
    elif data == "desligar_bot":
        bot_ligado = False
        await callback_query.answer("Bot DESLIGADO!", show_alert=True)
        await callback_query.message.edit_text(
            "🔴 **Painel de Controle - TeraBox**\n\n"
            "Status atual: 🔴 DESLIGADO\n\n"
            "Os envios estão pausados. Nenhuma mídia será repassada."
        )

@app.on_message(filters.user(MEU_ID) & filters.private & (filters.video | filters.photo | filters.document))
async def processar_midia_enviada(client: Client, message: Message):
    global bot_ligado
    if not bot_ligado:
        return

    legenda_original = message.caption or ""
    if legenda_original:
        nova_legenda = f"{legenda_original}\n\n{NOME_TOPICO_ORIGEM}"
    else:
        nova_legenda = NOME_TOPICO_ORIGEM

    try:
        if message.video:
            await client.send_video(chat_id=LINK_DESTINO, video=message.video.file_id, caption=nova_legenda)
        elif message.photo:
            await client.send_photo(chat_id=LINK_DESTINO, photo=message.photo.file_id, caption=nova_legenda)
        elif message.document:
            await client.send_document(chat_id=LINK_DESTINO, document=message.document.file_id, caption=nova_legenda)
            
        print(f"⚡ Mídia repassada com sucesso com a legenda: {nova_legenda}")
    except Exception as e:
        print(f"⚠️ Erro ao enviar mídia: {e}")

async def main():
    async with app:
        print("🤖 Bot conectado na sua conta com sucesso!")
        await start_web_server()
        await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
