import json
import os
from ai_engine import analyze_logs_with_qwen

def read_data(file_path):
    """Backend Rolü: Veriyi dosyadan okur."""
    print(f"[SİSTEM] {file_path} dosyasından loglar okunuyor...")
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def run_cli():
    """Frontend/CLI Rolü: Uygulama akışını yönetir ve ekrana basar."""
    print("="*50)
    print("🚀 AIOps SRE OTO-ANALİZ ARACI 🚀")
    print("="*50)
    
    # 1. Veriyi Oku (Backend)
    # Ana dizinden çalıştırılacağını varsayarak yolu veriyoruz
    log_file_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'logs.json')
    
    try:
        logs_data = read_data(log_file_path)
    except Exception as e:
        print(f"[HATA] Log dosyası okunamadı: {e}")
        return

    # Veriyi string'e çevir
    logs_text = json.dumps(logs_data, indent=2)
    
    print("[SİSTEM] Kriz tespit edildi! Loglar SAKA (Qwen35-122b) modeline gönderiliyor...\n")
    
    # 2. AI Analizi (AI Engineer)
    ai_response = analyze_logs_with_qwen(logs_text)
    
    # 3. Sonuçları Göster (Frontend)
    print("🤖 AI JÜRİ VE SİSTEM YANITI 🤖")
    print("-" * 50)
    print(ai_response)
    print("-" * 50)
    print("✅ Analiz tamamlandı.")

if __name__ == "__main__":
    # Konsolda uyarıları (SSL insecere request vs) gizlemek için
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    run_cli()