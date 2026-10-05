# Tur-6 düzeltme raporu

5 Ekim 2026 · Yerel, izole doğrulama · Sonuç: **392 test geçti**.

`denetim-tur-6.md` bütünüyle, `ozellik-kategoriler.md` ve `ozellik-tam-metin.md`
okundu. Her bulgu düzenleme öncesinde güncel kaynakla karşılaştırıldı.
Başlangıç paketi **351 passed in 0.87s** verdi. Dört istenen bulgu kaynakta
geçerliydi; **İTİRAZ yok**. Eski kaynak/test kopyaları geçici dizinde tutularak
değişiklikler `diff` ile incelendi; git çalıştırılmadı.

## Bulguların durumu ve kanıt

| Bulgu | Durum | Düzenleme öncesi kanıt ve yapılan düzeltme |
| --- | --- | --- |
| **E6-1** | **Düzeltildi** | `classifier.build_prompt` açıkça “hiçbiri uymuyorsa boş dize ver” diyordu; `SCHEMA` içinde `kategori` zorunlu değildi ve enum yoktu. `DEFAULT_KATEGORILER` sekiz girdiydi; `tur.run_tur` geçersiz kategori uyarısını mail döngüsünde ekliyordu. Dokuzuncu varsayılan `Diğer` eklendi; tanımı `yukarıdakilerin hiçbirine girmeyen mailler`, önemi `False`. `get_categories`, geçerli ve boş olmayan özel listede de `Diğer` sağlar; operatörün verdiği `Diğer` önemliyse yalnız çalışma kopyasında önemsiz yapılır. Operatör ayarı değiştirilmez. Prompt tam bir tanımlı ad ister ve başka kategori uymuyorsa `Diğer` seçtirir. Kategoriler açıkken şema, `kategori` alanını zorunlu ve tanımlı adların enum'u yapar. Kapalıyken prompt ve serileştirilmiş şema önceki hâliyle birebirdir. `Diğer` normal etiket ve kural/tarz yoluna girer. Eksik, bozuk, boş veya bilinmeyen yanıt koruması sürer ve tek özet uyarısı üretir; sınıflandırıcı hataları da bu tek satırda birleştirilir. |
| **Ö6-1** | **Düzeltildi** | `get_categories` geçersiz ayarda `ValueError` veriyor, `run_tur` bunu yakalamadan çağırıyordu; `save_config` hedef dosyaya doğrudan `write_text` yapıyordu. Artık tur geçersiz kategorileri **o çalışma için kapalı** sayar, alan sorununu belirten güvenli Türkçe uyarıyı dilim başına bir kez verir ve olağan teslimatı sürdürür. Model çağrısına açıkça `kategoriler=[]` verilmesi, sınıflandırıcının bozuk ayarı yeniden yüklemesini önler. Aynı dilimde Telegram kesintisi veya sorun türünün değişmesi ikinci ayar uyarısı oluşturmaz. `/kurallar` da aynı ayarda çökmez. Ayar, aynı dizinde geçici dosya, flush/fsync ve `os.replace` ile atomik yazılır; hata hâlinde eski dosya korunur ve geçici dosya temizlenir. |
| **Ö6-2** | **Bırakıldı — sahibin kararı** | İstenen kapsam gereği Güvenlik maillerinin mevcut tam metin gönderimi korunur. Kategoriye özel içerik kısıtlaması eklenmedi. |
| **Ö6-3** | **Düzeltildi** | `_label_id` önbelleği ve liste araması tam adla eşleşiyordu; 409 için yenileme yolu yoktu. Etiket anahtarları artık `NFC(name).casefold()` ile karşılaştırılır. Oluşturma 409 alırsa liste **bir kez** yenilenir ve eşleşen kimlik kullanılıp önbelleğe alınır. Renk 400 reddinden sonraki renksiz oluşturma 409 alırsa da aynı yol çalışır. Yenilenen listede eşleşme yoksa hata korunur; sınırsız tekrar yoktur. |
| **Ö6-4** | **Düzeltildi** | `_body_text` yalnız `body.data` okuyordu; `fetch_body` yalnız `messages.get` çağırıyor, boş dönüş turda sessizce atlanıyordu. Dosya/ek olmayan `text/plain` ve `text/html` parçalarında inline veri yoksa `users.messages.attachments.get(userId='me', messageId=..., id=...)`, `num_retries=3` ile okunur. Charset, HTML temizleme ve düz metin tercihi korunur. Bir parça alınamazsa okunur alternatif kullanılabilir. Ek olmayan gövdede veri, boyut veya ek kimliği bulunduğu hâlde metin elde edilemiyorsa `BodyUnreadableError` mevcut “tam metin okunamadı; Gmail'den kontrol edin.” uyarı yoluna girer. Gerçekten gövdesiz mail sessiz kalır; dosya ekleri ve ek alt ağaçları hâlâ atlanır. |
| **Açık sorular** | **Bırakıldı — kapsam dışı** | Gerçek Gmail etiket görünümü, model davranışı ve önceki turların canlı ortam soruları araştırılmadı. launchd veya canlı servis denemesi yapılmadı. Şemanın zorunlu alan düzeltmesi E6-1 kapsamında uygulandı; gerçek model çalıştırılmadı. |

