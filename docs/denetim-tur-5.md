# Mail Ajanı: bağımsız denetim, tur 5 (Ö4-1 ve Ö4-3 doğrulaması)

Tarih: 5 Ekim 2026 · Denetleyen: Opus (salt okunur) · Konu: `c79c047` (HEAD). Tur 4 düzeltmeleri `4f8ad3f`'te.
Kapsam isteğe göre dar: yalnız engel düzeyindeki ve gözetimsiz çalışmadan önce düzeltilmesi gereken sorunlar.

## Karar

**Evet, gözetimli canlı kuruluma hazır. Gözetimsiz çalışmayı engelleyen bir kod sorunu da kalmadı.** Ö4-1 ve Ö4-3 kapandı, önceki
yeniden üretimlerde gerileme yok. Gözetimsiz çalışmadan önce kalan şart kodda değil, canlı denemede: tur 1'in açık soruları (konuşma ve
mesaj arşivi, `untrash`, launchd altında Anahtar Zinciri izni) gerçek hesapla görülmeli.

## Çalıştırılan kontroller ve sonuçları

| Kontrol | Sonuç |
|---|---|
| `MAIL_AJANI_HOME=$(mktemp -d) MAIL_AJANI_LOGS=$(mktemp -d) .venv/bin/pytest -q` | geçti (197 passed) |
| Ö4-3 yeniden üretimi: 20 otomatik işlem, 254 karakterlik göndericiler, 4096 üstüne 400 dönen sahte Telegram | geçti |
| Özet kalıcı 400 (25 otomatik işlem, 2 parça) → yedek özet, kayıt muhasebesi | geçti |
| Yedek özet de reddedilirse | geçti (kayıp yok, 1 saatlik bekleme, karar bildirilmemiş kalıyor) |
| `--force` beklemeyi aşıyor, launchd çağrısı aşmıyor | geçti |
| Tur 1-4 yeniden üretimleri (R1-R5, R9, N1-N5, Y1, Y1b, Y2, Y2b, Ö-A, 35 ret, uyarı reddi, boş gönderen) | gerileme yok |
| Gerçek Gmail, Telegram, `claude`, launchd, Anahtar Zinciri | çalıştırılmadı (kapsam dışı) |

## Bulguların durumu

### Ö4-3: özet reddi her şeyi bekletiyordu: **kapandı**

- **Kısaltma:** 20 otomatik işlem, 240+ karakterlik göndericiler, `Ş&<` dolu konular:
  `özet UTF-16: 3277 | geri al düğmesi: 20 | mesajlar: 2 | kart geldi: True` (tur 4'te 7017 birimdi).
- **Yedek özet:** Ayrıntılı özetleri reddeden sahte Telegram, 25 otomatik işlem (20 + 5 iki parça):
  ```
  özet mesajı: 2 | geri al düğmesi: 25 tekil: 25 | otomatik karar: 25 bildirilen: 25
  yedek metin: <b>12:00 turu</b> · 26 yeni · 0 önemli · 1 senin kararını bekliyor / Kendi yaptıklarım: 20 işlem (ayrıntı gösterilemedi, geri al düğmeleri aşağıda)
  bekleyen: 0 | kart geldi: True | last_run: True
  12:15 {'skipped': True} | toplam mesaj: 3
  ```
  Bildirilmeyen otomatik karar yok, çift özet yok, her otomatik karar için tek geri al düğmesi var, arkadaki kart gitti, dilim kapandı.
- **Yedek de reddedilirse:** İstisna dış `except`'e gidiyor; 1 saatlik bekleme yazılıyor (`retry_at 13:00`). 3 otomatik kural kararı
  bildirilmemiş, 4 mail bekliyor olarak kalıyor (mark_notified ve mark_sent çağrılmadı). 12:15 bekleme nedeniyle dönüyor, 18:00'de yeniden
  deneniyor. Kayıp ya da çift Gmail işlemi yok. Yedek metin yalnız sayı ve saat içerdiği için Telegram'ın içerik yüzünden onu da
  reddetmesi gerçekte beklenmiyor.

### Ö4-1: `--force` bir saatlik beklemeyi aşmıyordu: **kapandı**

403 → bekleme; Telegram düzeldikten sonra:
```
12:15 otomatik {'incomplete': True}
12:20 force {'new': 1, …} | retry_at: ''
kart k1 sayısı: 1 | 12:35 {'skipped': True}
```
launchd çağrısı (force'suz) beklemeye uyuyor, elle `--force` hemen teslim ediyor ve beklemeyi temizliyor. `--force` artık Telegram'ın 429
`retry_after` süresini de aşıyor. Bu yalnız elle başlatılan çağrıda olur: istemci 60 saniyelik tekrar bütçesini aşınca yeni bir bekleme
yazar. Tek gönderim ya da kayıp açısından risk değil.

### Genişletilmiş bekleme (429 dışındaki her 4xx)

- **Kayıp yok:** Bekleme yalnız Telegram teslimini erteliyor. Mailler veritabanında, çekim penceresi korunuyor. Ö-A senaryosunda 4 kart
  13:20'de eksiksiz ve tek kez geldi.
- **Sonraki dilimi kalıcı engellemiyor:** Bekleme her seferinde `şimdi + 1 saat`; 18:00 denemesi yapıldı (yukarıda). Başarılı turda
  `telegram_retry_at` temizleniyor.
- Kartın kendisine ait 400 hâlâ `defer`'e gitmiyor (kart ret kaydı ve yedek kart yolu): 35 ret senaryosu tur 4'teki gibi 4 uyarı mesajı,
  hepsi gönderildi sayıldı, 12:15 atlandı.

## Gerileme

Önceki çıktılarla aynı:

- R1: tek Gmail işlemi, sonraki turda 3 mesaj.
- R2: bozuk Claude çıktısı dışarı taşmıyor.
- R3: aynı mail için 1 kart.
- R4: 25 düğme, 2 mesaj.
- R5: devamda özet tekrarı yok.
- N1/N2: dilim başına tek uyarı.
- N4: tamamlanmış dilimde çağrılar atlanıyor.
- N5: 429'a uyuluyor, 2 kart.
- Y1: bozuk hesabın maili sonraki dilimde tek kart.
- Ö-A: kart reddi kaydı yok.
- Uyarı reddinde tek yedek uyarı.
- Boş gönderene kural yok.

Tek fark beklenen davranış: tur 4'teki "18:15 force" artık beklemeyi aşıp teslim ediyor. Eski N3/Y2c betiklerindeki sahte Telegram durum
kodu taşımadığı için çıktıları önceki turlarda açıklandığı gibi.

## Gözetimsiz çalışmadan önce

Kodda engel yok. Canlı denemede görülmesi gerekenler (tur 1 açık soruları):

- tek mesaj arşivlenince konuşmanın gelen kutusunda kalıp kalmadığı,
- Çöp → Geri al sonrası mailin gelen kutusuna dönüp dönmediği,
- launchd altında ilk turda Anahtar Zinciri izin penceresi çıkıp çıkmadığı (`tur.log`).

Plist değişiklikleri (`StartInterval=900`, `HOME`) `scripts/kur.sh` yeniden çalışınca yürürlüğe girer.
