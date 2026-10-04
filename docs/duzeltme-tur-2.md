# Mail Ajanı: düzeltme turu 2

Tarih: 5 Ekim 2026. Kaynaklar: `docs/denetim-tur-2.md`, tasarım şartnamesi,
`docs/denetim-tur-1.md` ve `docs/duzeltme-tur-1.md`. Python: **3.14.7**, mevcut `.venv`.

İstenen beş bulgu mevcut kaynakta düzenleme öncesinde doğrulandı ve düzeltildi.
**İTİRAZ yok.** Y5 ve bütün açık sorular kullanıcı talebiyle bırakıldı.
Birinci turun commit edilmemiş düzeltmeleri korundu; bu turda git çalıştırılmadı.

## Bulgu başına doğrulama ve sonuç

| Bulgu | Durum | Düzenleme öncesi kaynak kanıtı ve yapılan düzeltme |
|---|---|---|
| Y1 | **Düzeltildi** | `tur.py` içinde `complete = not warnings` eksik istemciyi, çekim hatasının `complete = False` satırı da başarısız hesabı dilimi açık tutma nedeni yapıyordu. Artık yalnız bitmemiş Telegram teslimi dilimi açık tutuyor. Başarısız hesabın `last_fetch` kaydı ilerlemiyor; diğer hesaplar teslim edilince ve uyarı ulaşınca `last_run` yazılıyor. Tamamlanmış dilimde 15 dakikalık çağrılar atlanıyor; hesap sonraki dilimde eski çekim penceresinden kayıpsız telafi ediliyor. Aynı uyarı, Telegram teslimi nedeniyle devam eden dilimde de yeniden gönderilmiyor (`tur_warned`). |
| Y2 | **Düzeltildi** | `render.card_text` konu/ad/gövde uzunluklarını sınırlamıyordu; `run_tur` kart döngüsündeki ilk `TelegramError` bütün gönderimi kesiyordu. Kart alanları HTML kaçışından önce karakter bazında, kaçış sonrası UTF-16 bütçesiyle kesiliyor; HTML etiketi, entity veya emoji yarım bırakılmıyor. Kart ve işlem sonrası kart 4096 sınırının altında. `TelegramError.status_code` ve `permanent`, 429 dışındaki 4xx retlerini ayırıyor. Kalıcı rette aynı karar düğmeleriyle kısa yedek kart deneniyor; sonraki kartlara ve uyarılara devam ediliyor. Yedek de kalıcı reddedilirse mail kimliği ve durum kodu mevcut `meta.card_rejections` kaydında tutuluyor, kullanıcıya mail kimliğiyle açık uyarı gidiyor. Mail verisi silinmiyor; `sent_at` ancak bu uyarı teslim edilince yazılıyor. Uyarı teslim edilmezse mail bekliyor, ret kaydı yeniden kart denemesini engelliyor ve sonraki çağrı uyarıyı tamamlıyor. Yedeğin geçici hatasında mail bekliyor, teslim tarihi korunuyor. |
| Y3 | **Düzeltildi** | `cmd_tur` önce `_telegram` ve `build_clients`, sonra `run_tur` içindeki atlama kontrolünü çağırıyordu. Kilit altında önce veritabanı açılıp ortak `tur.skip_result` çalışıyor; tamamlanmış ve bekleyeni olmayan dilim veya henüz dolmamış `telegram_retry_at`, ayar/sır/istemci erişiminden önce dönüyor. `--force`, yeni dilim, bekleyen mail, bekleyen uyarı ve yarım teslim çalışmayı sürdürüyor; `--force` sunucunun bekleme tarihini aşmıyor. |
| Y4 | **Düzeltildi** | `parse_output` tek geçersiz öğede ve sonuç kimlikleri eksikken `ClassifierError` fırlatıp bütün parçanın tahminlerini düşürüyordu. Artık eksik/geçersiz öğe yalnız kendi mailini tahminsiz bırakıyor; sağlam öğeler korunuyor. Yinelenen kimliğin yalnız kendi tahmini eleniyor. Kısmi sonuçta güvenli uyarı var. Dış çıktı/sonuç listesi bozuksa veya hiç geçerli sonuç yoksa `classify` uyarılı tahminsiz dönüş yapıyor; istisna dışarı taşımıyor. Ham model çıktısı hata metnine girmiyor. |
| Y5 | **Bırakıldı** | Kullanıcı açıkça kapsam dışında bıraktı. Belirsiz ağ hatasında gönderim tekrarının çift teslim olasılığına ilişkin mevcut tercih değiştirilmedi; bağlantı/zaman aşımı tekrarları korunuyor. |
| Y6 | **Düzeltildi** | `summary_batches([])` boş otomatik işlem listesinde `[[]]` üretiyor, `run_tur` devamda bunu yeniden gönderiyordu. Başarıyla teslim edilen özet `meta.tur_summary_sent` ile kaydediliyor; yarım dilimde boş özet tekrarlanmıyor. İlk özet teslim edilmediyse tekrar deneniyor. Bildirilmemiş yeni otomatik kararlar kendi geri al düğmeleriyle özetleniyor; önce teslim edilen otomatik kararlar tekrar bildirilmez. Yeni dilimde ve yeni `--force` turunda kayıt sıfırlanıyor. |
| Açık sorular | **Bırakıldı** | Kullanıcı talebi: mesaj/konuşma arşivi, `untrash`, launchd Keychain izni, `after:` örtüşmesi, yıldızlı gönderen tanımı, gerçek Claude CLI uyumluluğu ve gönderim/kayıt arasındaki çökme penceresi değiştirilmedi. Önceki kapsam dışı Ö4/Ö8/Ö10 da değiştirilmedi. |

