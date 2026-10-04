# Mail Ajanı: denetim tur 1 düzeltmeleri

Tarih: 5 Ekim 2026. Doğruluk kaynağı: [tasarım](specs/2026-09-19-mail-ajani-design.md).
İncelenen rapor: [bağımsız denetim](denetim-tur-1.md).

Tasarım ve denetim raporu düzenlemelerden önce tam okundu. Planın Global Constraints bölümü de kontrol edildi.
İstenen 11 bulgunun tamamı düzenleme öncesindeki kaynakta doğrulandı; İTİRAZ yok.
Başlangıçta 77 test, düzeltmelerden sonra 154 test geçti. Her düzeltilen bulgu için regresyon testi var.

## Bulgu bazında sonuç

| Bulgu | Sonuç | Düzenleme öncesi doğrulama ve yapılan düzeltme | Regresyon kanıtı |
|---|---|---|---|
| E1 | Düzeltildi | `tur.run_tur`, Telegram'dan önce otomatik kararı kaydediyor ve çöp/arşiv için `mark_sent` çağırıyordu; `db.pending_mails` etkin kararı olanları eliyordu. Artık bildirilmemiş otomatik kararlar bekliyor. `decisions.notified_at` başarılı özet teslimini kaydediyor; çöp/arşiv ancak kendi özet parçası teslim edilince, önemli ancak kartı teslim edilince gönderilmiş sayılıyor. Devam turunda Gmail işlemi ve sınıflandırma tekrarlanmıyor. Eski veritabanına veri koruyan, SQLite yazma kilidi altında bir sütun geçişi eklendi. | `test_auto_delivery_recovers_without_reapplying_or_duplicate_card`: çöp/arşiv/önemli için özet hatası, önemli için kart hatası; aynı dilimde telafi, tek Gmail işlemi, tek kart ve tek geri al düğmesi. `test_style_auto_failed_summary_is_recovered_without_a_second_gmail_action`: üç tarz türü. `test_existing_database_migrates_notification_column_without_losing_data`: eski verinin korunması. |
| E2 | Düzeltildi | `parse_output` dış nesne, `items` ve öğelerde tür denetimi yapmıyordu; `classify` yalnız üç hata türünü yakalıyordu. Dış çıktı, sonuç listesi, kimlik/karar/özet, eksik ve yinelenen sonuçlar denetleniyor. Bozuk parçanın tahminleri kullanılmıyor; diğer sağlam parçalar korunuyor. Parça başına `Exception` yakalanıyor; `run_tur` da beklenmedik sınıflandırıcı hatasına karşı korumalı. Önceki başarısız gönderimden kalan tahminler fallback sırasında temizleniyor. Ham CLI çıktısı/hata metni uyarıya taşınmıyor. | `test_malformed_output_never_escapes_and_has_no_predictions`: dizi, metin, null, yanlış türler, geçersiz/eksik/yinelenen sonuçlar. `test_bad_chunk_does_not_discard_good_chunk`. `test_malformed_claude_output_reaches_predictionless_cards_with_warning`: rapordaki dört çıktı uçtan uca. `test_classifier_exception_clears_old_prediction_and_sends_warning`. |
| E3 | Düzeltildi | Telegram `_call` tek denemeliydi; kartlar beklemeden gidiyordu; tur plist'inde periyodik tekrar yoktu. 429 `retry_after`, bağlantı/zaman aşımı ve 5xx hatalarında en fazla üç tekrar eklendi. Toplam tekrar beklemesi en fazla 60 saniye; daha uzun 429 beklemesi kalıcı teslim tarihiyle sonraki çalışmaya erteleniyor, erken tekrar yapılmıyor. Teslim tarihi çekim/sınıflandırmada geçen süreyi de içeriyor. Tur mesajları arasında 1 saniye var. Plist'e `StartInterval=900` eklendi, dört takvim saati ve `should_run` korundu. Telegram/hesap çekimi/istemci kurma hatasında dilim tamamlanmıyor, CLI 1 dönüyor. `tur_incomplete`, daha önce başarılı olmuş aynı dilimdeki yarım `--force` turunun da tekrarını sağlıyor. Gönderilemeyen uyarılar yerelde saklanıp sonraki denemede iletiliyor. | `test_transient_errors_retry_then_succeed`, `test_retries_are_bounded_and_exhaustion_is_safe`, `test_long_retry_after_is_deferred_without_retrying_early`; `test_partial_cards_resume_same_slot_and_completed_slot_skips`, `test_warning_delivery_is_retried_even_when_cards_already_sent`, `test_sends_are_paced`, `test_long_telegram_retry_after_survives_until_scheduled_retry`, `test_retry_after_deadline_includes_time_spent_classifying`, `test_failed_forced_run_reopens_previously_completed_slot`; çekim/eksik istemci testleri ve `test_scheduled_tur_retries_in_same_slot_and_keeps_calendar`. |
| E4 | Düzeltildi | `cmd_tur` boyunca süreç kilidi yoktu. Artık `config.home()/tur.lock` üzerinde `fcntl.flock(LOCK_EX \| LOCK_NB)` alınmadan ayar, sır ve istemciler okunmuyor. İkinci tur, `--force` dahil, Türkçe bilgiyle 0 dönüyor. Dosya turun tamamında açık; hata ve dönüşte kilit bırakılıyor. | `test_overlapping_forced_tur_exits_cleanly_before_loading_config`, `test_lock_spans_whole_run_and_is_released_after_failure`: aynı dosyayı bağımsız açan gerçek işletim sistemi kilidi; tur çalışırken ikinci CLI girişi ve hatadan sonra kilit bırakılması. Süreç/fork başlatılmadı. |
| Ö1 | Düzeltildi | `_on_undo`, basılan mesajın kimliği kart kimliğiyle aynı değilse yeni kart yolluyordu. Artık `tg_message_id` varsa mevcut kart düzenleniyor; yalnız hiç kartı olmayan çöp/arşiv geri almalarında yeni kart var. | `test_undo_auto_important_from_summary_edits_existing_card_without_sending`; mevcut `test_undo_from_summary_sends_new_card` da korunuyor. |
| Ö2 | Düzeltildi | Metin ve klavye yalnız ilk 20 otomatik kararı gösteriyordu. `summary_batches` 20'lik parçalar üretiyor; her parça kendi geri al düğmeleriyle teslim ediliyor. Başarı kaydı parça bazında; ikinci parça başarısızsa ilk 20 yeniden bildirilmez. Metin/klavye yardımcıları verilen listeyi kırpmıyor. | `test_twenty_five_autos_have_twenty_five_undo_buttons_on_normal_path`, `test_more_than_twenty_autos_each_have_undo_and_partial_summary_recovers`, `test_summary_lists_autos_with_undo`. |
| Ö3 | Düzeltildi | Dinleyici başlangıç ayarını ve Gmail istemcilerini sürekli kullanıyordu. Her güncellemede güncel hesap listesi okunuyor; yeni hesap ekleniyor, çıkarılmış hesap önbellekten siliniyor. İşlem/geri alma sırasında `GmailAuthError`, `RefreshError` veya HTTP 401 gelirse yalnız ilgili istemci siliniyor; sonraki basışta mevcut Keychain izniyle yeniden kuruluyor. Geçici 503 önbelleği silmiyor. | `test_listener_reloads_accounts_and_rebuilds_client_after_auth_failure`: çalışan dinleyicide yeni hesabın düğmesi ve izin yenileme sonrası başarılı ikinci basış. `test_auth_failure_invalidates_cached_client_for_action_and_undo`: üç yetki hatası × iki işlem yolu. `test_transient_gmail_error_keeps_cached_client`. |
| Ö4 | Bırakıldı | Kullanıcı talebiyle `/durum` hata gösterimi kapsam dışında. Gönderilemeyen uyarıları saklayan E3 kaydı `/durum` görünümünü değiştirmiyor. | Yeni değişiklik/test yok. |
| Ö5 | Düzeltildi | Gmail mesaj/etiket çağrılarının tamamı varsayılan `num_retries=0` kullanıyordu. Hepsinde `execute(num_retries=3)` var. Kurulu googleapiclient kaynağında 429/5xx ve üstel tekrar davranışı doğrulandı; ağ araştırması yapılmadı. CLI log kurulumunda `googleapiclient.http` normal logları kapatılıyor: yeni tekrar uyarıları istek URL'sini yazabiliyor. Uygulamanın güvenli, yalnız hata sınıfı içeren uyarıları devam ediyor. | `test_every_gmail_request_has_bounded_library_retries`: bütün mesaj/etiket yolları. `test_library_retries_transient_gmail_errors_without_url_logs`: gerçek `HttpRequest`, sahte taşıma katmanında 429 → 503 → başarı ve dört 503'te tükenme; beklemeler, çağrı sayısı ve URL'siz log doğrulandı. |
| Ö6 | Düzeltildi | Boş gönderen 10 karardan sonra kural olabiliyordu; tarz yetkisi de boş gönderene uygulanabiliyordu. Boş/yalnız boşluk gönderen için kural oluşturulmuyor ve hiçbir otomatik işlem seçilmiyor. Eski boş gönderen kuralı da kullanılamıyor, öğrenme güncellemesinde siliniyor. | `test_empty_sender_does_not_form_rule_and_never_uses_style_authority`, `test_empty_sender_with_style_authority_always_gets_card`. |
| Ö7 | Düzeltildi | İki plist'in ortam sözlüğünde yalnız PATH vardı. İkisine `HOME=__HOME__` eklendi; mevcut kurulum betiğinin yer tutucu dönüşümüyle uyumlu. | `test_both_launchd_agents_have_explicit_home_after_install_substitution`; ayrıca iki plist'in `plutil -lint` sonucu OK. |
| Ö8 | Bırakıldı | Kullanıcı talebiyle log çoğalması, dinleyici yeniden başlama döngüsü ve urllib3 log politikası kapsam dışında. Ö5'te yalnız yeni Gmail tekrarlarının URL yazmasını önleyen logger ayarı eklendi. | Yeni Ö8 değişikliği/testi yok. |
| Ö9 | Düzeltildi | `bot-kur`, bütün mesajlardan son sohbet kimliğini onaysız kaydediyordu. Yalnız `/start` mesajları aday. Seçilen sohbetin adı, kullanıcı adı ve kimliği gösteriliyor; açık `evet` cevabından önce Keychain veya sahip ayarı yazılmıyor. | `test_bot_setup_shows_start_chat_and_requires_explicit_confirmation`: evet / hayır / boş / yes; sonradan gelen sıradan mesaj aday olmuyor. `test_bot_setup_ignores_non_start_messages`. Giriş, Telegram ve Keychain testte sahte. |
| Ö10 | Bırakıldı | Kullanıcı talebiyle canlı kurulum sırası kapsam dışında. | Kurulum çalıştırılmadı. |

