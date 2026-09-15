import re
from parser_layer.timestamp.timestamp_normalizer import TimestampNormalizer

class PlainTextParser:
    def __init__(self):
        self.ts = TimestampNormalizer()
        # Logun en başındaki tarihi yakalamak için genel bir regex
        self.date_pattern = re.compile(r'^([\d\-\:\sT\.Z\/]+)\s*\[?')

    def parse(self, log):
        # ÖNLEM 2 ve 4: Gizli karakterleri ve alt satırları (Stacktrace vb.) tek satıra indirge
        log = log.strip().replace('\n', ' ').replace('\r', '')
        
        # 1. Zaman Damgasını (Timestamp) Yakala (ÖNLEM 3)
        date_match = self.date_pattern.search(log)
        raw_time = date_match.group(1).strip() if date_match else None

        # 2. Seviyeyi (Severity) Yakala (Testinizdeki FATAL ve yaygın WARNING de eklendi)
        sev_match = re.search(r'\[(ERROR|WARN|WARNING|INFO|DEBUG|CRITICAL|FATAL)\]', log, re.I)
        severity = sev_match.group(1).upper() if sev_match else "INFO"
        
        # 3. Mesajı Temizle
        message = log.split(' - ')[-1] if ' - ' in log else log
        
        return {
            # Artık None yerine, logun başındaki tarihi UTC'ye çevirip veriyoruz
            "timestamp": self.ts.normalize(raw_time) if raw_time else None,
            "severity": severity.strip(),
            "message": message.strip()
        }