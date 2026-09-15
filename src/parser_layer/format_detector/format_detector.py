import json
import re

class FormatDetector:
    def __init__(self):
        # 1. Geleneksel Syslog RFC 3164 (Örn: Mar 17 18:47:33)
        self.syslog_rfc3164_pattern = re.compile(r'^(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d+\s+\d{2}:\d{2}:\d{2}')
        
        # 2. Nginx / Apache Access Log formatı (Örn: 10.220.13.38 - - [17/Mar/2026...)
        self.nginx_pattern = re.compile(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\s+\S+\s+\S+\s+\[')
        
        # 3. Standart ISO/Python/Java Uygulama Logları (Örn: 2026-04-05 11:51:20,498 veya 2026-04-05T11:51:20.491Z)
        self.app_log_iso_pattern = re.compile(r'^\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}')
        
        # 4. US Tarihli Uygulama Logları (Örn: 04/05/2026 11:51:20.457)
        self.app_log_us_pattern = re.compile(r'^\d{2}/\d{2}/\d{4}\s\d{2}:\d{2}:\d{2}')
        
        # 5. Kubernetes klog/glog formatı (Örn: I0405 12:27:01.474459 1 main.go:277])
        self.klog_pattern = re.compile(r'^[IWEF]\d{4}\s\d{2}:\d{2}:\d{2}\.\d+')

        # 6. YENİ: Standart Python/vLLM Log Formatı (Örn: INFO 04-05 05:27:21 [loggers.py:111])
        self.vllm_pattern = re.compile(r'^(?:INFO|ERROR|WARN|WARNING|DEBUG|TRACE|FATAL|CRITICAL)\s+\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\s+\[')

    def detect(self, log):
        log = log.strip()

        if not log:
            return None

        # 1. JSON Kontrolü
        if log.startswith("{") and self._is_json(log):
            return "json"

        # 2. Syslog Kontrolü: Ya < ile başlar (RFC5424) ya da Standart Tarih formatıyla (RFC3164)
        if log.startswith("<") or self.syslog_rfc3164_pattern.match(log):
            return "syslog"

        # 3. Structured Text Kontrolü: Tanımlı tüm yapısal desenleri kontrol et
        if (log.startswith("[") or 
            "|" in log or 
            self.nginx_pattern.match(log) or 
            self.app_log_iso_pattern.match(log) or 
            self.app_log_us_pattern.match(log) or
            self.klog_pattern.match(log) or
            self.vllm_pattern.match(log)):
            return "structured_text"

        # 4. KV (Key-Value) Kontrolü
        if "=" in log and " " in log and not log.startswith("{"):
            return "kv"

        # 5. Hiçbirine uymazsa düz metin (TypeError, NoneType vb.)
        return "plain_text"

    def _is_json(self, log):
        try:
            json.loads(log)
            return True
        except ValueError:
            return False