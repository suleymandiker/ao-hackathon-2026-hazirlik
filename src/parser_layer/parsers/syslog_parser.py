import re
from parser_layer.timestamp.timestamp_normalizer import TimestampNormalizer

class SyslogParser:
    def __init__(self):
        self.ts = TimestampNormalizer()
        
        # Daha önce düzelttiğimiz esnek (re.search uyumlu) regex'ler:
        # 1. RFC 5424 (Modern Syslog - <PRI> ile başlar)
        self.rfc5424_regex = re.compile(r'<(\d+)>v?\d?\s+([\d\-T:\.Z\+]+)\s+(\S+)\s+(\S+)\s+(.*)')
        
        # 2. RFC 3164 (Geleneksel Linux Syslog)
        self.rfc3164_regex = re.compile(r'(?:<(\d+)>)?\s*([A-Z][a-z]{2}\s+\d+\s+\d{2}:\d{2}:\d{2})\s+(\S+)\s+([^:]+):\s+(.*)')

    def parse(self, log):
        # ÖNLEM 2 ve 4: Çok satırlı Kernel/OS hatalarını ve gizli boşlukları tek satıra indirge
        log = log.strip().replace('\n', ' ').replace('\r', '')

        # RFC 5424 Kontrolü
        match = self.rfc5424_regex.search(log)
        if match:
            priority = int(match.group(1)) # ÖNLEM 1: Priority zaten int olarak alınıyor
            severity_code = priority % 8
            timestamp_raw = match.group(2)
            host = match.group(3)
            app_name = match.group(4)
            message_part = match.group(5)
            return self._build_payload(timestamp_raw, severity_code, message_part, host, app_name, priority)

        # RFC 3164 Kontrolü
        match = self.rfc3164_regex.search(log)
        if match:
            priority_str = match.group(1)
            severity_code = int(priority_str) % 8 if priority_str else 6 
            priority_val = int(priority_str) if priority_str else None
            
            timestamp_raw = match.group(2)
            host = match.group(3)
            app_name = match.group(4)
            message_part = match.group(5)
            return self._build_payload(timestamp_raw, severity_code, message_part, host, app_name, priority_val)

        return None

    def _build_payload(self, timestamp_raw, severity_code, message_part, host, app_name, priority_val):
        return {
            # ÖNLEM 3: Normalizer her şeyi UTC'ye sabitler
            "timestamp": self.ts.normalize(timestamp_raw) if timestamp_raw else None,
            "severity": self._map_severity(severity_code),
            "message": f"{app_name.strip()}: {message_part.strip()}",
            "host": host.strip() if host else None,
            
            # ÖNLEM 5: Syslog'a özel dinamik ve detaylı verileri güvenli attributes altına göm
            "attributes": {
                "syslog_app_name": app_name.strip() if app_name else "unknown",
                "syslog_priority": priority_val
            }
        }

    def _map_severity(self, code):
        mapping = {0:"EMERGENCY", 1:"ALERT", 2:"CRITICAL", 3:"ERROR", 4:"WARNING", 5:"NOTICE", 6:"INFO", 7:"DEBUG"}
        return mapping.get(code, "INFO")