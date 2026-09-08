import requests
import json

# API Bilgileri
QWEN_URL = "https://common-inference-apis.turkcelltech.ai/qwen35-122b-a10b-awq-teknocan/v1/chat/completions"
QWEN_KEY = "Yln2FFEa7AsL1yl2UgM5GSiFlZRIBSe3hW5x+D71Te4="

def analyze_logs_with_qwen(logs_text):
    """
    Qwen modelini kullanarak log analizi yapan AI fonksiyonu.
    (AI & Prompt Mühendisinin odaklanacağı alan)
    """
    headers = {
        "Authorization": f"Bearer {QWEN_KEY}",
        "Content-Type": "application/json"
    }
    
    # Prompt Mühendisliği: Modelin SRE uzmanı gibi davranmasını sağlıyoruz
    system_prompt = "Sen uzman bir Site Güvenilirliği Mühendisisin (SRE). Sana verilen sistem loglarını analiz et. 1) Kök nedeni (Root Cause) tek cümleyle yaz. 2) Çözüm önerisini madde madde belirt."
    
    payload = {
        "model": "teknocan__qwen35-122b-a10b-awq-teknocan",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Şu logları analiz et:\n{logs_text}"}
        ],
        "stream": False # Hackathon'da CLI için şimdilik False yapıyoruz, tek seferde yanıt dönecek.
    }
    
    try:
        # cURL'deki -k parametresi verify=False'a karşılık gelir
        response = requests.post(QWEN_URL, headers=headers, json=payload, verify=False)
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content']
        else:
            return f"API Hatası: {response.status_code} - {response.text}"
    except Exception as e:
        return f"Bağlantı Hatası: {str(e)}\nNot: Turkcell ağına/VPN'ine bağlı olduğunuzdan emin olun."