## Arayüz ve eski testlerdeki değişiklikler

Fonksiyonların mevcut çağrı imzaları korunuyor. `run_tur` tamamlanmamış iş için `incomplete=True` alanı,
`TelegramError` ise güvenli `retry_after` ve `not_modified` bilgileri taşıyor. Veritabanına yalnız bildirim zamanı sütunu eklendi.

Dört eski beklenti yeni sözleşmeye göre açıkça güncellendi:

- Bekleyen sorgusu artık bildirilmemiş otomatik kararı içeriyor; gönderilmiş ve kullanıcı kararlı mailleri eleme kontrolleri korunuyor.
- Sınıflandırıcı testi, geçersiz kararın sessizce atılmasını beklemek yerine ayrı regresyonla tüm hatalı parçanın tahminsiz kalmasını doğruluyor. Geçerli `result` JSON yolu korunuyor.
- Özet testi ilk 20 ile yetinmek yerine bütün 22 düğmeyi ve 20+2 parçalamayı doğruluyor.
- Ham CLI/Gmail/Telegram hata metni yerine güvenli Türkçe hata beklentisi var; sır/URL sızmadığına ilişkin ek kontroller eklendi. Ağ hatası testi artık ilk denemede hata beklemek yerine dört denemenin tükenmesini doğruluyor.

