# Backup e ripristino

Il backup deve comprendere **insieme database, intera directory PDF e
configurazione**. Un backup del solo database non conserva i disegni.

1. Chiudere QC Inspector in tutte le sessioni e su tutti i computer che usano
   quei dati. Bloccare nuovi accessi fino al termine della copia.
2. Leggere i percorsi effettivi `db_path` e `pdf_dir` dalla configurazione.
   Copiare il database, gli eventuali file SQLite `-wal` e `-shm`, tutti i PDF
   e i file di configurazione in una cartella di backup separata, conservando
   permessi e proprietari. Non copiare un database mentre viene utilizzato.
3. Annotare versione dell'applicazione, data e percorsi originali; conservare
   il backup con accesso limitato, perché contiene dati operativi.
4. Verificare periodicamente il ripristino su una copia isolata.

Per il `.deb` i percorsi predefiniti sono `/var/qc-inspector` (dati e opzioni)
e `/etc/qc-inspector/qc_inspector.conf` (configurazione amministrativa).
Nel portable salvare anche `qc_inspector.conf` accanto all'eseguibile.
Con installazione Python usare i percorsi XDG o quelli impostati nel config.

Per ripristinare, chiudere tutte le istanze, conservare prima una copia dello
stato attuale e ripristinare l'intero insieme allo stesso percorso con gli
stessi proprietari e permessi. Non lasciare file `-wal`/`-shm` dello stato
sostituito accanto al database ripristinato. Usare inizialmente la versione
dell'applicazione annotata nel backup; provare apertura setup, storico e
rigenerazione di un report. I riferimenti PDF salvati nel DB sono assoluti:
spostare soltanto le directory non aggiorna questi riferimenti.

Le migrazioni creano un backup SQLite, ma questo non sostituisce il backup
operativo completo dei PDF e della configurazione.

## PDF importati prima della correzione dei permessi

I nuovi PDF ricevono permessi `0640` e il gruppo della directory PDF.
I file già presenti sono conservati senza modifiche. Prima dell'uso
multiutente, un amministratore deve inventariarli, verificarne la titolarità
e correggere individualmente gli eventuali file non leggibili dal gruppo
`qc-inspector`, dopo un backup. Evitare modifiche ricorsive indiscriminate.
