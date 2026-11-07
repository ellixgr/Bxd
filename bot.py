import os
import time
import datetime
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import yt_dlp
from pymongo import MongoClient

# --- Servidor Web Keep-Alive para o Render (Plano Gratuito) ---
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is active and running!")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

def run_keep_alive_server():
    port = int(os.getenv("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), SimpleHandler)
    server.serve_forever()

threading.Thread(target=run_keep_alive_server, daemon=True).start()

# --- Configurações e Credenciais (Seguras via Variáveis de Ambiente) ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")
OWNER_ID = int(os.environ.get("OWNER_ID", "7711945457"))
MP = os.environ.get("MP")
MONGO_URI = os.environ.get("MONGO_URI")

bot = telebot.TeleBot(TOKEN)

# --- Conexão MongoDB (Collections isoladas) ---
try:
    mongo_client = MongoClient(MONGO_URI)
    db = mongo_client["bot_baixador_videos_db"]
    users_col = db["users_limits"]
    subs_col = db["subscriptions"]
    print("Conectado ao MongoDB com sucesso!")
except Exception as e:
    print(f"Erro ao conectar no MongoDB: {e}")

# Armazena temporariamente os links pendentes
user_pending_links = {}

def human_readable(bytes_num):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_num < 1024.0:
            return f"{bytes_num:.2f} {unit}"
        bytes_num /= 1024.0
    return f"{bytes_num:.2f} TB"

# --- Funções de Controle de Limite e Assinatura ---
def verificar_acesso(user_id):
    if user_id == OWNER_ID:
        return True, "owner"

    hoje = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    
    # 1. Verifica se tem assinatura VIP ativa
    sub = subs_col.find_one({"user_id": user_id})
    if sub:
        expires_at = sub.get("expires_at")
        if expires_at and expires_at > datetime.datetime.utcnow():
            return True, "vip"
        else:
            subs_col.delete_one({"user_id": user_id})

    # 2. Verifica limite diário gratuito (1 vídeo por dia)
    user_data = users_col.find_one({"user_id": user_id})
    
    if not user_data or user_data.get("date") != hoje:
        users_col.update_one(
            {"user_id": user_id},
            {"$set": {"date": hoje, "downloads_count": 0}},
            upsert=True
        )
        user_data = {"downloads_count": 0}

    if user_data.get("downloads_count", 0) < 1:
        return True, "free"
    
    return False, "limit_exceeded"

def registrar_uso(user_id):
    if user_id == OWNER_ID:
        return
    hoje = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    users_col.update_one(
        {"user_id": user_id, "date": hoje},
        {"$inc": {"downloads_count": 1}},
        upsert=True
    )

def criar_preferencia_mercado_pago(user_id):
    url = "https://api.mercadopago.com/checkout/preferences"
    headers = {
        "Authorization": f"Bearer {MP}",
        "Content-Type": "application/json"
    }
    data = {
        "items": [
            {
                "title": "Acesso VIP - Baixador de Vídeos (1 Semana)",
                "quantity": 1,
                "unit_price": 10.00,
                "currency_id": "BRL"
            }
        ],
        "external_reference": str(user_id),
        "back_urls": {
            "success": "https://t.me/" + bot.get_me().username,
            "pending": "https://t.me/" + bot.get_me().username,
            "failure": "https://t.me/" + bot.get_me().username
        },
        "auto_return": "approved"
    }
    try:
        response = requests.post(url, json=data, headers=headers, timeout=15)
        res_json = response.json()
        return res_json.get("init_point")
    except Exception as e:
        print(f"Erro ao criar preferência MP: {e}")
        return None

# --- Handlers do Bot ---
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "🤖 **Bot de Download Ativo!**\n\n- Você tem direito a **1 vídeo gratuito por dia**.\n- Se precisar baixar mais, faça um plano VIP de R$ 10,00 por 1 semana.\n\nEnvie o link do vídeo para começar!")

@bot.message_handler(commands=['vip', 'plano'])
def menu_vip(message):
    user_id = message.from_user.id
    link_pagamento = criar_preferencia_mercado_pago(user_id)
    
    if link_pagamento:
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("💳 Pagar R$ 10,00 (Pix/Cartão)", url=link_pagamento))
        bot.reply_to(message, "💎 **PLANO VIP SEMANAL**\n\n- Downloads ilimitados por 7 dias!\n- Valor: **R$ 10,00**\n\nClique no botão abaixo para gerar o pagamento:", reply_markup=markup)
    else:
        bot.reply_to(message, "❌ Erro ao gerar link de pagamento. Tente novamente mais tarde.")