Hiçbir güvenlik, öğrenme eşiği, tekrar gönderim veya Gmail davranışı kontrolü kaldırılmadı.

## Değişen dosyalar

- Uygulama: `mail_ajani/cli.py`, `classifier.py`, `db.py`, `dinleyici.py`, `gmail.py`, `learning.py`, `render.py`, `telegram.py`, `tur.py`.
- Zamanlayıcılar: `launchd/com.oguzhan.mail-ajani.tur.plist`, `launchd/com.oguzhan.mail-ajani.dinleyici.plist`.
- Testler: `tests/conftest.py`, `test_classifier.py`, `test_cli.py`, `test_db.py`, `test_dinleyici.py`, `test_gmail.py`, `test_learning.py`, `test_render.py`, `test_telegram.py`, `test_tur.py`; yeni `tests/test_launchd.py`.
- Rapor: `docs/duzeltme-tur-1.md`.

## Kabul kontrolleri

Tüm pytest çalıştırmalarında `MAIL_AJANI_HOME` ve `MAIL_AJANI_LOGS`, `mktemp -d` ile geçici dizinlere ayarlandı.
Gerçek kişisel veriler veya Keychain sırları okunmadı. Başlangıç kontrolü: **77 passed in 0.23s**.
Son tam paket komutu:

