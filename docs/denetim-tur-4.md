# Mail Ajanı: bağımsız denetim, tur 4 (Ö-A ve Ö-B doğrulaması)

Tarih: 5 Ekim 2026 · Denetleyen: Opus (salt okunur) · Konu: `1eef213` üstündeki commit edilmemiş değişiklik
(`mail_ajani/telegram.py`, `tur.py`, `render.py`, `tests/test_render.py`, `tests/test_telegram.py`, `tests/test_tur.py`).

## Karar

**Evet, gözetimli canlı kuruluma hazır.** Ö-A ve Ö-B kapandı. Bir saatlik bekleme mail kaybettirmiyor, sonraki dilimi kalıcı olarak
engellemiyor ve başarılı turdan sonra siliniyor. Önceki bütün senaryolarda gerileme yok. Yeni engel yok. Üç küçük öneri aşağıda; biri
(Ö4-3) olasılığı düşük ama etkisi büyük olduğu için gözetimsiz çalışmadan önce düzeltilmeli.

## Çalıştırılan kontroller ve sonuçları

| Kontrol | Sonuç |
|---|---|
| `MAIL_AJANI_HOME=$(mktemp -d) MAIL_AJANI_LOGS=$(mktemp -d) .venv/bin/pytest -q` | geçti (194 passed) |
| Ö-A yeniden üretimi: yarım dilimin devamında 403, sonra Telegram düzeliyor | doğru (aşağıda) |
| 403 bir dilim sınırını aşınca (17:50 → 18:00 → 18:55) | doğru |
| 35 kalıcı reddedilen kart (kart ve kısa kart 400) → uyarı uzunluğu | doğru: 4 mesaj, en uzunu 3783 UTF-16 birimi |
| Uyarı mesajının kendisi 400 alıyor | doğru: tek yedek uyarı gitti, ayrıntı logda, dilim kapandı, tekrar yok |
| Özet mesajı kalıcı 400 alıyor (yeni senaryo) | sorun gösterdi (Ö4-3) |
| Tur 1-3 yeniden üretimleri: R1, R2, R3, R4, R5, R9, N1-N5, Y1, Y1b, Y2, Y2b, Y2c | gerileme yok (R9 `run_tur` seviyesinde çift, beklenen; kilit CLI'da) |
| Yeni log satırına giren uyarı kaynaklarının taranması (`grep warnings.append`) | anahtar/jeton içeren kaynak yok |
| `git diff` ile test iddialarının karşılaştırılması | meşru (aşağıda) |
| Gerçek Gmail, Telegram, `claude`, launchd, Anahtar Zinciri | çalıştırılmadı (kapsam dışı) |

## Bulguların durumu

### Ö-A: Telegram'ın genel kalıcı hatası bütün kartları "reddedildi" yapıyordu: **kapandı**

`TelegramError.permanent` artık yalnız JSON gövdeli ve sohbetle ilgili olmayan 400 için doğru (`telegram.py:19-25`). 401/403/404/407/422,
"chat not found" ve JSON olmayan 4xx cevapları `needs_backoff` grubunda; `defer` bunlar için `telegram_retry_at = şimdi + 1 saat` yazıyor
(`tur.py:124-139`).

Kanıt (çalıştırıldı). 4 mail; 12:00'de özetten sonra 429 (600 sn), 12:15'ten itibaren her istek 403, 13:20'de Telegram sağlam:
```
12:15 {'new': 4, ..., 'incomplete': True} retry_at 13:15
12:30 {'incomplete': True} … 13:00, 13:10 {'incomplete': True}
card_rejections: None | gmail çekimi: 2 | sınıflandırıcı: 2
13:20 {'new': 4, ..., 'warnings': 1} | retry_at: ''
kartlar: [1, 2, 3, 4] | mesajlar: ['özet', 'kart', 'kart', 'kart', 'kart', 'uyarı']
13:35 {'skipped': True} | 18:00 {'new': 0, ...}
```
Hiçbir mail reddedilmiş sayılmadı. Bekleme süresince Gmail ve sınıflandırıcı çağrılmadı. Telegram düzelince 4 mailin her biri düğmeli
tek kart olarak geldi, özet tekrarlanmadı, `telegram_retry_at` temizlendi.

Uyarı uzunluğu (çalıştırıldı): 35 mailin kartı da kısa kartı da 400 alıyor:
```
12:00 {'new': 35, 'auto': 0, 'cards': 35, 'warnings': 70}
uyarı mesajı sayısı: 4 uzunluklar: [3783, 3744, 3744, 627] | gönderilmemiş mail: 0
35 mailin hepsi gönderen ile anılıyor: True
12:15 {'skipped': True}
```

Uyarı mesajının kendisi 400 alırsa (çalıştırıldı): `["⚠️ 1 uyarı Telegram'a gönderilemedi; ayrıntı tur.log dosyasında."]`, dilim kapandı,
12:15 atlandı. Log satırı: `Uyarı mesajı reddedildi, içerik: ['a: Gmail bağlantısı kurulamadı (GmailAuthError)']`.

### Ö-B: Reddedilen mail yalnız iç kimlikle anılıyordu: **kapandı**

`rejection_warning` artık hesap, gönderen (80 karakter) ve konuyu (80 karakter) yazıyor (`tur.py:111-114`). Kanıt:
`Mail #2 (a · kotu@x.com · ZEHIR konu): kısa kart da reddedildi. …`; 35 mailli denemede her mail gönderen adresiyle anıldı.

### Bir saatlik bekleme: kayıp ve kilitlenme

- **Kayıp yok:** Bekleme yalnız Telegram teslimini erteliyor. Hata turunda çekilen mailler veritabanında bekliyor. Sonraki çekimler
  `last_fetch - 1 sa`'ten devam ediyor. Ö-A'da 4 mailin dördü geldi; dilim aşımı senaryosunda bekleme sırasında gelen `x2` de 18:55'te geldi.
- **Sonraki dilim kalıcı engellenmiyor:** Bekleme süresi her başarısız denemede yeniden `şimdi + 1 saat`. Telegram düzeldikten sonra en geç
  1 saat içinde tur çalışıyor:
  ```
  17:50 (force) {..., 'incomplete': True}
  18:00 {'incomplete': True}
  18:15 force {'incomplete': True}
  18:55 {'new': 2, ...} ['özet', 'kart', 'kart', 'uyarı'] | last_run: …18:55
  19:10 {'skipped': True}
  ```
- **Temizleniyor:** Başarılı ve tamamlanmış turda `telegram_retry_at` boşaltılıyor (`tur.py:205-208`; Ö-A'da `retry_at: ''`).

### 422 bekleme grubunda mı olmalı

Evet. Telegram Bot API belgeleri 422 kodunu tanımlamıyor. Pratikte görülen kodlar 400, 401, 403, 404, 409, 429 ve 5xx. Tanınmayan bir 4xx'i
"bu kart bozuk" saymak geri dönüşsüz: mail kalıcı ret kaydına girer, düğmesi bir daha gelmez. Bekleme grubuna koymak ise yalnız 1 saatlik
gecikme. Belirsiz kodda güvenli taraf bekleme; seçim doğru.

## Gerileme denetimi

- **Tek gönderim ve tek Gmail işlemi:** R1 `gmail applied: [('g901', 'onemli')]`, sonraki turda 3 mesaj. N5 toplam 2 kart.
  R3 aynı mail için 1 kart.
- **Kayıp yok:** Y1 telafisi: `a-ARADA`, `b-2`, `b-3` birer kart, `a.since=05:00` korundu.
- **Y1:** N1/N2'de dilim başına tek uyarı, ara çağrılar atlandı; üç dilimde 3 uyarı.
- **Y2:** Tek zehirli kart arkadakileri bekletmiyor; `sonraki gitti: True`, zehirli mailin `sent_at`'i yalnız uyarıdan sonra doldu.
  Bu sahte Telegram konuyu içeren her metni reddettiği için uyarı da reddedildi ve yerine yedek uyarı gitti. Bkz. Ö4-2.
- **Y6:** R5 devamında ilk mesaj kart (özet tekrarı yok).
- **Bozuk Claude çıktısı (R2):** hâlâ dışarı taşmıyor.
- **Kilit ve tekrar sınırları:** bu turda değişmedi.
- **Sırlar:** Yeni log satırı (`tur.py:195`) yalnız uyarı metinlerini yazıyor. Uyarıların kaynakları: hesap adı + hata sınıf adı
  (`cli.py:29`, `tur.py:54, 89`), sınıflandırıcının kendi sabit metinleri (`tur.py:67`), sabit Telegram metni (`tur.py:127`), mail kimliği +
  hesap + gönderen + konu (`tur.py:163, 171, 181`). Hiçbiri anahtar, jeton ya da istek URL'si taşımıyor. Gönderen ve konu yerel loga
  düşüyor; bu kişisel veri, sır değil, ve log yerel klasörde (`~/Library/Logs/mail-ajani`).

## Testler

- 188 → 194 test. Yeni testler: `test_warning_messages_split_and_escape`, `test_auth_failure_is_not_recorded_as_card_rejection_and_recovers_with_buttons`,
  `test_rejection_warning_names_account_sender_and_subject`, `test_many_warnings_are_split_under_telegram_limit`,
  `test_rejected_warning_falls_back_once_and_closes_slot`, `test_chat_not_found_is_not_a_card_rejection`.
- `tests/test_telegram.py`'de değişen üç iddia meşru:
  1. `permanent == (400 <= code < 500 and code != 429)` → `permanent == (code == 400)`: yeni sözleşme. Yanına
     `needs_backoff == (code in (401, 403, 404, 422))` eklendi, yani ayrım daha sıkı denetleniyor.
  2. Çağrı sayısı iddiası `1 if permanent else 4` → `1 if 400 <= code < 500 and code != 429 else 4`: davranış aynı (429 dışındaki 4xx
     tek deneme, diğerleri 4); yalnız artık `permanent`'e bağlı değil.
  3. JSON olmayan 400 testi "kalıcı" yerine "kart reddi değil, bekleme gerekir" bekliyor. Yeni sözleşme. Anahtar/URL sızmama iddiası duruyor.

  Hiçbir güvenlik iddiası kaldırılmadı.

## Yeni sorunlar

### Engel

Yok.

### Öneriler

#### Ö4-1. `tur --force` bir saatlik beklemeyi aşmıyor
- **Yer:** `mail_ajani/tur.py:24-26` (`skip_result`, `force`'tan bağımsız).
- **Etki:** Oğuzhan botu düzelttikten (ör. engeli kaldırdıktan) sonra `tur --force` en fazla 1 saat "incomplete" döner.
  Kanıt: `18:15 force {'incomplete': True}`. Kayıp yok, yalnız gecikme.
- **Düzeltme:** `--force` yalnız kimlik/sohbet beklemesini aşsın, Telegram'ın 429 `retry_after` süresine uymaya devam etsin (iki süreyi ayrı meta anahtarında tut).

#### Ö4-2. Uyarı mesajı reddedilince o mesajdaki bütün uyarılar yalnız loga düşüyor
- **Yer:** `mail_ajani/tur.py:187-198`.
- **Etki:** Tek bir uyarı satırı (ör. konusunda Telegram'ın kabul etmediği bir karakter olan ret uyarısı) aynı mesajdaki ilgisiz uyarıları
  da ("hesap okunamadı" gibi) Telegram'dan siler; Oğuzhan yalnız "N uyarı gönderilemedi; ayrıntı tur.log" görür. Kanıt: sahte Telegram
  konuyu içeren metni reddedince yedek uyarı gitti, ret uyarısı yalnız logda kaldı.
- **Düzeltme:** 400 alan mesajın satırlarını tek tek dene; yine reddedilen satır için konu olmadan yalnız hesap ve gönderen adresini içeren kısa bir satır gönder.

#### Ö4-3. Özet mesajı kalıcı 400 alırsa hiçbir şey gitmiyor ve tur her 15 dakikada boşuna tekrarlanıyor
- **Yer:** `mail_ajani/render.py:57-66` (`summary_text` gönderen adresini kısaltmıyor), `tur.py:152-155` (özet hatası doğrudan dış
  `except`'e gidiyor), `tur.py:124-139` (kart reddi sayılan 400 için bekleme yok).
- **Tetikleyici:** 20 otomatik işlemli bir özet parçasında gönderen adresleri ortalama ~140 karakteri aşarsa metin 4096'yı geçer. Gerçek
  adreslerle olasılık düşük: 254 karakterlik adreslerle 7017 birim ölçüldü. Ya da özet metnini Telegram'ın reddettiği başka bir içerik.
- **Etki:** Özet hep ilk gönderildiği için o dilimde hiçbir kart ve uyarı gitmez. Bekleme olmadığından her 15 dakikada Gmail çekimi ve
  sınıflandırıcı yeniden çalışır. Kanıt (çalıştırıldı):
  ```
  12:00 … 12:45 hepsi {'new': 1, ..., 'incomplete': True}
  sınıflandırıcı çağrısı: 4 | giden: 0
  20 uzun göndericili özet UTF-16: 7017
  ```
- **Düzeltme:** `summary_text`'te gönderen ve konuyu `_short_html` ile kısalt. Özet kalıcı 400 alırsa otomatik işlem listesi olmadan kısa bir
  yedek özet gönderip kartlara devam et.

## Açık kalanlar

Değişmedi. Kullanıcı kararıyla Ö4 (`/durum`'da hata), Ö8, Ö10, Y5 ve tur 1 açık soruları duruyor. Canlı denemede bakılacaklar:

- konuşma görünümünde tek mesaj arşivlenince konuşmanın gelen kutusunda kalıp kalmadığı,
- `untrash`'ın maili gelen kutusuna geri koyup koymadığı,
- launchd altında Anahtar Zinciri izin penceresi.