@bot.message_handler(func=lambda message: message.text and message.text.startswith('http'))
def handle_link_input(message):
    user_id = message.from_user.id
    
    permitido, status = verificar_acesso(user_id)
    
    if not permitido and status == "limit_exceeded":
        link_pagamento = criar_preferencia_mercado_pago(user_id)
        markup = InlineKeyboardMarkup()
        if link_pagamento:
            markup.add(InlineKeyboardButton("💳 Assinar VIP por R$ 10,00 (1 Semana)", url=link_pagamento))
        
        bot.reply_to(message, 
            "⏳ **Limite Diário Atingido!**\n\n"
            "Você já utilizou seu **1 vídeo gratuito** de hoje.\n"
            "Para continuar baixando sem limites por 1 semana, adquira o plano VIP por apenas **R$ 10,00**!",
            reply_markup=markup
        )
        return

    url = message.text.strip()
    msg = bot.reply_to(message, "🔍 Analisando o link e verificando o tamanho do vídeo...")
    
    ydl_meta_opts = {
        'noplaylist': True,
        'socket_timeout': 30,
        'nocheckcertificate': True,
        'geo_bypass': True,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_meta_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            filesize = info.get('filesize') or info.get('filesize_approx') or 0
            
            if filesize == 0 and 'formats' in info:
                for f in info['formats']:
                    if f.get('filesize'):
                        filesize = max(filesize, f.get('filesize'))
                    elif f.get('filesize_approx'):
                        filesize = max(filesize, f.get('filesize_approx'))

        LIMITE_MEGABYTES = 50 * 1024 * 1024

        if filesize > 0 and filesize > LIMITE_MEGABYTES:
            user_pending_links[message.chat.id] = url
            tamanho_formatado = human_readable(filesize)
            
            markup = InlineKeyboardMarkup()
            markup.row(
                InlineKeyboardButton("📱 Baixar em 480p (Leve)", callback_data="dl_480"),
                InlineKeyboardButton("💻 Baixar em 720p (Padrão)", callback_data="dl_720")
            )
            
            texto_aviso = (
                f"⚠️ **VÍDEO PESADO DETECTADO!**\n\n"
                f"📦 **Tamanho estimado:** `{tamanho_formatado}`\n"
                f"🚫 O arquivo ultrapassa o limite direto de 50MB da API do Telegram.\n\n"
                f"👇 **Escolha uma resolução abaixo para comprimir e baixar com segurança:**"
            )
            bot.edit_message_text(texto_aviso, chat_id=message.chat.id, message_id=msg.message_id, reply_markup=markup, parse_mode="Markdown")
        else:
            bot.delete_message(message.chat.id, msg.message_id)
            registrar_uso(user_id)
            executar_download_e_envio(message, url, resolution_limit=None)

    except Exception as e:
        try:
            bot.edit_message_text(f"❌ **Erro ao analisar o link:**\n`{str(e)}`", chat_id=message.chat.id, message_id=msg.message_id, parse_mode="Markdown")
        except:
            bot.send_message(message.chat.id, f"❌ Erro ao analisar o link: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('dl_'))
def callback_resolution(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    
    if chat_id not in user_pending_links:
        bot.answer_callback_query(call.id, "⚠️ Link expirado ou inválido. Envie novamente.")
        return

    registrar_uso(user_id)

    url = user_pending_links.pop(chat_id)
    resolution = call.data.split('_')[1]
    
    bot.answer_callback_query(call.id, f"✅ Iniciando download em {resolution}p...")
    bot.edit_message_text(f"⚙️ Configurando download em **{resolution}p**, aguarde...", chat_id=chat_id, message_id=call.message.message_id, parse_mode="Markdown")
    
    class DummyMessage:
        def __init__(self, cid, mid, uid):
            self.chat = type('obj', (object,), {'id': cid})
            self.message_id = mid
            self.from_user = type('obj', (object,), {'id': uid})
            
    dummy_msg = DummyMessage(chat_id, call.message.message_id, user_id)
    executar_download_e_envio(dummy_msg, url, resolution_limit=int(resolution))


def executar_download_e_envio(message, url, resolution_limit=None):
    msg_id = message.message_id if hasattr(message, 'message_id') else bot.send_message(message.chat.id, "🔍 Iniciando download...").message_id
    
    if hasattr(message, 'text'):
        msg_id = message.message_id

    os.makedirs("downloads", exist_ok=True)
    last_update_time = [0]

    def yt_progress_hook(d):
        if d['status'] == 'downloading':
            ora = time.time()
            if ora - last_update_time[0] < 2:
                return
            last_update_time[0] = ora

            percent = d.get('_percent_str', 'Calculando...').strip()
            speed = d.get('_speed_str', 'Calculando...').strip()
            eta = d.get('_eta_str', 'Calculando...').strip()
            
            downloaded = d.get('downloaded_bytes', 0)
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0

            baixado_mb = human_readable(downloaded)
            total_mb = human_readable(total) if total > 0 else "Desconhecido"

            texto_progresso = (
                f"📥 **BAIXANDO VÍDEO...**\n\n"
                f"📊 **Progresso:** `{percent}`\n"
                f"📦 **Baixado:** `{baixado_mb} / {total_mb}`\n"
                f"⚡ **Velocidade:** `{speed}`\n"
                f"⏱️ **Tempo Restante:** `{eta}`"
            )
            try:
                bot.edit_message_text(texto_progresso, chat_id=message.chat.id, message_id=msg_id, parse_mode="Markdown")
            except Exception:
                pass
        elif d['status'] == 'finished':
            try:
                bot.edit_message_text("⚙️ Download finalizado! Processando arquivo...", chat_id=message.chat.id, message_id=msg_id)
            except:
                pass

    if resolution_limit:
        format_string = f'bv*[height<={resolution_limit}]+ba/b[height<={resolution_limit}] / best'
    else:
        format_string = 'bestvideo+bestaudio/best'

    ydl_opts = {
        'format': format_string,
        'outtmpl': 'downloads/%(id)s.%(ext)s',
        'merge_output_format': 'mp4',
        'noplaylist': True,
        'socket_timeout': 30,
        'nocheckcertificate': True,
        'geo_bypass': True,
        'progress_hooks': [yt_progress_hook],
    }
    
    final_file = None
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            base, ext = os.path.splitext(filename)
            final_file = base + ".mp4"
            if not os.path.exists(final_file):
                final_file = filename

        file_size = os.path.getsize(final_file)
        uploaded_bytes = [0]
        upload_start_time = [time.time()]
        last_upload_update = [0]

        class ProgressFileWrapper:
            def __init__(self, filepath):
                self._file = open(filepath, 'rb')

            def read(self, size=-1):
                data = self._file.read(size)
                if data:
                    uploaded_bytes[0] += len(data)
                    now = time.time()
                    
                    if now - last_upload_update[0] >= 2:
                        last_upload_update[0] = now
                        elapsed = now - upload_start_time[0]
                        speed = uploaded_bytes[0] / elapsed if elapsed > 0 else 0
                        
                        percent = (uploaded_bytes[0] / file_size) * 100 if file_size > 0 else 0
                        
                        up_baixado = human_readable(uploaded_bytes[0])
                        up_total = human_readable(file_size)
                        up_speed = human_readable(speed) + "/s"
                        
                        texto_envio = (
                            f"⬆️ **ENVIANDO VÍDEO...**\n\n"
                            f"📊 **Progresso:** `{percent:.1f}%`\n"
                            f"📦 **Enviado:** `{up_baixado} / {up_total}`\n"
                            f"⚡ **Velocidade:** `{up_speed}`"
                        )
                        try:
                            bot.edit_message_text(texto_envio, chat_id=message.chat.id, message_id=msg_id, parse_mode="Markdown")
                        except:
                            pass
                return data

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                self._file.close()

        bot.edit_message_text("⬆️ Iniciando envio do arquivo...", chat_id=message.chat.id, message_id=msg_id)

        with ProgressFileWrapper(final_file) as wrapped_file:
            bot.send_document(message.chat.id, wrapped_file, visible_file_name=os.path.basename(final_file))
            
        bot.delete_message(message.chat.id, msg_id)
            
    except Exception as e:
        try:
            bot.edit_message_text(f"❌ **Erro ao processar o vídeo:**\n`{str(e)}`", chat_id=message.chat.id, message_id=msg_id, parse_mode="Markdown")
        except:
            bot.send_message(message.chat.id, f"❌ Erro ao processar o vídeo: {str(e)}")
            
    finally:
        if final_file and os.path.exists(final_file):
            try:
                os.remove(final_file)
            except:
                pass

if __name__ == "__main__":
    print("Bot, banco de dados e servidor web iniciados com sucesso...")
    bot.infinity_polling()
