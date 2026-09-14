import json
import os
import argparse
from ai_engine import call_ai_agent, load_prompt, MODELS_CONFIG

def read_and_filter_data(file_path):
    print(f"[SİSTEM] {file_path} dosyasından loglar okunuyor ve ön filtreleme yapılıyor...")
    filtered_logs = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            all_logs = json.load(f)
            for log in all_logs:
                if log.get("level") in ["ERROR", "FATAL", "WARNING", "CRITICAL", "TIMEOUT"]:
                    filtered_logs.append(log)
        return json.dumps(filtered_logs, indent=2)
    except Exception as e:
        print(f"[HATA] Log dosyası okunamadı: {e}")
        return None

def run_cli():
    parser = argparse.ArgumentParser(description="🚀 Sinyal Sprint: Multi-Agent SRE Oto-Analiz Aracı")
    parser.add_argument(
        "-m", "--rca-model", 
        type=str, 
        choices=["Ajan_2_RCA_AgirTop", "Ajan_2_RCA_Hizli", "Claude-3"], 
        default="Ajan_2_RCA_AgirTop", 
        help="Kök Neden Analizi (RCA) için kullanılacak 2. Ajanı seçin."
    )
    
    args = parser.parse_args()
    secilen_rca_modeli = args.rca_model

    print("="*60)
    print("🚀 SİNYAL SPRINT: MULTI-AGENT SRE OTO-ANALİZ BAŞLIYOR 🚀")
    print("="*60)
    
    log_file_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'logs.json')
    pre_filtered_logs = read_and_filter_data(log_file_path)
    
    if not pre_filtered_logs:
        return

    print("\n[AJAN 1] DeepSeek-v4 Flash devreye giriyor. Loglar filtreleniyor...")
    sys_prompt_1 = load_prompt("ajan1_triyaj.md")
     
    filtered_logs, duration_1 = call_ai_agent("Ajan_1_Triyaj", sys_prompt_1, pre_filtered_logs)
    print(f"✅ Triyaj Tamamlandı (Süre: {duration_1:.2f} sn)\n")
    
    print(f"[AJAN 2] {MODELS_CONFIG[secilen_rca_modeli]['model_id']} devreye giriyor. Kök Neden Analizi (RCA) yapılıyor...")
    sys_prompt_2 = load_prompt("ajan2_rca.md")
    
    rca_report, duration_2 = call_ai_agent(secilen_rca_modeli, sys_prompt_2, filtered_logs)
    
    if "Hatası" in rca_report:
        print(f"\n❌ İşlem Başarısız: {rca_report}")
        return
        
    print(f"✅ SRE Analizi Tamamlandı (Süre: {duration_2:.2f} sn)\n")
    print("="*60)
    print(f"📊 NİHAİ SRE RAPORU (Toplam AI Süresi: {duration_1 + duration_2:.2f} sn) 📊")
    print("="*60)
    print(rca_report)
    print("="*60)

if __name__ == "__main__":
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    run_cli()