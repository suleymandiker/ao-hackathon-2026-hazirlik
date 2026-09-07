import os
import requests
import json

# Gerçek projede .env dosyasından okunmalıdır (asla buraya yazılmaz!)
API_KEY = "UIgw1qmU98AHAAzzDkDvuTw9p50cdrt1IU0AwCD49Tw=" # İlk maildeki test key
API_URL = "https://common-inference-apis.test-turkcelltech.ai/glm-52-fp8/v1/chat/completions"

def analiz_yap(veri):
    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    # prompts klasöründeki mantığı koda döküyoruz
    payload = {
        "messages": [
            {"role": "system", "content": "Sen yardımcı bir veri analistisin."},
            {"role": "user", "content": f"Şu veriyi 2 cümle ile özetle: {veri}"}
        ],
        "model": "glm-52-fp8",
        "stream": False,
        "temperature": 0.2
    }
    
    try:
        # Hackathon ortamı olmadığı için API hata verebilir, try-except ile koruyoruz
        response = requests.post(API_URL, headers=headers, json=payload, verify=False)
        if response.status_code == 200:
            print("\n[AI Analizi]:", response.json()['choices'][0]['message']['content'])
        else:
            print(f"API Hatası: {response.status_code}. Mock veri döndürülüyor...")
            print("[AI Analizi]: Verideki CPU kullanımları normal seviyededir.")
    except Exception as e:
        print("Bağlantı kurulamadı. (Hackathon networkünde olmanız gerekebilir)")

if __name__ == "__main__":
    print("AI-Ops Veri Analiz Aracı Başlıyor...")
    # Sentetik test verisi
    test_verisi = "[{'sunucu': 'app-1', 'cpu': %85}, {'sunucu': 'app-2', 'cpu': %20}]"
    analiz_yap(test_verisi)