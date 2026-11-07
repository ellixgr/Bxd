import os
import time
import datetime
import threading
import uuid
from flask import Flask, render_template_string, request, redirect, url_for
import requests
import yt_dlp
from pymongo import MongoClient

# --- Configurações Seguras (Exclusivamente via Variáveis de Ambiente) ---
MP_ACCESS_TOKEN = os.environ.get("MP_ACCESS_TOKEN")
MONGO_URI = os.environ.get("MONGO_URI")
VIP_SECRET_CODE = os.environ.get("VIP_SECRET_CODE")  # Defina no Render

app = Flask(__name__)

# --- Conexão MongoDB ---
try:
    mongo_client = MongoClient(MONGO_URI)
    db = mongo_client["baixador_videos_db"]
    users_col = db["users_limits"]
    subs_col = db["subscriptions"]
    print("Conectado ao MongoDB com sucesso!")
except Exception as e:
    print(f"Erro ao conectar no MongoDB: {e}")

def verificar_acesso_web(user_ip):
    hoje = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    
    # 1. Verifica se tem assinatura VIP ativa
    sub = subs_col.find_one({"user_ip": user_ip})
    if sub:
        expires_at = sub.get("expires_at")
        if expires_at and expires_at > datetime.datetime.utcnow():
            return "vip", 20 # VIP tem direito a 20 vídeos por dia
        else:
            subs_col.delete_one({"user_ip": user_ip})

    # 2. Limite diário gratuito (1 vídeo por dia)
    user_data = users_col.find_one({"user_ip": user_ip})
    if not user_data or user_data.get("date") != hoje:
        users_col.update_one(
            {"user_ip": user_ip},
            {"$set": {"date": hoje, "downloads_count": 0}},
            upsert=True
        )
        user_data = {"downloads_count": 0}

    count = user_data.get("downloads_count", 0)
    if count < 1:
        return "free", 1 - count
    
    return "limit_exceeded", 0

def registrar_uso_web(user_ip):
    hoje = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    users_col.update_one(
        {"user_ip": user_ip, "date": hoje},
        {"$inc": {"downloads_count": 1}},
        upsert=True
    )

def criar_preferencia_mercado_pago(user_ip):
    url = "https://api.mercadopago.com/checkout/preferences"
    headers = {
        "Authorization": f"Bearer {MP_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {
        "items": [
            {
                "title": "Acesso VIP - Baixador de Vídeos (20 vídeos/dia por 7 dias)",
                "quantity": 1,
                "unit_price": 10.00,
                "currency_id": "BRL"
            }
        ],
        "external_reference": user_ip,
        "back_urls": {
            "success": f"https://{request.host}/vip-success?ip={user_ip}",
            "pending": f"https://{request.host}/",
            "failure": f"https://{request.host}/"
        },
        "auto_return": "approved"
    }
    try:
        response = requests.post(url, json=data, headers=headers, timeout=15)
        return response.json().get("init_point")
    except Exception as e:
        print(f"Erro MP: {e}")
        return None

