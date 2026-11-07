import os
import socket
import asyncio
from aiohttp import web
from pyrogram import Client, filters
from pyrogram.types import Message

# Força o Python a usar IPv4 para evitar timeout
old_getaddrinfo = socket.getaddrinfo
socket.getaddrinfo = lambda *a, **kw: [r for r in old_getaddrinfo(*a, **kw) if r[0] == socket.AF_INET]

# Puxa estritamente das variáveis do Render. Sem valores padrão expostos!
API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
LINK_DESTINO = os.environ["LINK_DESTINO"]
NOME_TOPICO_ORIGEM = os.environ.get("HASHTAG", "#vazados")

app = Client(
    "minha_conta",
    api_id=API_ID,
    api_hash=API_HASH,
    sleep_threshold=60
)

# Servidor web leve para o UptimeRobot manter o Render acordado 24h
async def handle_ping(request):
    return web.Response(text="Bot TeraBox Manager Rodando 24h com Sucesso!")

async def start_web_server():
    web_app = web.Application()
    web_app.router.add_get("/", handle_ping)
    runner = web.AppRunner(web_app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"🌐 Servidor web ativo na porta {port} para o UptimeRobot.")

# Monitora as tuas mensagens (qualquer mídia que mandares nas Salvas ou chat privado)
@app.on_message(filters.me & (filters.video | filters.photo | filters.document))
async def processar_midia_enviada(client: Client, message: Message):
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
            
        print(f"⚡ Mídia repassada com sucesso para o destino com a legenda: {nova_legenda}")
    except Exception as e:
        print(f"⚠️ Erro ao enviar mídia: {e}")

async def main():
    async with app:
        print("🤖 Bot conectado na sua conta com sucesso!")
        await start_web_server()
        await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
