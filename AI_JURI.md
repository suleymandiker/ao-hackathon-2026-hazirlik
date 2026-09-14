# 🏆 AI Jüri Özeti - achillies

## 1. AI Stratejimiz ve İş Akışı
Log akışlarını analiz edip  kök neden analizi yapan otonom AI platformu.

**Son Git Commitleri:**
```
20da240 feat: AI konusma gecmisi icin conv.history.md otomatik loglama eklendi
206f0bd feat: E-ticaret SRE log analiz motoru ve Qwen35-122b AI entegrasyonu tamamlandi
64e6337 feat: iskelet yapi ve temel GLM-5.2 entegrasyonu eklendi
477d4ea Initial commit
```

- **Kanıt Dosyaları:** `prompts/`, `docs/plan.md`, `CLAUDE.md`

## 2. Problemi Nasıl Çözdük
- **Kanıt Dosyaları:** `src/`, `docs/mimari.md`, `demo/`

## 3. X-Factor Özelliklerimiz
### 🚀 X-Factor 1: Otonom AI Regex Bulucu ve Sıfır-Kayıp Normalleştirici
- Saf metin geometrisi ile çoklu satırları %100 sıfır kayıpla tekli satır olaylarına dönüştürür.
- **Kanıt:** `src/1_data_loader/vertex_normalizer.py:12-85`

### 🚀 X-Factor 2: Agentic Self-Healing Loop & Live Token Accounting
- Deterministik Python denetim motoru ile Regex hipotezlerini %100 kusursuz eşleşme sağlanana kadar otonom iyileştirir.
- **Kanıt:** `src/1_data_loader/main.py:40-110`

## 4. Çalıştırma
```bash
python3 scripts/agentic_vertex_async.py --input src/1_data_loader/examples/heterogeneous_karmasik_test.log
python3 scripts/agentic_drain3_autotuner.py --input src/1_data_loader/examples/normalized_heterogeneous_karmasik_test.log
```

## 5. Bilinen Sınırlar
- ADC auth gereklidir.