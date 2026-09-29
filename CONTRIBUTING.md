# Contribuire

Aprire una issue per descrivere il problema o la proposta e inviare modifiche
piccole con test di regressione. Usare esclusivamente dati sintetici: non
allegare disegni dei clienti, database operativi o informazioni personali.

Installare il progetto con `pip install -c constraints-release.txt --editable .`.
Eseguire `QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v`
e `bash -n build.sh build_deb.sh tools/check_audio_runtime.sh`.
Per le modifiche visive verificare anche l'interfaccia in una sessione desktop.

Schema e migrazioni SQLite appartengono esclusivamente a
`src/qc_inspector/database/schema_manager.py`. Non modificare le revisioni
storiche e mantenere atomico il salvataggio dei lotti.

I contributi di codice devono essere distribuibili sotto AGPL-3.0-only;
documentare fonte e licenza di ogni materiale di terzi aggiunto.
