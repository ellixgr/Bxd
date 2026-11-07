import os
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import telebot
import yt_dlp

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

# Inicia o servidor web em uma thread separada para manter a porta aberta
threading.Thread(target=run_keep_alive_server, daemon=True).start()
# -------------------------------------------------------------

# Pega as variáveis de ambiente configuradas no Render
TOKEN = os.environ.get("TELEGRAM_TOKEN")
OWNER_ID = int(os.environ.get("OWNER_ID", "7711945457"))

bot = telebot.TeleBot(TOKEN)

# Bloqueia qualquer usuário que não seja o dono
@bot.message_handler(func=lambda message: message.from_user.id != OWNER_ID)
def ignore_others(message):
    bot.reply_to(message, "🚫 Acesso negado. Este bot é privado.")

# Mensagem inicial apenas para o dono
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "Tudo pronto. Envie o link do vídeo para eu baixar e enviar em alta qualidade.")

# Processa o link enviado pelo dono
@bot.message_handler(func=lambda message: message.from_user.id == OWNER_ID and message.text and message.text.startswith('http'))
def download_video(message):
    url = message.text.strip()
    msg = bot.reply_to(message, "⏳ Iniciando conexão com o link...")
    
    os.makedirs("downloads", exist_ok=True)
    
    last_update_time = [0]  # Usado para controlar o intervalo de atualização da mensagem

    def yt_progress_hook(d):
        if d['status'] == 'downloading':
            ora = time.time()
            # Atualiza a cada 3 segundos para evitar bloqueio (flood) da API do Telegram
            if ora - last_update_time[0] < 3:
                return
            last_update_time[0] = ora

            percent = d.get('_percent_str', '0.0%').strip()
            speed = d.get('_speed_str', 'Desconhecida').strip()
            eta = d.get('_eta_str', 'Desconhecido').strip()
            
            # Pega o tamanho baixado e o total se disponível
            downloaded = d.get('downloaded_bytes', 0)
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            
            def human_readable(bytes_num):
                for unit in ['B', 'KB', 'MB', 'GB']:
                    if bytes_num < 1024.0:
                        return f"{bytes_num:.2f} {unit}"
                    bytes_num /= 1024.0
                return f"{bytes_num:.2f} TB"

            baixado_mb = human_readable(downloaded)
            total_mb = human_readable(total) if total > 0 else "Calculando..."

            texto_progresso = (
                f"📥 **BAIXANDO VÍDEO...**\n\n"
                f"📊 **Progresso:** `{percent}`\n"
                f"📦 **Baixado:** `{baixado_mb} de {total_mb}`\n"
                f"⚡ **Velocidade:** `{speed}`\n"
                f"⏱️ **Falta:** `{eta}`"
            )
            try:
                bot.edit_message_text(texto_progresso, chat_id=message.chat.id, message_id=msg.message_id, parse_mode="Markdown")
            except Exception:
                pass  - # Ignora se a mensagem não mudou o suficiente

    ydl_opts = {
        'format': 'bestvideo+bestaudio/best',
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
            bot.edit_message_text("🔍 Extraindo informações e gerando arquivo...", chat_id=message.chat.id, message_id=msg.message_id)
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            base, ext = os.path.splitext(filename)
            final_file = base + ".mp4"
            if not os.path.exists(final_file):
                final_file = filename

        bot.edit_message_text("⬆️ Download concluído! Enviando o vídeo para o chat...", chat_id=message.chat.id, message_id=msg.message_id)
        
        with open(final_file, 'rb') as video:
            bot.send_video(message.chat.id, video, supports_streaming=True)
            
        bot.delete_message(message.chat.id, msg.message_id)
            
    except Exception as e:
        try:
            bot.edit_message_text(f"❌ **Erro ao processar o vídeo:**\n`{str(e)}`", chat_id=message.chat.id, message_id=msg.message_id, parse_mode="Markdown")
        except:
            bot.send_message(message.chat.id, f"❌ Erro ao processar o vídeo: {str(e)}")
            
    finally:
        if final_file and os.path.exists(final_file):
            try:
                os.remove(final_file)
            except:
                pass

if __name__ == "__main__":
    print("Bot e servidor web iniciados com sucesso...")
    bot.infinity_polling()
