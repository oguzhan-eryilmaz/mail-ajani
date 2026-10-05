# İçerik kategorileri

5 Ekim 2026

İçerik kategorileri mevcut tur, öğrenme, Gmail, Telegram ve tam metin akışına
eklendi. Canlı yapılandırma ve veritabanı değiştirilmedi; özellik operatör kategori
listesini kurduğunda açılır. Başlangıç paketi 270 testle yeşildi; tamamlanan paket
351 testle yeşil. Mevcut testlerin hiçbir doğrulaması zayıflatılmadı.

## Yapılanlar

`config.json` içindeki `kategoriler` listesi sahibin tanımladığı nesneleri taşır:
`ad`, `tanim`, `onemli` ve isteğe bağlı `renk`. İsimler boş olmamalı, benzersiz ve
en fazla 60 karakter olmalı; önem alanı boolean olmalı. Renk verilirse Gmail
etiketinin arka plan rengi olarak kullanılır. Anahtar yoksa veya liste boşsa
kategorilendirme kapalıdır; mevcut prompt ve gönderen kuralının modeli atlama
davranışı aynen korunur.

`config.DEFAULT_KATEGORILER` şu listeyi içerir:

| Kategori | Her zaman önemli | Kapsam |
| --- | --- | --- |
| Güvenlik | ⭐ | Giriş/cihaz uyarıları, şifre/passkey/2FA değişiklikleri, yetki ve OAuth izinleri, hesap güvenliği. |
| Fatura | ⭐ | Fatura/e-fatura, makbuz, ödeme alındı/ödeme belgesi, abonelik ücreti, vergi ve muhasebe yazışmaları. |
| İşbirliği | ⭐ | Sponsorluk, işbirliği, ortaklık, reklam/marka teklifleri, gerçek kişi veya şirketten iş teklifi. |
| Yazışma | | Cevap bekleyebilecek kişisel/iş yazışması, destek yanıtı. |
| Hesap | | Üyelik, hoş geldin, sözleşme, doğrulama, tek kullanımlık kod/giriş bağlantısı; güvenlik uyarısı olmayanlar. |
| Geliştirici | | GitHub/Vercel benzeri araçlardan depo, issue, PR, dağıtım bildirimleri. |
| Sosyal | | Sosyal platform davet, öneri, etkinlik ve özetleri. |
| Bülten | | Bülten, ürün duyurusu, kampanya, pazarlama ve tanıtım. |

Sınıflandırıcı promptu adları, tanımları ve önem bayraklarını listeler. Gönderen,
konu ve ön izleme birlikte değerlendirilir; yalnız anahtar kelime eşleşmesi
istenmez. İki kategori uyduğunda önemli kategori kazanır. Her sonuçta tek bir
tanımlı ad veya hiçbir kategori uymuyorsa boş dize istenir. Mail metni JSON
satırı içinde veri olarak taşınır; içindeki talimatlara uyulmaması açıkça yazılır.

Gerçek CLI çıktısının `structured_output` ve `result` biçimleri korunur. JSON
şemasına isteğe bağlı `kategori` alanı eklendi. `classify` yine iki değer döndürür:
`predictions, errors`; her tahmin yine `(karar, ozet)` ikilisidir. Sözlük alt sınıfı
`Predictions.categories`, mail kimliği → kategori adını taşır. Tanımlı olmayan
adlar, yanlış alan tipleri ve eksik kategori boş kabul edilir. Yinelenen kimlik,
geçersiz karar veya geçersiz özet o mailin sonucunu geçersiz kılar; diğer geçerli
sonuçlar korunur. Parçalar mevcut 25 mail sınırıyla çalışır.

Veritabanında yeni `mails.content_category` sütunu kullanılır. Eski `category`
sütunu Gmail sekmesini göstermeye devam eder. `db.connect`, mevcut şemayı
`BEGIN IMMEDIATE` altında kontrol edip eksik sütunu `ALTER TABLE ... ADD COLUMN`
ile ekler. Geçiş tekrarlanabilir; mail, karar, kural ve meta kayıtları korunur.
Eski şema testi değişen yeni şemadan türetilmeden, eski SQL ile oluşturulur.

