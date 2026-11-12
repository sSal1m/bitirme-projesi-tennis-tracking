"""Generate train_colab.ipynb.

Building the notebook from Python guarantees valid JSON and stable cell ids.
Run from the project root:

    python scripts/make_colab_notebook.py
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

NOTEBOOK = Path(__file__).resolve().parents[1] / "train_colab.ipynb"


def new_id() -> str:
    """nbformat 4.5 requires a unique id on every cell."""
    return uuid.uuid4().hex[:8]


def md(text: str) -> dict:
    lines = text.strip("\n").splitlines(keepends=True)
    return {"cell_type": "markdown", "id": new_id(), "metadata": {}, "source": lines}


def code(text: str) -> dict:
    lines = text.strip("\n").splitlines(keepends=True)
    return {
        "cell_type": "code",
        "id": new_id(),
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": lines,
    }


CELLS = [
    md(
        """
# Duvar Tenis — RF-DETR Nano pilot eğitimi (Colab)

Bu notebook **pilot** eğitimidir: önce 5 epoch ile boru hattının uçtan uca çalıştığını kanıtlar, sonra `EPOCHS` değerini artırarak tam eğitime geçersin.

**Önce yapman gerekenler**

1. `Runtime → Change runtime type → T4 GPU` seç.
2. Sağdaki dosya panelinden `train.zip` ve `valid.zip` dosyalarını yükle (Colab'ın `/content` klasörüne).
3. `Run all` çalıştır.

Zip dosyalarını bu not defterinin yanındaki **Dosyalar** panelinden yükle. Arşivleri açarken görsellerin ve `_annotations.coco.json` dosyasının kök dizinde olduğu doğrulanır; iç içe klasör varsa hata verir.

**Uyarı:** Bu notebook kendi etiketlediğin kareleri eğitir. Eğitim kaybının düşmesi saha doğruluğu değildir; ölçüm için `scripts/evaluate.py` ve ayrı test videosu gerekir.
"""
    ),
    code(
        """
# 1) Google Drive bağlantısı
from google.colab import drive
import os
import shutil
from pathlib import Path

drive.mount('/content/drive')
DRIVE_ROOT = Path('/content/drive/MyDrive/duvar-tenis')
(DRIVE_ROOT / 'runs').mkdir(parents=True, exist_ok=True)
print('Drive hazir:', DRIVE_ROOT)
"""
    ),
    code(
        """
# 2) GPU kontrolü
import torch

if not torch.cuda.is_available():
    raise SystemExit(
        'GPU bulunamadi. Runtime -> Change runtime type -> T4 GPU sec, '
        'ardindan bu hucreyi yeniden calistir.'
    )

print('GPU:', torch.cuda.get_device_name(0))
print('CUDA:', torch.version.cuda)
print('VRAM: %.1f GB' % (torch.cuda.get_device_properties(0).total_memory / 1024**3))
"""
    ),
    code(
        """
# 3) Kurulum
import subprocess
import sys

print('Python:', sys.version.split()[0])
subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', 'rfdetr==1.11.0'], check=True)
subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', 'rfdetr[train,loggers]'], check=True)
import rfdetr
print('rfdetr surumu:', getattr(rfdetr, '__version__', 'bilinmiyor'))
"""
    ),
    code(
        """
# 4) train.zip ve valid.zip dosyalarını bul
CONTENT = Path('/content')


def find_zip(name):
    for base in (CONTENT, CONTENT / 'sample_data'):
        if not base.exists():
            continue
        for candidate in base.rglob(name):
            if candidate.is_file():
                return candidate
    return None


archives = {}
for name in ('train.zip', 'valid.zip'):
    found = find_zip(name)
    if found is None:
        raise SystemExit(
            f'{name} bulunamadi. Dosyalar panosunden {name} dosyasini yukleyip '
            'sonra bu hucreyi yeniden calistir.'
        )
    archives[name] = found
    print(name, '->', found, '(%.1f MB)' % (found.stat().st_size / 1024**2))
"""
    ),
    code(
        """
# 5) Arşivleri aç: RF-DETR'in beklediği Roboflow düzeni
#    /content/wall/train/_annotations.coco.json
#    /content/wall/valid/_annotations.coco.json
import zipfile

WALL = Path('/content/wall')
if WALL.exists():
    shutil.rmtree(WALL)
WALL.mkdir(parents=True)

for name, target in (('train.zip', 'train'), ('valid.zip', 'valid')):
    destination = WALL / target
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archives[name]) as archive:
        archive.extractall(destination)
    coco = destination / '_annotations.coco.json'
    images = list(destination.glob('*.jpg'))
    if not coco.is_file():
        raise SystemExit(f'{name} icinde _annotations.coco.json yok (kok dizinde olmali).')
    if not images:
        raise SystemExit(f'{name} icinde JPG yok.')
    print(f'{target}: {len(images)} JPG + {coco.name} (kok dizinde)')
"""
    ),
    code(
        """
# 6) Veri bütünlüğü kontrolü
import json

for split in ('train', 'valid'):
    folder = WALL / split
    doc = json.loads((folder / '_annotations.coco.json').read_text('utf-8'))
    names = {img['file_name'] for img in doc['images']}
    on_disk = {p.name for p in folder.glob('*.jpg')}
    missing = names - on_disk
    if missing:
        raise SystemExit(
            f"{split}: COCO dosyasinda {len(missing)} kare eksik, ilk: {sorted(missing)[0]}"
        )
    categories = sorted((c['id'], c['name']) for c in doc['categories'])
    print(
        f"{split}: {len(doc['images'])} kare, {len(doc['annotations'])} kutu, "
        f"kategoriler {categories}"
    )


