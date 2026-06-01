# Baselines for Confluence — app-specific performance tests

Bu toolkit, **Baselines for Confluence** (OBSS) eklentisinin app-specific yük
testlerini `standalone_extension` altında çalıştıracak şekilde hazırlandı.

## Entegre edilen / değişen dosyalar

| Dosya | Rol |
|---|---|
| `app/jmeter/confluence.jmx` | `standalone_extension` içine 6 ağırlıklı Baselines aksiyonu eklendi. Orijinali `app/jmeter/confluence.jmx.orig` olarak yedeklendi. |
| `app/util/confluence/prepare_baseline_data.py` | Baseline seed scripti. `confluence_prepare_data.py` gibi `CONFLUENCE_SETTINGS`'ten config okur. |
| `app/confluence.yml` (`services` → `prepare`) | Seed scripti `confluence_prepare_data.py`'den hemen sonra **otomatik** çalışacak şekilde eklendi. |
| `app/confluence.yml` (`standalone_extension`) | Ağırlık (plumbing zaten mevcut, sadece değeri ayarla). |
| `app/datasets/confluence/baselines.csv` | Seed çıktısı (prepare aşamasında üretilir); JMeter `bsl_*` değişkenlerini buradan okur. |

## Eklenen app-specific aksiyonlar

`standalone_extension` her tetiklendiğinde, ağırlıklı olarak aşağıdaki
aksiyonlar çalışır (her biri ayrı TransactionController → raporda ayrı etiket):

| Transaction | Endpoint(ler) | Ağırlık |
|---|---|---|
| `bsl_view_baseline` | POST baselineviewerservlet | %30 |
| `bsl_browse` | baseline.action + renderTreeComponent + gettoplevelpagesforspace + getsubpagesofpage + getBelongingBaselines | %30 |
| `bsl_compare_baselines` | POST baselinecompareservlet | %15 |
| `bsl_create_delete` | POST createBaseline (benzersiz isim) → POST baselinedeleteservlet | %10 |
| `bsl_export_pdf` | createPdfForBaseline → getProcess poll | %10 |
| `bsl_export_csv` | createCsv | %5 |

## Ön koşullar

1. Toolkit'in normal `prepare_data`'sı çalışmış olmalı (`pages.csv`, `users.csv` dolu).
2. Test instance'ında **geçerli bir Baselines lisansı** olmalı.
3. Instance **read-only modda OLMAMALI** (create/delete/compare aksiyonları aksi halde 403).
4. Baselines admin izin grupları **kısıtlanmamış** olmalı. Varsayılan (hiç grup
   seçilmemiş) durumda tüm kullanıcılar yetkilidir; gruplar seçildiyse test
   kullanıcılarını o gruplara ekle.

## Adımlar

### 1. Ağırlığı aç

`app/confluence.yml` içinde (zaten mevcut, varsayılan kapalı):

```yaml
    standalone_extension: 0   # By default disabled
```

değerini yük payına göre ayarla — yeni aksiyonları izole doğrulamak için `100`,
core Confluence aksiyonlarıyla gerçekçi karışık koşu için `5`-`10`. Aksiyonlar
arası iç dağılım (30/30/15/10/10/5) `confluence.jmx` içinde sabittir.

### 2. Testi çalıştır

Toolkit'in normal akışıyla (örn. `bzt confluence.yml`). Başka bir şey yapmana
gerek yok:

- `prepare` aşamasında `confluence_prepare_data.py` çalışır (pages.csv vb. üretir),
- hemen ardından `prepare_baseline_data.py` **otomatik** çalışır ve her space için
  iki `version-based` baseline (`perf-seed-1`, `perf-seed-2`) oluşturup
  `app/datasets/confluence/baselines.csv` dosyasını yazar:
  ```
  bsl_space_key,bsl_space_id,bsl_page_id,bsl_baseline1,bsl_baseline2
  ```
- sonra JMeter koşusu başlar; raporda `bsl_*` transaction etiketlerini göreceksin.

> `standalone_extension: 0` iken seed scripti kendini **atlar** (hiçbir şey
> yapmadan çıkar), böylece app testi çalıştırmadığın koşularda prepare aşamasını
> etkilemez veya hata vermez.

### (Opsiyonel) Manuel/elle çalıştırma — debug için

`app/` dizininden, toolkit ortamı (PYTHONPATH=app, kurulu requirements) ile:

```bash
python util/confluence/prepare_baseline_data.py --spaces-limit 40 --pages-per-baseline 3
```

Bağlantı ve kimlik bilgileri `confluence.yml`'den (`CONFLUENCE_SETTINGS`) okunur —
ayrıca argüman gerekmez. Yalnızca iki baseline'ı da başarıyla oluşturulan
space'ler CSV'ye yazılır; var olan isimler "already exists" olarak yeniden
kullanılır (idempotent).

## Notlar / sınırlar

- **Seeding modu:** `version-based`, space başına az sayfa → küçük baseline'lar;
  PDF export boyut limitine takılıp 400 dönmez.
- `bsl_create_delete` her çalıştığında benzersiz isimli baseline oluşturup hemen
  siler; veri sınırsız büyümez.
- Async aksiyonlar (PDF export) sınırlı sayıda ilerleme poll'u yapar; askıda kalmaz.
- App-specific aksiyonlar garanti seed edilmiş space'leri kullanmak için
  `baselines.csv`'den okur — rastgele `pages.csv` space'ini değil.
- Orijinal JMeter planını geri yüklemek için: `app/jmeter/confluence.jmx.orig`
  dosyasını `confluence.jmx` olarak kopyala (ya da git'ten geri al).
