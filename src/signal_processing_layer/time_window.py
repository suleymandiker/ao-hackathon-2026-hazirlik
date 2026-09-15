import time
from collections import deque
import threading

class TimeWindowManager:
    def __init__(self, window_seconds=60):
        self.window_seconds = window_seconds
        self.events = {} 
        self._lock = threading.Lock()
        self._last_cleanup = time.time()

    def add_and_count(self, template_id, current_time_ms=None):
        # 1. Zaman Standartlaştırma (Milisaniyeyi Saniyeye Çevir)
        if current_time_ms is None:
            now_sec = time.time()
        else:
            # Gelen veri milisaniye ise saniyeye çeviriyoruz (10 haneden büyükse ms'dir)
            now_sec = current_time_ms / 1000.0 if current_time_ms > 1e12 else current_time_ms
            
        with self._lock:
            # 2. TemplateID Yönetimi
            if template_id not in self.events:
                self.events[template_id] = deque()
            
            self.events[template_id].append(now_sec)
            
            # 3. Eskimiş Logları Temizle (Mevcut mantık)
            cutoff_time = now_sec - self.window_seconds
            while self.events[template_id] and self.events[template_id][0] < cutoff_time:
                self.events[template_id].popleft()
            
            # 4. MEMORY LEAK ÖNLEMİ (Genel Temizlik)
            # Her 5 dakikada bir, içi tamamen boşalmış template anahtarlarını siler
            if now_sec - self._last_cleanup > 300: 
                self._global_cleanup(cutoff_time)
                self._last_cleanup = now_sec

            return len(self.events[template_id])

    def _global_cleanup(self, cutoff_time):
        """Aktif olmayan (boş) template anahtarlarını bellekten tamamen atar."""
        to_remove = [tid for tid, dq in self.events.items() if not dq]
        for tid in to_remove:
            del self.events[tid]