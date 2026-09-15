import re
from parser_layer.timestamp.timestamp_normalizer import TimestampNormalizer

class StructuredTextParser:
    def __init__(self):
        self.ts = TimestampNormalizer()
        
        # 1. Nginx / Apache Access Log Formatı (Common Log Format)
        self.nginx_regex = re.compile(r'^(\S+)\s+\S+\s+\S+\s+\[([^\]]+)\]\s+"(.*?)"\s+(\d{3})\s+(\d+)')
        
        # 2. Standart Köşeli Parantezli Log Formatı [Time] [Severity] Message
        self.generic_regex = re.compile(r'^\[?([\d\-\:\sT\.Z]+)\]?\s*(?:\[(ERROR|WARN|WARNING|INFO|DEBUG|CRITICAL|FATAL)\])?\s*(.*)', re.I)

    def parse(self, log):
        # ÖNLEM 2 ve 4: Çok satırlı yapıları ve gizli boşluk/satır sonlarını temizle
        log = log.strip().replace('\n', ' ').replace('\r', '')

        # Önce Nginx/Apache formatı mı diye kontrol et
        match = self.nginx_regex.match(log)
        if match:
            ip, timestamp_raw, request, status, size = match.groups()
            status_code = int(status)
            size_bytes = int(size) if size.isdigit() else 0 # Veri tipi tutarlılığı
            
            # HTTP Status kodunu Severity'ye çevir
            if status_code >= 500:
                severity = "ERROR"
            elif status_code >= 400:
                severity = "WARNING"
            else:
                severity = "INFO"

            return {
                "timestamp": self.ts.normalize(timestamp_raw),
                "severity": severity,
                # Mesajı daha sade tutup, ekstra bilgileri attributes içine alıyoruz
                "message": f"{request.strip()} (HTTP {status_code})",
                "host": ip,
                # ÖNLEM 5: Ekstra detayları mapping explosion riski olmadan sakla
                "attributes": {
                    "http_status_code": status_code,
                    "response_size_bytes": size_bytes
                }
            }

        # Nginx değilse, genel köşeli parantez formatını dene
        match = self.generic_regex.match(log)
        if match:
            raw_ts, severity, message = match.groups()
            if not raw_ts: 
                return None
                
            return {
                "timestamp": self.ts.normalize(raw_ts.strip("[] ")) if raw_ts else None,
                "severity": (severity or "INFO").upper(),
                "message": message.strip() if message else log,
                 # Orijinal metni veya bulunabilen extra veriyi (opsiyonel olarak) buraya koyabiliriz
                "attributes": {}
            }
            
        return None