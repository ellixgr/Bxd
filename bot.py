import os
import socket
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message

# Força o Python a usar IPv4 para evitar timeout no Termux
old_getaddrinfo = socket.getaddrinfo
socket.getaddrinfo = lambda *a, **kw: [r for r in old_getaddrinfo(*a, **kw) if r[0] == socket.AF_INET]

API_ID = 37157305
API_HASH = "bc217a1d9e670ff5fb875a04e6667e39"
MEU_ID = 7711945457

# Caminho base das pastas do TeraBox no seu celular Android
CAMINHO_BASE = "/storage/emulated/0/Download/TeraBox/Download"

app = Client(
    "minha_conta",
    api_id=API_ID,
    api_hash=API_HASH,
    sleep_threshold=60
)

# Estado temporário para guardar a legenda e o chat de destino escolhidos por você
config_usuario = {
    "destino": None,
    "legenda": "#vazados"
}

@app.on_message(filters.user(MEU_ID) & filters.command("start"))
async def cmd_start(client: Client, message: Message):
    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("📁 Navegar nas Pastas do TeraBox", callback_data="listar_pastas_raiz")],
        [InlineKeyboardButton("⚙️ Configurar Destino e Legenda", callback_data="menu_config")]
    ])
    await message.reply_text(
        "🤖 **Painel TeraBox - Local (Termux)**\n\n"
        "Escolha uma opção abaixo para gerenciar os arquivos do seu celular:",
        reply_markup=teclado
    )

@app.on_callback_query(filters.user(MEU_ID))
async def callback_handler(client, callback_query):
    data = callback_query.data
    
    if data == "menu_config":
        await callback_query.message.edit_text(
            f"⚙️ **Configurações Atuais:**\n"
            f"• Legenda/Hashtag: `{config_usuario['legenda']}`\n\n"
            f"Para alterar a legenda, envie o comando:\n`/legenda sua_nova_legenda`",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Voltar", callback_data="voltar_inicio")]])
        )
        
    elif data == "voltar_inicio":
        await callback_query.message.edit_text(
            "🤖 **Painel TeraBox - Local (Termux)**\n\n"
            "Escolha uma opção abaixo:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📁 Navegar nas Pastas do TeraBox", callback_data="listar_pastas_raiz")],
                [InlineKeyboardButton("⚙️ Configurar Destino e Legenda", callback_data="menu_config")]
            ])
        )
        
    elif data == "listar_pastas_raiz":
        if not os.path.exists(CAMINHO_BASE):
            await callback_query.answer("Pasta do TeraBox não encontrada no celular!", show_alert=True)
            return
            
        pasta_sub = [f for f in os.listdir(CAMINHO_BASE) if os.path.isdir(os.path.join(CAMINHO_BASE, f))]
        
        botoes = []
        for pasta in pasta_sub:
            botoes.append([InlineKeyboardButton(f"📁 {pasta}", callback_data=f"pasta_{pasta}")])
        botoes.append([InlineKeyboardButton("🔙 Voltar", callback_data="voltar_inicio")])
        
        await callback_query.message.edit_text(
            "📂 **Selecione a pasta principal (ex: Bruninha):**",
            reply_markup=InlineKeyboardMarkup(botoes)
        )
        
    elif data.startswith("pasta_"):
        nome_pasta = data.replace("pasta_", "")
        caminho_atual = os.path.join(CAMINHO_BASE, nome_pasta)
        
        subpastas = [f for f in os.listdir(caminho_atual) if os.path.isdir(os.path.join(caminho_atual, f))]
        
        botoes = []
        for sub in subpastas:
            botoes.append([InlineKeyboardButton(f"📁 {sub}", callback_data=f"sub_{nome_pasta}_{sub}")])
        botoes.append([InlineKeyboardButton("🔙 Voltar", callback_data="listar_pastas_raiz")])
        
        await callback_query.message.edit_text(
            f"📂 Pasta: `{nome_pasta}`\nEscolha a subpasta (ex: India Gotica):",
            reply_markup=InlineKeyboardMarkup(botoes)
        )
        
    elif data.startswith("sub_"):
        partes = data.replace("sub_", "").split("_", 1)
        pasta_pai, subpasta = partes[0], partes[1]
        
        caminho_final = os.path.join(CAMINHO_BASE, pasta_pai, subpasta)
        
        await callback_query.message.edit_text(
            f"📁 **Pasta selecionada:** `{pasta_pai} / {subpasta}`\n\n"
            "O que deseja fazer com as mídias desta pasta?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📸 Enviar Fotos", callback_data=f"enviar_tipo_fotos_{pasta_pai}_{subpasta}")],
                [InlineKeyboardButton("🎥 Enviar Vídeos", callback_data=f"enviar_tipo_videos_{pasta_pai}_{subpasta}")],
                [InlineKeyboardButton("🔙 Voltar", callback_data=f"pasta_{pasta_pai}")]
            ])
        )
        
    elif data.startswith("enviar_tipo_"):
        tipo, resto = data.replace("enviar_tipo_", "").split("_", 1)
        pasta_pai, subpasta = resto.split("_", 1) if "_" in resto else (resto, "")
        
        caminho_final = os.path.join(CAMINHO_BASE, pasta_pai, subpasta)
        
        await callback_query.answer(f"Varrendo e enviando {tipo}...", show_alert=True)
        await callback_query.message.reply_text(f"🚀 Iniciando envio de {tipo} da pasta `{subpasta}`...")
        
        # Executa o envio dos arquivos locais encontrados na pasta
        extensoes = (".jpg", ".jpeg", ".png", ".webp") if tipo == "fotos" else (".mp4", ".mkv", ".avi", ".mov")
        
        arquivos = [f for f in os.listdir(caminho_final) if f.lower().endswith(extensoes)]
        
        if not arquivos:
            await callback_query.message.reply_text(f"⚠️ Nenhum arquivo de {tipo} encontrado em `{subpasta}`.")
            return
            
        # Pede o link ou chat de destino onde quer enviar
        await callback_query.message.reply_text(
            f"Encontrados {len(arquivos)} arquivos. Para qual chat/grupo você quer enviar? Responda com o ID ou link do grupo."
        )

@app.on_message(filters.user(MEU_ID) & filters.command("legenda"))
async def alterar_legenda(client: Client, message: Message):
    nova_leg = message.text.replace("/legenda", "").strip()
    if nova_leg:
        config_usuario["legenda"] = nova_leg
        await message.reply_text(f"✅ Legenda atualizada para:\n`{nova_leg}`")
    else:
        await message.reply_text(f"ℹ️ Legenda atualizada atual: `{config_usuario['legenda']}`")

if __name__ == "__main__":
    print("🤖 Bot local do Termux iniciado com sucesso!")
    app.run()
