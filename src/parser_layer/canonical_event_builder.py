# -*- coding: utf-8 -*-
import time
import xxhash
import re

class CanonicalEventBuilder:
    def __init__(self):
        # 1. HIZ OPTİMİZASYONU: Regex'i sadece bir kez derliyoruz.
        self.severity_pattern = re.compile(r'\[(ERROR|WARN|CRITICAL|FATAL|DEBUG)\]', re.IGNORECASE)
        
        # 2. HIZ OPTİMİZASYONU: Aranacak kelimeleri tuple olarak önbelleğe alıyoruz.
        self.error_keywords = ("failed", "timeout", "exception", "error")
        
        # 3. KESİN BENZERSİZLİK (ÇAKIŞMA ÖNLEYİCİ): İşletim sistemini yormayan hızlı sayaç.
        self._counter = 0

    def build(self, fields, raw, source):
        # 1. ZAMAN DAMGASI (Ingest Time)
        ingest_time = time.time() * 1000 
        
        event_time = fields.get("timestamp")
        if event_time is None:
            event_time = ingest_time
        
        # 2. DINAMIK SEVERITY
        severity = str(fields.get("severity", "INFO")).upper()
        
        if severity == "INFO" and raw:
            # Önceden derlenmiş regex motorunu kullanıyoruz
            severity_match = self.severity_pattern.search(raw)
            if severity_match:
                severity = severity_match.group(1).upper()
            else:
                # Büyük metinler için .lower() işlemini döngü dışında SADECE 1 KEZ yapıyoruz.
                raw_lower = raw.lower()
                if any(word in raw_lower for word in self.error_keywords):
                    severity = "ERROR"
        
        # 3. MESAJ YÖNETIMI
        message = fields.get("message") or raw

        # 4. TRACEABILITY
        # Stable across replays of the same ordered input. The previous version
        # mixed ingest_time into the ID, which made every Streamlit rerun create
        # different incident/evidence IDs and therefore miss the AI response cache.
        event_id = self._generate_unique_event_id(raw, event_time, source)

        # --- YENİ: PARSER METADATA VE LATENCY ---
        now_ms = time.time() * 1000
        metadata = {
            "parser_at": now_ms,
            "latency_parser_ms": round(now_ms - ingest_time, 3)
        }

        return {
            "event_id": event_id,
            "evidence_ids": [],
            "ingest_time": ingest_time,
            "event_time": event_time,
            "severity": severity,
            "message": message,
            "template_id": fields.get("template_id"),
            "source": source,
            "service": fields.get("service") or fields.get("service_name") or fields.get("app") or fields.get("application"),
            "host": fields.get("host") or fields.get("hostname"),
            "raw": raw,
            "attributes": fields.get("attributes", {}),
            "metadata": metadata  # Metadata objesini buraya ekledik
        }

    def _generate_unique_event_id(self, raw, event_time, source):
        # Deterministic + unique for a single ordered stream replay:
        # counter differentiates identical duplicate lines while raw/event_time
        # keep the ID stable across repeated runs of the same input file.
        self._counter += 1
        seed = f"{self._counter}|{event_time}|{source}|{raw}"
        return xxhash.xxh64(seed.encode("utf-8")).hexdigest()[:13]