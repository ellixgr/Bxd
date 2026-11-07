import os
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
    msg = bot.reply_to(message, "⏳ Baixando o vídeo em alta qualidade...")
    
    os.makedirs("downloads", exist_ok=True)
    
    # Configuração do yt-dlp para máxima qualidade e formato MP4
    ydl_opts = {
        'format': 'bestvideo+bestaudio/best',
        'outtmpl': 'downloads/%(id)s.%(ext)s',
        'merge_output_format': 'mp4',
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            base, ext = os.path.splitext(filename)
            final_file = base + ".mp4"
            if not os.path.exists(final_file):
                final_file = filename

        bot.edit_message_text("⬆️ Enviando o vídeo...", chat_id=message.chat.id, message_id=msg.message_id)
        
        with open(final_file, 'rb') as video:
            bot.send_video(message.chat.id, video, supports_streaming=True)
            
        bot.delete_message(message.chat.id, msg.message_id)
        
        # Limpa o arquivo do servidor após o envio
        if os.path.exists(final_file):
            os.remove(final_file)
            
    except Exception as e:
        bot.edit_message_text(f"❌ Erro ao processar o vídeo: {str(e)}", chat_id=message.chat.id, message_id=msg.message_id)

if __name__ == "__main__":
    print("Bot e servidor web iniciados com sucesso...")
    bot.infinity_polling()
