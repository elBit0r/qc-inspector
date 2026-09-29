# Changelog

## 1.3.5 — 2026-09-29

Prima release pubblica, pubblicata con tag `v1.3.5` e pacchetto `.deb` per
Linux amd64, accompagnato dal checksum SHA-256. Testata su Ubuntu 26.04 (64 bit).

- Programmazione dei controlli da disegno PDF con pallinature, quote e tolleranze.
- Piani di campionamento configurabili, registrazione delle misure e valutazione
  PASS/FAIL, storico dei lotti e report PDF.

- Validazione di tipo, finitezza ed esito delle misure prima del commit;
  rifiuto di deroghe incomplete e rollback del lotto in caso di errore.
- Importazione PDF atomica, gruppo della directory di destinazione e permessi
  `0640` per i nuovi file. I PDF esistenti non vengono modificati.
- Recupero persistente della chiave legacy `printername` quando manca
  `label_printer`, mantenendo la precedenza della chiave moderna.
- Vincoli delle dipendenze di build, checksum degli archivi e documenti
  per contribuzione, sicurezza, backup e preparazione del rilascio.

Download e note di installazione:
[release v1.3.5](https://github.com/elBit0r/qc-inspector/releases/tag/v1.3.5).
