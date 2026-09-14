import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DOCS_DIR = BASE_DIR / "docs"

def analyze_checklist():
    total_tasks = 0
    completed_tasks = 0
    pending_items = []

    files_to_check = [DOCS_DIR / "fazlar.md", DOCS_DIR / "plan.md"]
    
    for file_path in files_to_check:
        if not file_path.exists():
            continue
        with open(file_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                clean_line = line.strip()
                if clean_line.startswith("- [x]") or clean_line.startswith("- [X]"):
                    total_tasks += 1
                    completed_tasks += 1
                elif clean_line.startswith("- [ ]"):
                    total_tasks += 1
                    task_desc = clean_line.replace("- [ ]", "").strip()
                    pending_items.append(f"{file_path.name} (Satır {line_num}): {task_desc}")

    if total_tasks == 0:
        print("⚠️ Henüz docs/ altında fazlar.md veya plan.md içerisinde görev bulunamadı.")
        return

    percentage = (completed_tasks / total_tasks) * 100
    bar_length = 25
    filled_length = int(bar_length * completed_tasks // total_tasks)
    bar = "█" * filled_length + "░" * (bar_length - filled_length)

    print("\n" + "=" * 65)
    print("📊 HACKATHON İLERLEME DASHBOARD'U")
    print("=" * 65)
    print(f"Tamamlanma Oranı : [{bar}] %{percentage:.1f}")
    print(f"Tamamlanan Görev : {completed_tasks} / {total_tasks}")
    print(f"Kalan Görev Sayısı: {len(pending_items)}")
    
    if pending_items:
        print("\n⚠️ Yapılacak İlk Görevler:")
        for idx, item in enumerate(pending_items[:7], 1):
            print(f"  {idx}. {item}")
    else:
        print("\n🎉 Tebrikler! Tüm maddeler tamamlandı. Reponuz kabule hazır.")
    print("=" * 65 + "\n")

if __name__ == "__main__":
    analyze_checklist()