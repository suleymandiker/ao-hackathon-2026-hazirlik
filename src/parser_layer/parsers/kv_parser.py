import re
# Zaman damgasını standartlaştırmak için Normalizer'ı ekliyoruz
from parser_layer.timestamp.timestamp_normalizer import TimestampNormalizer

class KVParser:
    def __init__(self):
        self.ts = TimestampNormalizer()
        # Key=Value eşleşmesi için daha güvenli regex (boşluklu value'ları yanlış bölmez)
        self.kv_pattern = re.compile(r'([a-zA-Z0-9_]+)=(".*?"|\S+)')

    def parse(self, log):
        # ÖNLEM 2 ve 4: Gizli karakterleri ve alt satırları temizle
        log = log.strip().replace('\n', ' ').replace('\r', '')
        
        fields = {}
        # 1. Standart KV Ayıklama
        matches = self.kv_pattern.findall(log)
        for k, v in matches:
            # ÖNLEM 2: Tırnak işaretlerini (" veya ') tamamen temizle ("ERROR" -> ERROR)
            clean_value = v.strip('"\'')
            
            # ÖNLEM 1: Veri Tipi Tutarsızlığı (Rakamları int veya float yap)
            if clean_value.isdigit():
                clean_value = int(clean_value)
            else:
                try:
                    clean_value = float(clean_value)
                except ValueError:
                    pass # String ise olduğu gibi bırak
            
            fields[k] = clean_value

        # 2. Standart Alanları Doldur (Pop kullanarak alınan veriyi fields sözlüğünden çıkarıyoruz)
        raw_time = fields.pop("timestamp", None) or fields.pop("time", None)
        
        # Severity fallback
        severity = fields.pop("level", None) or fields.pop("severity", None)
        if not severity:
            sev_match = re.search(r'\[(ERROR|WARN|INFO|DEBUG|CRITICAL|FATAL)\]', log, re.I)
            severity = sev_match.group(1) if sev_match else "INFO"

        # Message fallback
        message = fields.pop("msg", None) or fields.pop("message", None)
        if not message:
            message = log.split(' - ')[-1] if ' - ' in log else log

        return {
            # ÖNLEM 3: Zaman damgasını UTC / Timestamp formatına dönüştür
            "timestamp": self.ts.normalize(str(raw_time)) if raw_time else None,
            
            # Üst düzey temizlik: Tırnak veya boşluk kalmışsa sil ve BÜYÜK HARF yap
            "severity": str(severity).upper().strip('"\' '), 
            
            "message": str(message).strip('"\' '),
            
            # ÖNLEM 5: Mapping Explosion. Zaman, seviye ve mesaj haricindeki 
            # tüm dinamik verileri (port=443, dest_ip=10... gibi) bu objede güvenle sakla.
            "attributes": fields
        }