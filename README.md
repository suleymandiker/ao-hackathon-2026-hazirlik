# achillies-sre-ai (achillies)

> **Özet:** Vertex AI Gemini 2.5 Flash entegrasyonu ile log akışlarını %100 sıfır kayıpla indirgeyen ve kök neden analizi yapan otonom AI platformu.

## 🎯 Çözülen Problem
Kurumsal altyapılarda oluşan karmaşık, çoklu satırlı log akışlarını manuel inceleme zorluğunu ve yüksek LLM token maliyetlerini ortadan kaldırmaktır.

## 💡 Çözümümüz Nasıl Çalışır?
Çözümümüz deterministik Python kontrol motoru ile yapay zekayı hibrit olarak çalıştırır:
1. **Log Normalleştirme:** Saf metin geometrisiyle çoklu satırlar tekil olaylara dönüştürülür.
2. **Otonom İyileştirme (Self-Healing):** AI Regex hipotezleri deterministik doğrulama motoruyla %100 eşleşene kadar test edilir.
3. **Şablonlama & XAI:** Gürültü sıkıştırılır ve Gemini 2.5 Flash ile kök neden analizi raporlanır.

## 🛠️ Kurulum Adımları
```bash
git clone <repo-url>
cd <repo-folder>
pip install -r requirements.txt
```

## 🚀 Çalıştırma Komutu
```bash
python3 scripts/agentic_vertex_async.py --input src/1_data_loader/examples/heterogeneous_karmasik_test.log
python3 scripts/agentic_drain3_autotuner.py --input src/1_data_loader/examples/normalized_heterogeneous_karmasik_test.log
```

## 🤖 Kullanılan AI Araçları ve Model Sürümleri
- **Platform:** SAKA
- **AI Modelleri:** Vertex AI Gemini 2.5 Flash (Sürüm: 2026-v1), Claude 3.5 Sonnet
- **Kullanım Amacı:** Kod geliştirme, Regex üretimi, şablon sadakat analizi ve XAI raporlama.

## 🔌 MCP Sunucu Listesi
- **MCP Sunucuları:** Kullanılmadı / Yok (Tüm işlemler doğrudan API entegrasyonu ile yürütülmektedir).

## 🔗 Entegre Edilen API'ler
- GCP Vertex AI API
- SAKA LLM Gateway API

## 📸 Ekran Görüntüleri
1. **X-Factor (Ana Çıktı / Sihir Anı):** `demo/screenshot-01.png` - *Otonom self-healing ve XAI kök neden analiz ekranı*
2. **Ana Akış / Arayüz:** `demo/screenshot-02.png` - *Log yükleme ve özet kontrol paneli*

## 🌐 Deploy URL ve Bilinen Sınırlar
- **Deploy URL:** *(Opsiyonel - Uygulama yerel CLI üzerinden koşturulmaktadır)*
- **Bilinen Sınırlar:** Vertex AI API erişimi için GCP Application Default Credentials (ADC) yapılandırması gerektirir.