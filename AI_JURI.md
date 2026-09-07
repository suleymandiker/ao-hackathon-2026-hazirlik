# AI Jüri Özeti

## 1. AI Stratejimiz ve İş Akışı
Modeli verinin özetlenmesi için kullandık, kodlamada GitHub Copilot destek verdi.
Kanıt: `prompts/analiz_prompt.txt`, `conv.history.md`

## 2. Problemi Nasıl Çözdük
Sentetik veriyi alıp JSON parse ederek modele verdik.
Kanıt: `src/main.py`

## 3. X-Factor
Terminal üzerinden direkt doğal dil ile verinin ne anlama geldiğini sorma yeteneği.
Kanıt: `src/main.py:25-40`

## 4. Çalıştırma
`pip install requests` -> `python src/main.py`

## 5. Bilinen Sınırlar
Şu an sadece 10 satırlık veriyi analiz edebiliyor. (Mailde dürüstlüğün puan kazandırdığı vurgulanmış.)