# Çekim bazlı sızıntı kontrolu: aynı klibin iki bölümde olmamalı.
def keys(split):
    doc = json.loads((WALL / split / '_annotations.coco.json').read_text('utf-8'))
    return {img['file_name'].split('_', 1)[0] for img in doc['images']}


train_keys, valid_keys = keys('train'), keys('valid')
overlap = train_keys & valid_keys
print('ortak cekim sayisi:', len(overlap))
if overlap:
    raise SystemExit(f"VERI SIZINTISI: ayni cekim train ve valid icinde: {sorted(overlap)}")
print('Sizinti kontrolu: TEMIZ')
"""
    ),
    code(
        """
# 7) Pilot eğitimi: 5 epoch
#    Tam eğitim için EPOCHS = 40 yap ve bu hücreyi yeniden çalıştır.
from rfdetr import RFDETRNano

EPOCHS = 5
RESOLUTION = 560
OUTPUT_DIR = Path('/content/wall-nano')

model = RFDETRNano(resolution=RESOLUTION)
model.train(
    dataset_dir=str(WALL),
    epochs=EPOCHS,
    batch_size=2,
    grad_accum_steps=8,
    lr=1e-4,
    output_dir=str(OUTPUT_DIR),
    resolution=RESOLUTION,
    device='cuda',
    early_stopping=True,
    early_stopping_patience=8,
    tensorboard=False,
    wandb=False,
)
print('Egitim bitti. Cikti:', OUTPUT_DIR)
"""
    ),
    code(
        """
# 8) Model paketini hazırla (uyulamanın beklediği biçim)
import hashlib

best = OUTPUT_DIR / 'checkpoint_best_total.pth'
if not best.is_file():
    candidates = sorted(OUTPUT_DIR.glob('*.pth'))
    if not candidates:
        raise SystemExit('Hicbir .pth checkpoint uretilmedi; egitim gunlugune bakin.')
    best = candidates[-1]
    print('checkpoint_best_total.pth yok; yedek olarak kullaniliyor:', best.name)

bundle = OUTPUT_DIR / 'wall-nano.pth'
shutil.copy2(best, bundle)

metadata = {
    'architecture': 'RFDETRNano',
    'resolution': RESOLUTION,
    'class_ids': {'ball': 0, 'racket': 1},
    'rfdetr_version': '1.11.0',
    'sha256': hashlib.sha256(bundle.read_bytes()).hexdigest(),
    'dataset': str(WALL),
    'epochs': EPOCHS,
    'validation': 'Pilot egitimi; saha olcumu scripts/evaluate.py ile ayrica yapilmalidir.',
}
bundle.with_suffix('.json').write_text(json.dumps(metadata, indent=2, ensure_ascii=False), 'utf-8')
print('Paket: wall-nano.pth + wall-nano.json')
print('  ', bundle)
print('  ', bundle.with_suffix('.json'))
"""
    ),
    code(
        """
# 9) Çıktıları Google Drive'a kaydet
#    Colab oturumu kapanınca /content silinir; ağırlıklar Drive'da kalır.
target = DRIVE_ROOT / 'runs' / f'wall-nano-{EPOCHS}ep'
if target.exists():
    shutil.rmtree(target)
shutil.copytree(OUTPUT_DIR, target)

print('Drivea kopyalandi:', target)
for path in sorted(target.glob('*')):
    if path.is_file():
        print('  ', path.name, '(%.1f MB)' % (path.stat().st_size / 1024**2))
"""
    ),
    md(
        """
## Modeli uygulamaya taşı

Drive'daki `wall-nano.pth` ve `wall-nano.json` dosyalarını indir ve proje içindeki `models/` klasörüne kopyala. Yerel uygulamada **Ölçüm/takip → RF-DETR modeli seç** ile `.pth` dosyasını seç.

```powershell
Copy-Item <indirdigin-yol>\\wall-nano.pth models\\
Copy-Item <indirdigin-yol>\\wall-nano.json models\\
```

## Pilot sonrası kontrol listesi

| Adım | Durum |
|---|---|
| Eğitim hücresi hatasız bitti | ☐ |
| `checkpoint_best_total.pth` üretildi | ☐ |
| Drive'a `wall-nano.pth` + `wall-nano.json` kopyalandı | ☐ |
| Yerel uygulamada model yüklendi | ☐ |
| Ayrı test videosunda vuruşlar incelendi | ☐ |
| `scripts/evaluate.py` raporu alındı | ☐ |

**Not:** Pilot eğitimde `valid` metrikleri tek klip grubundan gelir; tek başına başarı kanıtı değildir. Tam eğitimde `EPOCHS = 40` kullan ve `test` bölümünü hiçbir eşik ayarında kullanma.
"""
    ),
]


def main() -> None:
    doc = {
        "cells": CELLS,
        "metadata": {
            "accelerator": "GPU",
            "colab": {"provenance": [], "gpuType": "T4"},
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python", "version": "3.11"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    NOTEBOOK.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", "utf-8")
    print(f"Yazildi: {NOTEBOOK} ({len(CELLS)} hucre)")


if __name__ == "__main__":
    main()