Kategoriler açıkken, gönderen kuralına girenler dahil kategorisiz bütün bekleyen
mailler modele gönderilir. Önemli kategori, gönderen kuralını ve tarz yetkisini
geçersiz kılar; yalnız `onemli` kararı ve `kategori` kaynağı üretir. Gmail'de
yıldız ve `Ajan/Önemli` eklenir; gelen kutusu ve okunma durumu değiştirilmez.
Özette `kategori: <ad>` ve geri alma düğmesi bulunur. Mail düğmeli kart olarak
gelir, kartın sonunda `🏷 <ad>` satırı görünür. Kısa yedek kart da bu satırı taşır.
Kategori kararları mevcut tam metin takibini başlatır; dört parça sınırı, kaçırma,
sessizlik, gönderim aralığı ve hata/erteleme davranışı korunur. Uzun kategori
özetleri Telegram sınırını aşmadan bölünür.

Gmail etiketi `Kategori/<ad>` olarak hesap başına mevcut önbellekle bulunur veya
oluşturulur. Renkli oluşturma Gmail 400 reddi alırsa renksiz oluşturma denenir.
Kategori etiketini uygulamak tek bir `messages.modify` çağrısıyla yalnız bir
`addLabelIds` ekler. INBOX, UNREAD, STARRED ve Ajan/* etiketlerine bu çağrı
dokunmaz. Mevcut sınırlı Google kitaplık tekrarları korunur.

## Hata ve güvenlik senaryoları

Her satır `tests/test_kategoriler.py` içinde test edilir; mevcut 270 test de
değiştirilmeden çalışır.

| Senaryo | Davranış | Test |
| --- | --- | --- |
| Sınıflandırıcı kapalı, çöp/arşiv kuralı veya tarz yetkisi var | Otomatik işlem yapılmaz. Mail normal düğmeli kart olarak gelir; uyarı gönderilir. Hata açıklamasındaki URL/token aktarılmaz. | `test_no_usable_category_never_trashes_or_archives`: `down`, kural/tarz, çöp/arşiv |
| Bozuk çıktı, eksik mail sonucu, geçersiz karar | O mail için otomatik işlem yok; kart ve uyarı var. Geçerli diğer sonuçlar korunur. | Aynı testin `malformed`, `missing`, `bad_action` örnekleri; `test_chunk_categories_partial_results_and_duplicate_invalidation` |
| Bilinmeyen/uydurma kategori; boş kategori; yanlış tip; alan yok | Kategori boş kabul edilir, kayıt ve etiket üretilmez; çöp/arşiv uygulanmaz, kart ve uyarı gelir. Boş kategori için de temkinli kart yolu kullanılır. | Aynı testin `unknown`, `empty`, `bad_type`, `no_field` örnekleri |
| Mail metni modeli yönlendirmeye çalışıyor | Yönergeler veri olan JSON dizesi içinde kalır, sistem promptundaki kategori listesine dönüşmez. Modelden gelse bile uydurma ad reddedilir. | `test_prompt_injection_is_json_data_and_categories_are_owner_defined` |
| GitHub gönderenine çöp kuralı var, yeni güvenlik maili geliyor | Model yine çağrılır; `onemli/kategori` uygulanır. Yıldız ve etiket, geri alınabilir özet, kart ve tam metin gelir. Model çöp demiş olsa bile kategori kazanır. | `test_important_category_overrides_github_trash_rule_and_style` |
| Önemli kategori, hesap istemcisi yok | Kategori yerelde kayıtlıdır; Gmail işlemi ve karar kaydı yoktur. Kart ve hesabın bağlı olmadığı uyarısı gelir. | `test_missing_account_important_category_card_and_warning` |
| Önemli kategori için Gmail yıldız/önemli işlemi başarısız | Karar kaydedilmez; kategori kaydı korunur. Kart ve uyarı gelir, tam metin takibi başlatılmaz. | `test_category_decision_apply_failure_keeps_card_no_decision` |
| Kategori etiketi oluşturma veya uygulama başarısız | Tur devam eder, kategori yerelde korunur, kart gelir ve mail başına bir uyarı verilir. Önemli kategori yine yıldız işlemini deneyebilir. Önemli olmayan kategori için kural/tarzla mail gizlenmez. | `test_category_label_failure_continues_and_warns_once`, `test_label_failure_does_not_cancel_category_importance`, `test_nonimportant_label_failure_also_keeps_rule_mail_as_card` |
| Etiket hatasından sonra Telegram kartı da geçici hata alıyor | Kart yolu sonraki turda korunur. `category_label_failed:<id>` meta bayrağı, devam ederken çöp/arşiv kuralının kartı gizlemesini önler. Uyarı bekleyen uyarı kaydıyla teslim edilir. | `test_label_failure_card_fallback_survives_telegram_outage` |
| Telegram kategori kararından sonra kapalı | Gmail kararı SQLite'ta kayıtlıdır; sonraki tur bildirilmemiş özeti ve kartı tamamlar. Model, yıldız ve kategori etiketi tekrar uygulanmaz. Karttan sonra tam metin gelir. | `test_telegram_down_resumes_category_summary_and_card_without_reapplying`: özet ve kart aşamaları |
| Kategori kararını geri alma | Yalnız o mailde STARRED ve Ajan/Önemli kaldırılır; Kategori etiketi ve yerel kategori kalır. Karar undone olur. Hiçbir kural/yetki silinmez veya sıfırlanmaz. Kart henüz teslim edilmemişse, sonraki turda kategori kararı tekrar uygulanmaz. | `test_category_undo_keeps_category_rule_and_style_authority`, `test_real_important_apply_and_undo_keep_category_and_read_state` |
| Kategori kararlarının öğrenmeye etkisi | Sahibin yıldızı sayılmaz; gönderen kuralı, tarz doğruluğu ve öğrenme örneklerine girmez. Sahibin mevcut karar serisini de bölmez. | `test_category_decisions_do_not_train_owner_rules_or_style` |
| Eski veritabanı | Sütun bir kez eklenir, yeniden açılışta tekrar eklenmez; eski veriler, Gmail sekmesi ve sonradan kaydedilen kategori korunur. | `test_literal_legacy_schema_migration_is_idempotent_and_preserves_data` |
| Kategori listesi yok veya boş | Eski prompt birebir kullanılır; gönderen kuralı yine modeli atlar, bugünkü işlem yolu sürer. | `test_no_categories_exact_old_prompt_and_rule_bypass`; bütün mevcut testler |
| Backfill sırasında mail Gmail'den silinmiş, 404 geliyor | Sessizce atlanır; kategori kaydedilmez, sayıma eklenmez, uyarı/log oluşturulmaz. Diğer mailler işlenir. | `test_backfill_deleted_gmail_message_skipped_quietly` |
| Backfill bir turla veya başka backfill ile çakışıyor | Aynı `tur.lock` alınamazsa config, veritabanı, model ve istemcilere erişmeden temizce çıkar. Kilit sınıflandırma ve etiketleme boyunca tutulur, bitince bırakılır. | `test_backfill_overlapping_run_exits_before_any_config_or_service_access`, `test_backfill_chunks_and_lock_spans_classifier_and_label_mutations` |
| Backfill model veya etiket hatası | Başarılı kayıtlar korunur; başarısız mailin kategorisi boş kalır ve sonraki komutta denenebilir. Terminalde güvenli uyarı/sayı, hata çıkış kodu 1 verilir. | `test_backfill_failure_retry_without_side_effects` |

Normal turda etiket hatası için ek bir uygulama tekrar kuyruğu kurulmadı: yerel
kategori korunur, bir uyarı teslim edilir. Teslim edilmiş mail sonraki turda
yeniden işlenmez. `kategorile` de yalnız yerel kategorisi boş mailleri seçer;
bu yüzden yerel kategorisi kaydedilmiş ama Gmail etiketi başarısız olmuş mailin
etiketini onarmaz. Bu, tasarımın izin verdiği tek uyarı seçeneğidir.

Prompt yönlendirme testi veri/talimat ayrımını ve tanımlı ad kontrolünü doğrular.
Gerçek model çalıştırılmadığı için anlamsal sınıflandırma doğruluğu veya modele
karşı bütün yönlendirme saldırılarının etkisizliği iddia edilmez.

## Komutlar ve görünürlük

Operatörün kullanabileceği komutlar (bu çalışmada canlı ortamda çalıştırılmadı):

```sh
.venv/bin/python -m mail_ajani kategori-kur
.venv/bin/python -m mail_ajani kategorile
```

`kategori-kur`, yalnız `kategoriler` anahtarı yoksa varsayılan listeyi yazar ve
listeyi gösterir. Mevcut özel listeyi veya boş listeyi hiçbir zaman değiştirmez.
İkinci çağrı dosyayı yeniden yazmaz. Renkler varsayılan listede yoktur; isteyen
operatör geçerli Gmail paletinden `renk` ekleyebilir.

`kategorile`, veritabanında kategorisi boş ve hesabı bağlanabilen eski mailleri
25'lik parçalarla sınıflandırır. Gönderilmiş veya sahibin karar verdiği eski
mailler de dahil edilir. Yalnız Kategori etiketini uygular ve başarıdan sonra
yerel kategoriyi kaydeder; kategori başına yeni başarı sayısını yazdırır.
Karar, tahmin, özet, gönderim zamanı, Telegram kimliği ve tur meta durumu
değiştirilmez. Telegram kullanılmaz; yıldız, çöp, arşiv veya tam metin işlemi
yoktur. Yeniden çalıştırmada başarıyla kategorilenmiş mailler atlanır.
Sıfır uyarı/hata durumunda çıkış kodu 0; başarısız kategori/etiket veya bağlantı
uyarısı durumunda 1'dir. Gmail 404 sessiz atlamadır, hata çıkışına yol açmaz.

`/kurallar`, mevcut kural ve tarz yetkilerinin ardından Kategoriler bölümünü
gösterir. Her zaman önemli kategoriler ⭐ ile işaretlenir. Kategoriler için
silme düğmesi yoktur; mevcut kural/yetki düğmeleri aynen korunur.

## Değişen dosyalar

- `mail_ajani/config.py`: varsayılan liste ve yapılandırma doğrulaması.
- `mail_ajani/classifier.py`: kategori promptu, isteğe bağlı şema alanı, güvenli ad kontrolü, uyumlu sonuç genişletmesi.
- `mail_ajani/db.py`: yeni sütun, yerinde/idempotent geçiş, kategori okuma/yazma ve geri alınmış kategori kontrolü.
- `mail_ajani/gmail.py`: mevcut etiket önbelleğiyle kategori etiketi ve renk reddinde yedek oluşturma.
- `mail_ajani/tur.py`: bütün kategorisiz bekleyenleri sınıflandırma, önem önceliği, başarısız yanıt/etiket bariyeri, kategori tam metni.
- `mail_ajani/learning.py`: kategori geri almasının kural ve yetkilere dokunmaması.
- `mail_ajani/render.py`: kart kategori satırı, özette kaynak, güvenli özet bölme ve kategori listesi.
- `mail_ajani/dinleyici.py`: `/kurallar` için güncel kategori listesini okuma.
- `mail_ajani/cli.py`: `kategori-kur` ve kilitli `kategorile` komutları.
- `tests/helpers.py`: sahte kategori etiketleme; üretilmiş eğitim maili kimlikleri için ayrı `fixture-` alanı. Yeni testler ortak sayacı g900'e taşıyınca mevcut testte ortaya çıkan sahte kimlik çakışması giderildi; doğrulamalar değiştirilmedi.
- `tests/test_kategoriler.py`: 81 yeni test örneği.
- `README.md`: komutlar ve özelliğin açılma koşulu.
- `docs/ozellik-kategoriler.md`: bu rapor.

Mevcut `docs/ozellik-tam-metin.md` ve diğer önceki değişiklikler geri alınmadı.
Tam metin kodunun yalnız kapsamına `kategori` kaynağı eklendi; mevcut 61 tam
metin testini de içeren eski paket korunuyor.

## Doğrulama

Komut:

```sh
MAIL_AJANI_HOME=$(mktemp -d) MAIL_AJANI_LOGS=$(mktemp -d) .venv/bin/pytest -q
```

Son çıktı:

```text
........................................................................ [ 20%]
........................................................................ [ 41%]
........................................................................ [ 61%]
........................................................................ [ 82%]
...............................................................          [100%]
351 passed in 0.83s
```

Testler geçici uygulama/log dizinlerinde ve sahte servislerle çalıştırıldı.
Google/Telegram bağlantısı, gerçek Claude CLI çağrısı, paket kurulumu, git,
alt ajan veya Agent çağrısı yapılmadı. Launchd yüklenmedi veya yeniden
başlatılmadı. Canlı `~/Library/Application Support/mail-ajani` verisi okunmadı
veya değiştirilmedi. Kategori etiketleme testleri kalıcı silme, okunma durumu
değişikliği ve kategori çağrısında diğer etiketlere müdahale olmadığını doğrular.
Gizli bilgi saklama düzeni Keychain olarak korunur; yeni kod hata açıklamalarını
ve mail gövdelerini loglara taşımaz.

Sahibin karar vermesi gereken açık tasarım konusu yok. Etkinleştirme ve eski
mailleri etiketleme komutlarını canlı ortamda çalıştırmak operatöre bırakıldı;
bu çalışma yalnız kodu ve izole doğrulamayı tamamladı.