Y2'de yedek kart da reddedilirse `tg_message_id` boş kalır: mail, yerel ret kaydı ve
başarıyla teslim edilmiş açık uyarıyla bildirilmiş sayılır. Bu durumda kart düğmesi yoktur;
kullanıcı maili Gmail'den kontrol eder. Sessiz düşürme veya maili silme yoktur.
Şema değişikliği yok; yeni teslim kayıtları mevcut `meta` tablosundadır.

## Regresyon kanıtı

- **Y1:** `test_missing_client_completes_slot_and_recovers_next_slot`,
  `test_failed_fetch_completes_slot_and_recovers_next_slot_without_repeats`:
  dilim kapanması, üç ara çağrının atlanması, tek uyarı, sağlıklı hesabın tek teslimi,
  eski `last_fetch` penceresinden sonraki dilimde telafi. İkinci test, beklerken sağlıklı
  hesaba gelen yeni mailin de sonraki dilime kaldığını doğruluyor.
  `test_persistent_account_failure_warns_once_in_each_completed_slot`: sürekli hata
  iki ayrı dilimde birer kez bildiriliyor. Eski `test_missing_client_keeps_slot_open`
  ve çekim hatasında dilimi açık bekleyen test yeni sözleşmeyle adlandırılıp güçlendirildi;
  `test_account_failure_warns_and_others_continue` içindeki yanlış `last_run` beklentisi düzeltildi.
- **Y2:** `test_permanent_card_rejection_continues_to_other_cards_and_warning`:
  yedek kartın başarı ve kalıcı ret yolları, arkadaki kart/uyarı, sonraki çağrılarda tekrarsızlık.
  `test_permanent_rejection_waits_for_warning_delivery_and_is_not_retried`:
  uyarı geçici başarısızken ret kaydı ve bekleyen mail korunuyor, devamda yalnız uyarı teslim ediliyor.
  `test_recorded_rejection_reconstructs_identified_warning_before_marking_sent`:
  yalnız ret kaydı varsa mail kimlikli uyarı yeniden oluşturuluyor; mail uyarısız teslim edilmiş sayılmıyor.
  `test_permanent_card_with_temporary_fallback_failure_continues_and_recovers`:
  yedek 429'unda erken tekrar yok, sağlıklı kart ve hesap uyarısı tekrarlanmıyor, bekleyen mail telafi ediliyor.
  `test_long_card_payload_is_bounded_before_delivery`,
  `test_truncation_preserves_html_entities_tags_and_utf16_budget`:
  uzun konu/ad/adres/hesap/gövde, HTML entity ve emoji bütçesi, kapalı HTML etiketleri,
  işlem sonrası kart ve kısa kart sınırı.
  `test_error_exposes_safe_permanent_status_without_server_text`:
  400/401/403/404/422 kalıcı, 429/503 geçici; ham açıklama, URL ve anahtar hata metnine sızmıyor.
  `test_non_json_http_rejection_is_permanent_and_safe`: JSON olmayan HTTP 400 de güvenli kalıcı ret.
- **Y3:** `test_tur_skips_before_keychain_or_gmail_client_build`: tamamlanmış dilim ve
  dolmamış teslim tarihi için ayar, Keychain, Telegram ve Gmail kurucularının çağrılması testi düşürüyor.
  `test_tur_preflight_allows_due_or_pending_work`: force, bekleyen mail/uyarı, yarım teslim
  ve yeni dilimin çalışmasına ilişkin beş ayrı kontrol.
