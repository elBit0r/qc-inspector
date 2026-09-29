# Changelog

## Non rilasciato — preparazione della prima release pubblica

- Validazione di tipo, finitezza ed esito delle misure prima del commit;
  rifiuto di deroghe incomplete e rollback del lotto in caso di errore.
- Importazione PDF atomica, gruppo della directory di destinazione e permessi
  `0640` per i nuovi file. I PDF esistenti non vengono modificati.
- Recupero persistente della chiave legacy `printername` quando manca
  `label_printer`, mantenendo la precedenza della chiave moderna.
- Vincoli delle dipendenze del candidato, checksum degli archivi e documenti
  per contribuzione, sicurezza, backup e preparazione del rilascio.

La versione del codice resta 1.3.5 durante la preparazione. Versione finale,
tag e sistemi supportati saranno definiti alla chiusura delle verifiche.