```sh
MAIL_AJANI_HOME=$(mktemp -d) MAIL_AJANI_LOGS=$(mktemp -d) .venv/bin/pytest -q
```

Son çıktı:

```text
........................................................................ [ 46%]
........................................................................ [ 93%]
..........                                                               [100%]
154 passed in 0.31s
```

Statik kontroller:

```text
plutil -lint launchd/*.plist
launchd/com.oguzhan.mail-ajani.dinleyici.plist: OK
launchd/com.oguzhan.mail-ajani.tur.plist: OK

bash -n scripts/*.sh
çıkış kodu: 0; çıktı yok
```

`mail_ajani/` içinde `messages.delete`, `batchDelete`, `UNREAD`, `threads(` taramasında eşleşme yok.
Telegram ve Google bağlantısı, Claude CLI, launchd yükleme, pip kurulumu, git, etkileşimli komut ve alt ajan/fork çalıştırılmadı.
Bot kurulum regresyonlarında kullanıcı girdisi ve servis çağrıları sahteydi. Gerçek kilit testlerinde yalnız bağımsız dosya açma kullanıldı.

## Sahibin karar vermesi gerekenler ve sınırlar

Bu 11 düzeltme için yeni tasarım kararı gerekmiyor. İstenen Ö4/Ö8/Ö10 ve denetimin yedi açık sorusu değiştirilmedi.
Özellikle mesaj mı konuşma mı arşivleneceği, yıldızlı gönderenin Gmail'deki elle verilen yıldızları kapsayıp kapsamadığı ve
başarılı Telegram teslimi ile yerel kayıt arasındaki çökme penceresinde teslim garantisi, sahibin değerlendirmesine açık kalıyor.
`untrash` davranışı, launchd Keychain izni, gecikmiş mail penceresi ve Claude CLI çıktı uyumluluğu da canlı doğrulama bekliyor.

Normal başarılı akış ve bilinen başarısız teslimlerden sonraki devam testlerinde çift kart yok.
Sunucu mesajı kabul edip ağ cevabı kaybolursa ya da teslimden sonra yerel kayıt öncesi süreç ölürse,
Telegram'ın idempotency anahtarı bulunmadığı için kesin tek teslim garantisi verilemez; denetimin açık çökme sorusu genişletilmedi.

Eski sürüm çöp/arşiv için teslimden önce `sent_at` yazdığı için geçmişte kaybolmuş bildirim ile gerçekten teslim edilmiş bildirimi
veritabanından ayırt etmek mümkün değil. Bu değişiklik eski gönderilmiş kayıtları topluca yeniden yollamıyor.
Eski sürümle gerçek turlar yapılmış ve bildirim kaybından şüphe varsa sahibin geçmiş otomatik kararları kontrol etmesi gerekir.
Eski otomatik önemli kararlarda `sent_at` boşsa yeni bekleyen sorgusu bunları da telafi eder.

Plist şablonları düzeltildi; yüklü launchd ajanlarına uygulanmadı. 15 dakikalık yeniden deneme ve açık HOME ayarı,
sahibin daha sonra yapacağı yeniden kurulum/yükleme ile etkinleşir.