# --- Template HTML com Link Direto de Download ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Baixador de Vídeos</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 20px; display: flex; justify-content: center; align-items: center; min-height: 100vh; }
        .container { background: #1e293b; padding: 30px; border-radius: 12px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); width: 100%; max-width: 500px; text-align: center; }
        h1 { color: #38bdf8; font-size: 22px; margin-bottom: 10px; }
        p { color: #94a3b8; font-size: 14px; margin-bottom: 20px; }
        input[type="text"] { width: 100%; padding: 12px; border: 1px solid #334155; background: #0f172a; color: #fff; border-radius: 8px; margin-bottom: 15px; font-size: 14px; box-sizing: border-box; }
        button { background: #0284c7; color: white; border: none; padding: 12px 20px; border-radius: 8px; font-size: 16px; cursor: pointer; width: 100%; font-weight: bold; transition: background 0.2s; }
        button:hover { background: #0369a1; }
        .vip-box { margin-top: 25px; background: #334155; padding: 15px; border-radius: 8px; text-align: left; }
        .vip-box h3 { color: #fbbf24; margin: 0 0 10px 0; font-size: 15px; }
        .btn-vip { background: #d97706; margin-top: 10px; }
        .btn-vip:hover { background: #b45309; }
        .error { background: #7f1d1d; color: #fca5a5; padding: 10px; border-radius: 6px; margin-bottom: 15px; font-size: 14px; }
        .success { background: #065f46; color: #6ee7b7; padding: 15px; border-radius: 6px; margin-bottom: 15px; word-break: break-all; }
        .download-btn { display: inline-block; background: #10b981; color: white; padding: 12px 25px; border-radius: 8px; text-decoration: none; font-weight: bold; margin-top: 10px; }
        .download-btn:hover { background: #059669; }
        input[type="text"].code-input { width: 70%; display: inline-block; margin-right: 5px; }
        .btn-code { width: 28%; display: inline-block; background: #475569; }
        .btn-code:hover { background: #334155; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Baixador de Vídeos</h1>
        <p>Cole o link abaixo para extrair o vídeo instantaneamente.</p>
        
        {% if error %}
            <div class="error">{{ error }}</div>
        {% endif %}

        {% if direct_url %}
            <div class="success">
                <p>Mídia extraída com sucesso!</p>
                <a href="{{ direct_url }}" class="download-btn" target="_blank" download>Baixar Direto no Dispositivo</a>
                <br><br>
                <a href="/" style="color: #38bdf8; text-decoration: none;">Extrair outro</a>
            </div>
        {% else %}
            <form method="POST" action="/process">
                <input type="text" name="url" placeholder="Cole o link (YouTube, Xvideos, Insta, etc)..." required>
                <button type="submit">Extrair Link</button>
            </form>
        {% endif %}

        <div class="vip-box">
            <h3>Área VIP</h3>
            <p style="margin: 5px 0;"><b>{{ status_texto }}</b></p>
            <form method="POST" action="/activate-vip-code" style="margin-top: 10px;">
                <input type="text" name="vip_code" placeholder="Código VIP" class="code-input">
                <button type="submit" class="btn-code">Ativar</button>
            </form>
            <a href="/pay-mp"><button class="btn-vip">Assinar VIP (R$ 10,00)</button></a>
        </div>
    </div>
</body>
</html>
"""

@app.route("/")
def index():
    user_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    status, left = verificar_acesso_web(user_ip)
    
    if status == "vip":
        status_texto = f"VIP Ativo (Restam {left} hoje)"
    elif status == "free":
        status_texto = f"Plano Gratuito ({left} restante hoje)"
    else:
        status_texto = "Limite diário esgotado."

    return render_template_string(HTML_TEMPLATE, status_texto=status_texto, error=request.args.get('error'))

@app.route("/process", methods=["POST"])
def process_video():
    user_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    status, _ = verificar_acesso_web(user_ip)
    
    if status == "limit_exceeded":
        return redirect(url_for('index', error="Limite diário esgotado! Ative um código VIP ou assine."))

    url = request.form.get("url", "").strip()
    if not url:
        return redirect(url_for('index', error="Insira um link válido!"))

    try:
        # Bypass específico para TikTok caso necessário
        if "tiktok.com" in url:
            try:
                res = requests.post("https://www.tikwm.com/api/", data={"url": url}, timeout=10).json()
                if res.get("code") == 0:
                    url = res["data"]["play"]
            except:
                pass

        # Extração leve apenas de metadados e URL direta de streaming (Consumo de RAM zero)
        ydl_opts = {
            'format': 'best[height<=720]/best',
            'noplaylist': True,
            'nocheckcertificate': True,
            'geo_bypass': True,
            'extractor_args': {'generic': {'impersonate': True}},
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if 'url' in info:
                direct_url = info['url']
            elif 'requested_formats' in info:
                direct_url = info['requested_formats'][0]['url']
            else:
                # Tenta pegar do entries se for playlist/objeto composto
                formats = info.get('formats', [])
                if formats:
                    direct_url = formats[-1]['url']
                else:
                    raise Exception("Formato direto não encontrado.")

        registrar_uso_web(user_ip)
        return render_template_string(HTML_TEMPLATE, status_texto="Pronto", direct_url=direct_url)

    except Exception as e:
        return redirect(url_for('index', error=f"Erro ao extrair link: {str(e)}"))

@app.route("/pay-mp")
def pay_mp():
    user_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    init_point = criar_preferencia_mercado_pago(user_ip)
    if init_point:
        return redirect(init_point)
    return redirect(url_for('index', error="Erro ao gerar pagamento."))

@app.route("/vip-success")
def vip_success():
    user_ip = request.args.get('ip')
    if user_ip:
        expires = datetime.datetime.utcnow() + datetime.timedelta(days=7)
        subs_col.update_one(
            {"user_ip": user_ip},
            {"$set": {"expires_at": expires, "downloads_limit": 20}},
            upsert=True
        )
    return redirect(url_for('index'))

@app.route("/activate-vip-code", methods=["POST"])
def activate_vip_code():
    code = request.form.get("vip_code", "").strip()
    user_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    
    if VIP_SECRET_CODE and code == VIP_SECRET_CODE:
        expires = datetime.datetime.utcnow() + datetime.timedelta(days=7)
        subs_col.update_one(
            {"user_ip": user_ip},
            {"$set": {"expires_at": expires, "downloads_limit": 20}},
            upsert=True
        )
        return redirect(url_for('index'))
    else:
        return redirect(url_for('index', error="Código VIP inválido!"))

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
