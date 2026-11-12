# Интерфейс и запуск

## Локальный веб-интерфейс

Windows: дважды нажмите `Start.cmd` или выполните `./run.ps1 serve --open` в PowerShell.

macOS/Linux:

```sh
sh start.sh
```

Откройте http://127.0.0.1:8765. В форме выберите VCF/VCF.GZ/TSV/ZIP и добавьте фенотип. Локальный сервер привязан к loopback-адресу по умолчанию и не отправляет файлы во внешние API.

## CLI

Онлайн-аннотация доступна только в CLI и отключена по умолчанию. Пример с явным указанием сборки:

```powershell
.\\run.ps1 run --dataset examples\\demo_case.vcf --phenotype "арахнодактилия" --online --assembly GRCh38
```

При включении online-режима координаты и аллели вариантов отправляются Ensembl; фенотип не отправляется.

```sh
python -m genomic_detective prepare
python -m genomic_detective run --dataset examples/demo_case.vcf --phenotype "арахнодактилия эктопия хрусталика"
python -m genomic_detective serve --port 8765 --open
```

## Демонстрационные данные

`examples/demo_case.vcf` содержит учебную строку с геном FBN1 и VUS-маркером. Она нужна для проверки потока чтения, а не представляет клинический пример или причинный вариант.