Ö6-1 için denetim raporundaki “açık ama değerlendirilemedi” önerisi yerine bu
düzeltme talebindeki açık sözleşme uygulandı: geçersiz ayar **yapılandırılmamış**
sayılır. Bu durumda mevcut gönderen kuralları olağan biçimde çalışabilir.
Kategori nedeniyle üretilen karar ise hâlâ yalnız `onemli/kategori` olabilir;
çöp/arşiv ancak mevcut `rule` veya `style` yetkisinden gelir.

## Regresyon kanıtları

Yeni `tests/test_round6.py` toplam **41 test örneği** ekler:

- `test_eight_unmatched_mails_all_get_diger_without_warning`: sahte modelle sekiz
  kargo maili, sekiz yerel `Diğer`, sekiz kategori etiketi ve sekiz kart;
  **sıfır uyarı**, sıfır otomatik karar. Prompt ve gerçek komuta verilen zorunlu
  enum şeması da doğrulanır. Bu test gerçek modelin anlamsal doğruluğunu iddia etmez.
- `test_diger_allows_existing_sender_and_style_authorities`: `cop`, `arsiv` ve
  `onemli` için kural ve tarz kaynakları; `Diğer` mailinde çöp gönderen kuralı
  uygulanır, uyarı oluşmaz ve kararın kaynağı kategori olmaz.
- `test_fallback_is_added_without_mutating_operator_config` ve
  `test_no_categories_schema_is_byte_identical_to_before_round6`: özel listede
  zorunlu önemsiz fallback, ayarın korunması, boş listenin kapalı kalması ve
  dondurulmuş eski şemayla bayt eşitliği. Mevcut
  `test_no_categories_exact_old_prompt_and_rule_bypass` eski promptu ve modeli
  atlayan kural davranışını doğrulamaya devam eder.
- `test_many_unusable_answers_keep_protection_and_only_one_warning` ve
  `test_unusable_category_warning_is_single_across_resumed_delivery`: sekiz
  eksik/boş/bilinmeyen/bozuk/başarısız yanıt, sıfır çöp/arşiv, tüm kartlar ve
  yalnız bir kategori uyarısı; Telegram kesintisi sonrası da tekrarsız teslim.
- `test_invalid_config_delivers_using_unconfigured_contract_once_per_slot`:
  liste/nesne/ad/tanım/önem/renk tip sorunları, boş ad ve yinelenen ad; normal
  kart, sorunu belirten tek uyarı, yeni dilimde tek yeni uyarı ve çalışan
  `/kurallar`. Kesintiyle devam ve kapalı modda gönderen kuralının korunması
  ayrı testlerle kapsanır.
- `test_save_config_replaces_complete_temp_atomically_and_preserves_old_on_failure`:
  değiştirme anına kadar okuyucu eski geçerli JSON'u görür; geçici dosya tam
  yeni JSON'dur ve aynı dizindedir. Başarıda yeni ayar, hatada eski ayar kalır;
  her iki durumda geçici dosya artığı yoktur.
- `test_label_matches_case_and_nfc_without_creation`,
  `test_409_refreshes_once_then_reuses_existing_label` ve
  `test_409_without_matching_label_stops_after_one_refresh`: harf/NFD eşleşmesi,
  409 ve 400→409, ikinci mailde önbellek, yalnız bir yenileme ve eşleşme yoksa
  sınırlandırılmış hata. Uygulama gövdesi yalnız `addLabelIds` taşır.
- `test_attachment_body_is_fetched_read_only_with_charset_and_bounded_retries`:
  düz/HTML metin, ISO-8859-9, salt okunur istekler ve her okumada üç kütüphane
  tekrarı. Gerçek dosya eklerinin atlanması ve okunur HTML alternatifi ayrıca
  test edilir.
