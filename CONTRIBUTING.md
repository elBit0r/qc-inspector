# Contribuire

Aprire una issue per descrivere il problema o la proposta e inviare modifiche
piccole con test di regressione. Usare esclusivamente dati sintetici: non
allegare disegni dei clienti, database operativi o informazioni personali.

Per riprodurre l'ambiente CI, usare Python 3.14.4 in un ambiente virtuale:

```bash
python -m pip install -r constraints-release.txt
python -m pip install --no-deps --no-build-isolation --editable .
QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v
for script in build.sh build_deb.sh packaging/build_rpm.sh tools/check_audio_runtime.sh; do
  bash -n "$script" || exit
done
```

La versione applicativa è in `src/qc_inspector/__init__.py`.
La build legge la stessa versione per rigenerare il manuale PDF, incluso nei
pacchetti e disponibile anche in `dist/Manuale_operativo_QC_Inspector.pdf`.
Per rigenerare solo il manuale, installare `fonts-lato` e usare l'ambiente
Python del progetto:

```bash
.venv/bin/python tools/generate_manual.py
```

Il PDF viene scritto in `output/pdf/`. Il testo e l'impaginazione sono nel
generatore. Quando cambia l'interfaccia, aggiornare anche gli screenshot
pertinenti in `tools/manual/screenshots/`.

Per le modifiche visive verificare anche l'interfaccia in una sessione desktop.

Schema e migrazioni SQLite appartengono esclusivamente a
`src/qc_inspector/database/schema_manager.py`. Non modificare le revisioni
storiche e mantenere atomico il salvataggio dei lotti.

## Pacchetti Linux x86_64

Eseguire `bash build.sh` su Ubuntu 24.04, come in CI, con l'ambiente Python vincolato, le
dipendenze native della CI e i pacchetti di sistema `rpm`, `dpkg` e
`binutils`. La build crea il bundle una sola volta e produce il pacchetto
`.deb` per Debian e Ubuntu in `dist/debroot/`, il pacchetto `.rpm` per
Fedora in `dist/rpm/` e l'archivio portable in `dist/`, ciascuno con il
proprio checksum SHA-256.

Il requisito minimo di glibc per entrambi i pacchetti viene calcolato dagli
ELF inclusi nel bundle. Una build su un host più recente può richiedere una
versione di glibc superiore a quella disponibile su Debian 13.
Le build CI avviate da un tag o manualmente caricano
tutti e tre i formati nell'artefatto `qc-inspector-candidate`.

Per generare il solo pacchetto Debian insieme all'archivio portable, usare
`bash build_deb.sh`.

I contributi di codice devono essere distribuibili sotto AGPL-3.0-only;
documentare fonte e licenza di ogni materiale di terzi aggiunto.