- **Y4:** `test_one_bad_item_preserves_other_predictions`: yedi bozuk öğe biçiminde sağlam
  tahmin korunuyor. `test_missing_one_of_twenty_five_preserves_twenty_four`: 25 mailin
  biri eksikken 24 tahmin korunuyor.
  `test_duplicate_invalidates_only_its_mail_even_if_followed_by_valid_item`:
  yinelenen kimlik diğer tahmini düşürmüyor ve üçüncü öğe tahmini tekrar açmıyor.
  `test_partial_classifier_result_keeps_valid_predictions_in_cards`: uçtan uca sağlam
  önemli kart, yalnız iki tahminsiz kart, güvenli uyarı ve bütün maillerin teslimi.
  Mevcut tamamen bozuk çıktı ve beklenmedik istisna regresyonları korundu.
- **Y6:** `test_partial_cards_resume_same_slot_and_completed_slot_skips` ve
  `test_auto_delivery_recovers_without_reapplying_or_duplicate_card`, devamdan sonra
  toplam özet sayısının bir olduğunu da doğruluyor.
  `test_resume_sends_summary_if_first_attempt_was_not_delivered`:
  başarısız ilk özet telafi ediliyor; yeni dilimin özeti ayrıca gönderiliyor.
  Mevcut 20+5 otomatik işlem telafisi ve tek Gmail işlemi kontrolleri korunuyor.

Öğrenme eşikleri, kullanıcı kararı, geri alma, Gmail işlemi, send-once ve sır güvenliği
iddiaları gevşetilmedi. Y1'deki yanlış açık-dilim iddiaları kullanıcı tarafından istenen
sözleşmeye göre değiştirildi; bunlara ara çağrılar ve sonraki dilim kontrolleri eklendi.

## Bu turda değişen dosyalar

- Uygulama: `mail_ajani/tur.py`, `mail_ajani/cli.py`, `mail_ajani/render.py`,
  `mail_ajani/telegram.py`, `mail_ajani/classifier.py`.
- Testler: `tests/test_tur.py`, `tests/test_cli.py`, `tests/test_render.py`,
  `tests/test_telegram.py`, `tests/test_classifier.py`.
- Rapor: `docs/duzeltme-tur-2.md`.

## Kabul kontrolleri ve çıktı sonu

Bütün test çağrılarında `MAIL_AJANI_HOME` ve `MAIL_AJANI_LOGS` geçici dizinlere ayarlandı.
İlk tam çalışmada yeni 429 durum-kodu regresyonu başarısızdı (183 passed, 1 failed).
429 dalı hata nesnesini yeniden oluştururken durum kodunu kaybediyordu; kaynak düzeltildi,
iddia korunarak ek hata/telafi kontrolleriyle son tam paket geçirildi.

```sh
MAIL_AJANI_HOME=$(mktemp -d) MAIL_AJANI_LOGS=$(mktemp -d) .venv/bin/pytest -q
```

Son tam test çıktısı:

```text
........................................................................ [ 38%]
........................................................................ [ 76%]
............................................                             [100%]
188 passed in 0.36s
```

```text
plutil -lint launchd/*.plist
launchd/com.oguzhan.mail-ajani.dinleyici.plist: OK
launchd/com.oguzhan.mail-ajani.tur.plist: OK

bash -n scripts/*.sh
çıkış kodu: 0; çıktı yok
```

İki betik ayrıca ayrı ayrı `bash -n scripts/kur.sh` ve `bash -n scripts/kaldir.sh`
ile kontrol edildi; ikisi de çıkış kodu 0, çıktı yok.

`mail_ajani/` içinde `messages.delete`, `batchDelete`, `UNREAD`, `threads(` taramasında
hiç eşleşme yok. Gmail işlem/okunma yolları, Keychain saklama modeli ve launchd dosyaları
bu turda değiştirilmedi. Telegram/Google bağlantısı, gerçek Keychain erişimi, Claude CLI,
launchd yükleme, paket kurulumu, git, etkileşimli komut, alt ajan, Agent çağrısı veya fork
çalıştırılmadı. Servis yolları yalnız sahte istemci/HTTP oturumu ve sahte sınıflandırıcı
çalıştırıcısıyla test edildi. Y5 ve açık çökme penceresi için yeni teslim garantisi iddiası yok.