- `test_present_unreadable_autoimportant_body_emits_existing_warning_once`:
  veri alınamayan ek kimliği, okuma hatası, yalnız boyut, görünmez HTML ve yalnız
  inline resim; karttan sonra mevcut uyarı bir kez gelir, sonraki turda gövde
  tekrar okunmaz. Başarılı ayrı kimlikli gövdenin karttan sonra gönderilmesi,
  kaçırılması ve DB/loga yazılmaması da uçtan uca sahte servisle doğrulanır.

## Değişen mevcut doğrulamalar

Hiçbir doğrulama testi geçirmek için zayıflatılmadı. Yeni sözleşmenin değiştirdiği
beklentiler şunlardır:

1. `tests/test_kategoriler.py::test_defaults_include_owner_intent`: sekiz ad
   bekleyen listeye dokuzuncu `Diğer` eklendi. Önemli kategorileri tam olarak
   `Güvenlik`, `Fatura`, `İşbirliği` bekleyen doğrulama aynen kaldı.
2. `test_real_cli_fixture_shape_and_legacy_return_shape`: kategori şemasında
   `kategori not in required` yerine `kategori in required`; ayrıca enum'un
   çalışma listesindeki bütün adlarla tam eşitliği eklendi.
3. `test_no_usable_category_never_trashes_or_archives`: uyarı sayısı `>= 1`
   yerine **`== 1`** oldu. Etiket/işlem/karar yokluğu, kart teslimi ve gizlilik
   doğrulamaları değişmedi.
4. `tests/test_gmail.py::test_fetch_body_returns_empty_when_no_readable_text`:
   gerçekten gövdesiz ve dosya eki olan örneklerde `== ''` korunur. Inline
   resim, boşluk içeren metin, alınamayan `attachmentId` ve script/style-only
   HTML örnekleri yeni `test_fetch_body_signals_present_but_unreadable_body`
   testine taşındı; aynı örnekler artık **`BodyUnreadableError`** bekler ve
   değiştirme/çöp/silme/etiket çağrısı olmadığını doğrular. Ayrı kimlikli okunur
   gövde yeni testlerde metnin tam eşitliğiyle sınanır. Eski örnekler atılmadı.

`tests/test_tur.py::test_empty_body_has_no_followup_or_warning` değiştirilmedi:
gövdenin varlığına ilişkin veri bulunmayan boş dönüşte eski davranış sürer.

## Değişen dosyalar

- `mail_ajani/config.py`: dokuzuncu varsayılan, fallback garantisi, güvenli alan
  hata açıklamaları ve atomik ayar yazımı.
- `mail_ajani/classifier.py`: zorunlu kategori promptu ve çalışma listesiyle
  üretilen required/enum şeması; kapalı mod korunur.
- `mail_ajani/tur.py`: geçersiz ayarda kapalı mod ve dilimlik uyarı, bozuk
  kategori yanıtlarında tek özet satırı.
- `mail_ajani/gmail.py`: NFC/casefold etiket anahtarları, 409 yenilemesi,
  ayrı kimlikli gövde okuması ve okunamayan mevcut gövde sinyali.
- `mail_ajani/dinleyici.py`: geçersiz kategoride `/kurallar` yanıtının korunması.
- `tests/test_kategoriler.py`: yukarıda listelenen yeni sözleşme doğrulamaları.
- `tests/test_gmail.py`: gövde mevcut ama okunamaz örneklerin yeni beklentisi.
- `tests/test_round6.py`: 41 regresyon örneği.
- `docs/duzeltme-tur-6.md`: bu rapor.

## Test komutu ve çıktı kuyruğu

Son tam paket komutu (iki yol da geçici dizindir):

```sh
MAIL_AJANI_HOME=/private/tmp/mail-ajani-round6-final-home MAIL_AJANI_LOGS=/private/tmp/mail-ajani-round6-final-logs .venv/bin/pytest -q
```

```text
........................................................................ [ 18%]
........................................................................ [ 36%]
........................................................................ [ 55%]
........................................................................ [ 73%]
........................................................................ [ 91%]
................................                                         [100%]
392 passed in 0.97s
```

Tüm komutlarda `MAIL_AJANI_HOME` ve `MAIL_AJANI_LOGS` geçici dizinlere ayarlandı.
Canlı `~/Library/Application Support/mail-ajani` okunmadı/yazılmadı. Ağ,
Telegram/Google bağlantısı, gerçek Claude CLI, pip install, git, alt ajan/fork/
Agent ve launchd yükleme/yeniden başlatma kullanılmadı. Gizli bilgi düzeni
Keychain olarak kaldı. Yeni kod mail gövdesini, token veya URL'yi loglamaz.
`messages.delete` eklenmedi; gövde okumaları ve kategori etiketleri okunma
durumunu değiştirmez. Dağıtım veya canlı kategori kurulumu yapılmadı.
