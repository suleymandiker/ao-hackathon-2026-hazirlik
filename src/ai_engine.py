import requests
import json
import os
import time
from datetime import datetime
from dotenv import load_dotenv

# .env dosyasındaki değişkenleri yükle
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
SAKA_API_KEY = os.getenv("SAKA_API_KEY", "")

MODELS_CONFIG = {
    "Ajan_1_Triyaj": {
        "provider": "saka", # local yerine saka yaptık
        "url": "https://common-inference-apis.turkcelltech.ai/llm-dynamo-deepseek-v4-flash-0731/v1/chat/completions",
        "key": SAKA_API_KEY,
        "model_id": "deepseek-v4-flash-0731"
    },
    "Ajan_2_RCA_AgirTop": {
        "provider": "saka", # local yerine saka yaptık
        "url": "https://common-inference-apis.turkcelltech.ai/qwen35-122b-a10b-awq-teknocan/v1/chat/completions",
        "key": SAKA_API_KEY,
        "model_id": "teknocan__qwen35-122b-a10b-awq-teknocan"
    },
    "Ajan_2_RCA_Hizli": {
        "provider": "openai",
        "url": "https://api.openai.com/v1/chat/completions",
        "key": OPENAI_API_KEY,
        "model_id": "gpt-4o-mini" 
    },
    "Claude-3": {
        "provider": "anthropic",
        "url": "https://api.anthropic.com/v1/messages",
        "key": ANTHROPIC_API_KEY,
        "model_id": "claude-3-haiku-20240307"
    }
}

def load_prompt(prompt_filename):
    """prompts klasöründeki belirtilen dosyayı okur."""
    prompt_path = os.path.join(os.path.dirname(__file__), '..', 'prompts', prompt_filename)
    try:
        with open(prompt_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"[HATA] Prompt dosyası okunamadı: {prompt_filename}"

def log_conversation(agent_role, model_name, prompt_data, ai_response, duration):
    """Etkileşimleri model adı ve süresiyle birlikte loglar."""
    log_file_path = os.path.join(os.path.dirname(__file__), '..', 'conv.history.md')
    zaman = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    md_icerik = f"## 🕒 Tarih: {zaman} | Görev: {agent_role} | Model: {model_name} | Süre: {duration:.2f} sn\n\n"
    md_icerik += f"### 📥 Girdi (Input):\n```text\n{prompt_data}\n```\n\n"
    md_icerik += f"### 📤 Çıktı (Output):\n{ai_response}\n\n---\n\n"
    
    with open(log_file_path, 'a', encoding='utf-8') as f:
        f.write(md_icerik)

def call_ai_agent(agent_key, system_prompt, user_content):
    """İstenen modele göre doğru API formatını hazırlayıp analizi çalıştırır."""
    config = MODELS_CONFIG.get(agent_key)
    if not config:
        return f"Hata: {agent_key} konfigürasyonu bulunamadı.", 0

    # 'saka' ve 'openai' sağlayıcıları aynı header yapısını kullanır
    if config["provider"] in ["saka", "openai"]:
        headers = {
            "Authorization": f"Bearer {config['key']}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": config["model_id"],
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            "temperature": 0.1 
        }
    elif config["provider"] == "anthropic":
        headers = {
            "x-api-key": config["key"],
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        payload = {
            "model": config["model_id"],
            "max_tokens": 1024,
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": user_content}
            ],
            "temperature": 0.1
        }

    start_time = time.time()
    try:
        response = requests.post(config["url"], headers=headers, json=payload, verify=False, timeout=300)
        duration = time.time() - start_time
        
        if response.status_code == 200:
            if config["provider"] == "anthropic":
                ai_reply = response.json()['content'][0]['text']
            else:
                ai_reply = response.json()['choices'][0]['message']['content']
            
            log_conversation(agent_key, config["model_id"], user_content, ai_reply, duration)
            return ai_reply, duration
        else:
            # Hata detayını daha net görebilmemiz için log ekliyoruz
            error_msg = f"API Hatası ({response.status_code}): {response.text}"
            print(f"[DEBUG] {error_msg}") 
            return error_msg, duration
    except Exception as e:
        duration = time.time() - start_time
        return f"Bağlantı Hatası: {str(e)}", duration