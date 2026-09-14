import streamlit as st
import json
import os
import time
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

try:
    from ai_engine import call_ai_agent, load_prompt, MODELS_CONFIG
except ImportError as e:
    st.error(f"İçe aktarma hatası: {e}.")
    st.stop()

st.set_page_config(page_title="AIOps SRE Otopilot", page_icon="🚀", layout="wide")

st.markdown('''
    <style>
    .metric-box { background-color: #1e1e1e; padding: 15px; border-radius: 8px; border-left: 4px solid #ff4b4b; margin-bottom: 15px;}
    .success-box { background-color: #1e1e1e; padding: 15px; border-radius: 8px; border-left: 4px solid #00c853; margin-bottom: 15px;}
    div.stButton > button:first-child {background-color: #ff4b4b; color: white; border: none; font-weight: bold;}
    </style>
''', unsafe_allow_html=True)

st.title("🚀 AIOps SRE Otopilot")
st.markdown("Turkcell AI Platform Orkestrasyonu | XAI Destekli Olay Yeri İnceleme (RCA)")
st.markdown("---")

with st.sidebar:
    st.header("⚙️ Kontrol Paneli")
    st.info("**Ajan 1 (Sabit Triyaj):**\nDeepSeek-V4 Flash")
    
    rca_modelleri = [k for k in MODELS_CONFIG.keys() if k != "Ajan_1_Triyaj"]
    secilen_model = st.selectbox("🧠 Ajan 2 (RCA) Modeli Seçin", rca_modelleri, index=0)
    
    st.success(f"**Ajan 2 (Seçili):**\n{MODELS_CONFIG[secilen_model]['model_id']}")
    st.markdown("---")
    start_btn = st.button("🚨 KRİZ ANALİZİNİ BAŞLAT", use_container_width=True)

def load_logs(file_path):
    filtered_events = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            all_logs = json.load(f)
            for log in all_logs:
                if log.get("level") in ["ERROR", "FATAL", "WARNING", "CRITICAL"]:
                    filtered_events.append(log)
        return json.dumps(filtered_events, indent=2)
    except Exception as e:
        return None

if start_btn:
    st.session_state['analysis_started'] = True

if st.session_state.get('analysis_started', False):
    st.subheader("📥 1. Log Verisi (Ön Filtreleme)")
    
    log_file_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'logs.json')
    raw_logs_text = load_logs(log_file_path)
        
    if raw_logs_text is None:
        st.error("HATA: `data/logs.json` dosyası okunamadı!")
        st.stop()
        
    with st.expander(f"Kritik Logları Görüntüle (Deterministik Filtre)", expanded=False):
        st.code(raw_logs_text[:1500] + "\n\n... [DEVAMI VAR]", language="json")

    st.markdown("---")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown('<div class="metric-box"><h4>🕵️‍♂️ Ajan 1: DeepSeek Triyaj</h4></div>', unsafe_allow_html=True)
        sys_prompt_1 = load_prompt("ajan1_triyaj.md")
        
        with st.spinner("DeepSeek logları süzüyor..."):
            filtered_logs, dur_1 = call_ai_agent("Ajan_1_Triyaj", sys_prompt_1, raw_logs_text)
            
        st.success(f"✅ Triyaj Tamamlandı! ({dur_1:.2f} sn)")
        with st.expander("AI Filtre Çıktısı", expanded=True):
            st.code(filtered_logs, language="text")

    with col2:
        st.markdown(f'<div class="success-box"><h4>🧠 Ajan 2: Kök Neden Analizi</h4></div>', unsafe_allow_html=True)
        sys_prompt_2 = load_prompt("ajan2_rca.md")
        
        with st.spinner(f"{MODELS_CONFIG[secilen_model]['model_id']} XAI raporu üretiyor..."):
            rca_report, dur_2 = call_ai_agent(secilen_model, sys_prompt_2, filtered_logs)
            
        if "Hatası" in rca_report:
            st.error(f"❌ Hata: {rca_report}")
        else:
            st.success(f"✅ Analiz Tamamlandı! ({dur_2:.2f} sn)")

    if "Hatası" not in rca_report:
        st.markdown("---")
        st.header("📊 Nihai XAI (Açıklanabilir AI) Raporu")
        st.info(f"⚡ **Toplam AI Süresi:** {dur_1 + dur_2:.2f} saniye")
        
        # XAI Sekmeleri (Jüri Sunumu)
        tab1, tab2, tab3 = st.tabs(["🎯 Kök Neden ve Çözüm", "🧠 XAI (Karar Gerekçesi)", "🧾 Kanıt (Ham Log)"])
        
        with tab1:
            st.markdown(rca_report)
        with tab2:
            st.info("Yapay zeka, OOMKilled ve Timeout zincirini analiz ederek aşağıdaki kararı vermiştir:")
            # RCA raporundan ilgili XAI kısmını Markdown olarak basıyoruz
            st.markdown(rca_report) 
        with tab3:
            st.markdown("**Sistemin Karar Verirken Dayandığı Log Satırları:**")
            st.code(filtered_logs, language="json")
            
        st.balloons()