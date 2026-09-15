import logging

logger = logging.getLogger("ScoringEngine")

class ScoringEngine:
    def __init__(self, threshold=50):
        """
        Risk Puanlama Motoru.
        threshold: Bu puanın altındaki loglar 'gürültü' kabul edilir ve iletilmez.
        """
        self.threshold = threshold

        # 1. Severity (Hata Seviyesi) Puan Tablosu
        self.severity_scores = {
            "INFO": 10,
            "DEBUG": 0,
            "NOTICE": 20,
            "WARNING": 30,
            "ERROR": 50,       
            "CRITICAL": 80,
            "ALERT": 90,
            "EMERGENCY": 100
        }

    def calculate_score(self, event):
        """Sinyal metriklerine bakarak toplam risk skorunu (0-100) hesaplar."""
        
        # --- A) SEVERITY SCORE ---
        severity = event.get("severity", "INFO").upper()
        severity_score = self.severity_scores.get(severity, 10)

        # --- B) VELOCITY SCORE (Hız/Yoğunluk) ---
        # Üretim (Prod) ortamındaki log akış hızına göre eşikler yükseltildi
        window_count = event.get("window_count_1m", 1)
        raw_velocity = 0
        
        if window_count >= 500:
            raw_velocity = 50  # Çok ciddi ve sürekli yoğunluk
        elif window_count >= 100:
            raw_velocity = 30  # Belirgin artış
        elif window_count >= 25:
            raw_velocity = 15  # Ufak kıpırdanma
        else:
            raw_velocity = 0   # Normal akış

        # ZEKİ DOKUNUŞ: INFO logları yoğun gelse bile ERROR kadar puan almamalı!
        # Velocity puanını Severity seviyesine göre ağırlıklandırıyoruz.
        if severity in ["DEBUG", "INFO"]:
            velocity_score = int(raw_velocity * 0.2)  # %20 etki. Max 10 puan alır. (10 + 10 = 20 < 50 barajı)
        elif severity in ["NOTICE", "WARNING"]:
            velocity_score = int(raw_velocity * 0.6)  # %60 etki. Max 30 puan alır. (30 + 30 = 60 > 50 barajı)
        else:
            velocity_score = raw_velocity             # ERROR ve üstü %100 tam etki alır.

        # --- C) SMART METRICS PENALTIES (Zeka Cezaları) ---
        metadata = event.get("metadata", {})
        entropy = metadata.get("entropy", 0)
        confidence = metadata.get("confidence", 1.0)
        
        entropy_penalty = 0
        confidence_penalty = 0

        # Entropi 6.0'ın üzerindeyse mesaj içeriği çok karmaşık/bozuk demektir
        if entropy > 6.0:
            entropy_penalty = 20
        
        # Güven skoru 0.4'ün altındaysa sistem bu şablonu tam çözememiş demektir
        if confidence < 0.4:
            confidence_penalty = 15

# --- D) TOPLAM HESAPLAMA ---
        total_score = severity_score + velocity_score + entropy_penalty + confidence_penalty
        
        # --- KRİTİK GÜNCELLEME: ERROR FAST PASS ---
        # Eğer log ERROR veya üzeriyse, diğer puanlara bakmaksızın 
        # direkt threshold üstü (is_actionable = True) yapalım.
        if severity in ["ERROR", "CRITICAL", "ALERT", "EMERGENCY"]:
            is_actionable = True
            final_risk_score = max(self.threshold, min(100, total_score))
        else:
            final_risk_score = min(100, total_score)
            is_actionable = final_risk_score >= self.threshold
        
        # ERROR ve üzeri için yukarıdaki fast-pass sonucu korunur; diğer severity
        # seviyelerinde threshold uygulanır.
        return {
            "total_risk_score": final_risk_score,
            "is_actionable": is_actionable,
            "details": {
                "severity_score": severity_score,
                "velocity_score": velocity_score,     # Artık INFO logları için törpülenmiş hali görünecek
                "entropy_penalty": entropy_penalty,
                "confidence_penalty": confidence_penalty
            }
        }