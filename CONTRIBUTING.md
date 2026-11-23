# Contribuire

Aprire una issue per descrivere il problema o la proposta e inviare modifiche
piccole con test di regressione. Usare esclusivamente dati sintetici: non
allegare disegni dei clienti, database operativi o informazioni personali.

Per riprodurre l'ambiente CI, usare Python 3.14.4 in un ambiente virtuale:

```bash
python -m pip install -r constraints-release.txt
python -m pip install --no-deps --no-build-isolation --editable .
QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v
for script in build.sh build_deb.sh tools/check_audio_runtime.sh; do
  bash -n "$script" || exit
done
```

La versione applicativa è in `src/qc_inspector/__init__.py`.
Per le modifiche visive verificare anche l'interfaccia in una sessione desktop.

Schema e migrazioni SQLite appartengono esclusivamente a
`src/qc_inspector/database/schema_manager.py`. Non modificare le revisioni
storiche e mantenere atomico il salvataggio dei lotti.

## Pacchetto Ubuntu amd64

Eseguire `bash build_deb.sh` direttamente su Ubuntu con l'ambiente Python
vincolato e le dipendenze native installate. Lo script stampa il percorso del
pacchetto e salva il checksum nella stessa cartella, sotto `dist/debroot/`.
Il requisito minimo di glibc viene calcolato dalle librerie incluse nel bundle.

I contributi di codice devono essere distribuibili sotto AGPL-3.0-only;
documentare fonte e licenza di ogni materiale di terzi aggiunto.
