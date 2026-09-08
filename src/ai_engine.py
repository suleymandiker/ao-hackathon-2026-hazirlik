import requests
import json
import os
from datetime import datetime

# API Bilgileri
QWEN_URL = "https://common-inference-apis.turkcelltech.ai/qwen35-122b-a10b-awq-teknocan/v1/chat/completions"
QWEN_KEY = "Yln2FFEa7AsL1yl2UgM5GSiFlZRIBSe3hW5x+D71Te4="

def log_conversation(prompt_data, ai_response):
    """
    Hackathon Zorunlu Kuralı: AI ile olan etkileşimi conv.history.md dosyasına kaydeder.
    """
    # Ana dizindeki conv.history.md dosyasının yolunu buluyoruz
    log_file_path = os.path.join(os.path.dirname(__file__), '..', 'conv.history.md')
    zaman = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Markdown formatında içeriği hazırlıyoruz
    md_icerik = f"## 🕒 Tarih: {zaman}\n\n"
    md_icerik += f"### 👤 Gönderilen Log Verisi:\n```json\n{prompt_data}\n```\n\n"
    md_icerik += f"### 🤖 SAKA (Qwen35-122b) Yanıtı:\n{ai_response}\n\n"
    md_icerik += "---\n\n" # Her sorguyu bir çizgi ile ayırıyoruz
    
    # Dosyaya 'a' (append/ekleme) modunda yazıyoruz ki eski kayıtlar silinmesin
    with open(log_file_path, 'a', encoding='utf-8') as f:
        f.write(md_icerik)

def analyze_logs_with_qwen(logs_text):
    """
    Qwen modelini kullanarak log analizi yapan AI fonksiyonu.
    """
    headers = {
        "Authorization": f"Bearer {QWEN_KEY}",
        "Content-Type": "application/json"
    }
    
    system_prompt = "Sen uzman bir Site Güvenilirliği Mühendisisin (SRE). Sana verilen sistem loglarını analiz et. 1) Kök nedeni (Root Cause) tek cümleyle yaz. 2) Çözüm önerisini madde madde belirt."
    
    payload = {
        "model": "teknocan__qwen35-122b-a10b-awq-teknocan",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Şu logları analiz et:\n{logs_text}"}
        ],
        "stream": False 
    }
    
    try:
        response = requests.post(QWEN_URL, headers=headers, json=payload, verify=False)
        if response.status_code == 200:
            ai_reply = response.json()['choices'][0]['message']['content']
            
            # --- YENİ EKLENEN KISIM: Yanıtı dönmeden önce dosyaya kaydet ---
            log_conversation(logs_text, ai_reply)
            
            return ai_reply
        else:
            return f"API Hatası: {response.status_code} - {response.text}"
    except Exception as e:
        return f"Bağlantı Hatası: {str(e)}"