# QC Inspector - Controllo qualita da disegni PDF

QC Inspector e un'applicazione desktop PyQt5 per programmare controlli qualita su disegni tecnici PDF, registrare misure di collaudo per lotto e generare report PDF.

Funzioni principali:

- Programmazione setup con Classe di Collaudo, PDF, pallinature e controlli
  dimensionali o Si/No.
- Nomi setup univoci senza distinzione tra maiuscole e minuscole e revisioni
  automatiche immutabili di ogni configurazione salvata.
- Collaudo lotto con uno o piu campioni.
- Valutazione automatica PASS/FAIL e accettazione tracciata dei FAIL in deroga.
- Generazione report PDF con pallinature verdi per PASS, rosse per FAIL e arancioni per deroghe.
- Storico lotti per setup con rigenerazione dei report.
- Report globale per periodo con valutazione fornitori basata su pezzi PASS, FAIL e accettati in deroga.
- Anagrafica operatori, fornitori e classi di campionamento, più configurazione
  persistente e separata per classe dei piani ESTESO, NORMALE e RIDOTTO.
- Calcolo automatico della quantità da controllare in base a lotto, piano scelto
  e criticità presenti nel setup, usando i piani della Classe di Collaudo
  assegnata al codice.
- Stampa opzionale dell'etichetta lotto tramite CUPS.
- Blocco di avvio multiplo: lo stesso utente non puo aprire piu istanze dell'app.

## Licenza

Il codice originale di QC Inspector è distribuito sotto **GNU AGPL v3 soltanto**
(`AGPL-3.0-only`). Vedere [LICENSE](LICENSE) per il testo completo e
[NOTICE.md](NOTICE.md) per gli avvisi, inclusa l'assenza di garanzia.
Le dipendenze e i materiali di terzi mantengono le proprie licenze.
L'inventario delle dipendenze e degli asset è in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md); i testi raccolti sono in
`third_party/licenses/`.

Il pulsante **Licenza** nel launcher mostra gli avvisi e il testo anche offline.
Le build portable e Debian includono questi documenti e i testi delle licenze;
il `.deb` li installa inoltre in `/usr/share/doc/qc-inspector/`.
Ogni release binaria deve fornire accesso ai sorgenti corrispondenti completi,
con gli script di build e installazione, secondo le condizioni della licenza.

## Requisiti

Su Ubuntu, sia per il portable sia per i sorgenti, installare il runtime audio:

```bash
sudo apt install libgstreamer1.0-0 libgstreamer-plugins-base1.0-0 gstreamer1.0-plugins-base gstreamer1.0-plugins-good
```

Il `.deb` dichiara queste dipendenze: installarlo con `sudo apt install ./nome-pacchetto.deb`.
Le build usano GStreamer e GLib del sistema, evitando copie rilocate che non
trovano `identity` o mescolano librerie e plugin di versioni differenti.
Sulla macchina di build serve anche `gstreamer1.0-tools`: la build verifica
caricamento dei plugin e decodifica dei suoni con uscita simulata, senza
richiedere una scheda audio. Per ripetere il controllo:

```bash
bash tools/check_audio_runtime.sh dist/qc-inspector/_internal
```

Il controllo non verifica volume, dispositivo di uscita o audio della VM:
per questi usare **Configurazione → Opzioni → Prova** nella sessione desktop.

- Python 3.10+
- PyQt5
- PyMuPDF (`fitz`)
- ReportLab
- CUPS client (`lp`) per la stampa etichette

Il package e le dipendenze Python sono definiti in `pyproject.toml`;
`requirements.txt` resta disponibile per gli strumenti che richiedono il
formato tradizionale.

## Installazione

### Ambiente Python/dev

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --editable .
qc-inspector
```

Il comando funziona indipendentemente dal nome assegnato alla directory del
clone o dell'archivio estratto.

### Pacchetto portable

Generazione:

```bash
./build.sh
```

Lo script crea:

- `dist/qc-inspector/qc-inspector`
- `dist/qc-inspector-package/`
- `dist/qc-inspector-<versione>-linux-x86_64.tar.gz`

Nel pacchetto portable viene creato un database SQLite vuoto a ogni build:

```text
qc_database.sqlite
```

Il file di configurazione di esempio e:

```text
qc_inspector.conf.sample
```

Per usare il portable, copiarlo come `qc_inspector.conf` nella cartella dell'eseguibile e avviare:

```bash
./qc-inspector
```

### Pacchetto `.deb`

Generazione:

```bash
./build_deb.sh
```

Il pacchetto installa:

```text
/opt/qc-inspector
/usr/bin/qc-inspector
/etc/qc-inspector/qc_inspector.conf
/var/qc-inspector
/var/qc-inspector/qc_inspector.options.conf
```

Il database runtime predefinito e:

```text
/var/qc-inspector/qc_database.sqlite
```

La cartella PDF runtime predefinita e:

```text
/var/qc-inspector/pdf
```

Durante installazione o aggiornamento del pacchetto `.deb`, database, PDF e
opzioni esistenti vengono preservati. Il pacchetto rifiuta percorsi runtime
costituiti da link simbolici e non applica modifiche ricorsive ai dati.

Dopo l'installazione, aggiungere gli utenti al gruppo `qc-inspector` per accedere al database e alla cartella PDF:

```bash
sudo usermod -aG qc-inspector <utente>
```

L'utente deve poi chiudere la sessione e rientrare.

## Avvio

### Dev

In PyCharm puoi usare la configurazione **main** oppure aprire il `main.py`
nella root e premere **Run**,
usando l'interprete del progetto con le dipendenze installate.
Da terminale puoi eseguire `python main.py` dalla root del progetto.
Non occorre installare il progetto come package per l'avvio diretto.

```bash
qc-inspector
```

### `.deb`

```bash
qc-inspector
```

### Portable

```bash
./qc-inspector
```

## Configurazione

In sviluppo la configurazione viene creata secondo lo standard XDG:

```text
$XDG_CONFIG_HOME/qc-inspector/qc_inspector.conf
```

Se `XDG_CONFIG_HOME` non è impostata viene usato
`~/.config/qc-inspector/qc_inspector.conf`. Database e PDF vengono creati in
`$XDG_DATA_HOME/qc-inspector`, con fallback `~/.local/share/qc-inspector`.
Per usare un config esplicito si può impostare `QC_INSPECTOR_CONFIG`.

Nel portable il file principale è `qc_inspector.conf`, accanto
all'eseguibile.

Chiavi supportate:

- `label_printer`: nome stampante CUPS, default `Zebra-ZPL`.
- `labels_qta`: numero copie etichetta, default `2`.
- `label_enable`: abilita richiesta stampa etichetta (`YES`, `Y`, `TRUE`, `1`, `ON`).
- `db_path`: percorso del database SQLite.
- `pdf_dir`: directory in cui vengono copiati i PDF dei setup.
- `decimal_separator`: separatore decimale visualizzato, `.` oppure `,`.

I percorsi relativi sono risolti rispetto alla cartella del file `.conf`.

Nel pacchetto `.deb`, percorsi e impostazioni amministrative sono letti da:

```text
/etc/qc-inspector/qc_inspector.conf
```

Le opzioni salvate dalla GUI sono scritte in:

```text
/var/qc-inspector/qc_inspector.options.conf
```

Il secondo file può contenere soltanto le opzioni esposte dall'interfaccia;
`db_path` e `pdf_dir` restano sotto controllo amministrativo.

## Struttura progetto

```text
qc_inspector/
├── pyproject.toml                  # Packaging, dipendenze ed entry point
├── requirements.txt
├── build.sh                        # Build portable
├── build_deb.sh                    # Build pacchetto .deb
├── packaging/
│   └── qc_inspector.debian.conf    # Config predefinito del pacchetto Debian
├── docs/
│   └── PROJECT_MAP.md              # Mappa tecnica locale del progetto
├── src/qc_inspector/
│   ├── __init__.py                # Versione del package
│   ├── main.py                     # Launcher e funzione main()
│   ├── ISTRUZIONI_USO.md           # Manuale incluso nell'app
│   ├── assets/                     # Icone e feedback audio
│   ├── core/                       # Config, valutazione, report e servizi
│   ├── database/                   # Schema e persistenza SQLite
│   └── ui/                         # Finestre e widget PyQt5
└── tests/                          # Suite unittest
```


## Modalita Programmazione

1. Apri **PROGRAMMAZIONE** dalla schermata di avvio.
2. Carica il PDF del disegno tecnico.
3. Inserisci nome e descrizione del setup.
4. Seleziona la Classe di Collaudo e clicca sul disegno per posizionare le pallinature.
5. Per ogni balloon, definisci il controllo:
   - **Dimensionale**: nominale, tolleranza positiva e tolleranza negativa.
   - **Si/No**: controllo booleano.
6. Usa **Applica controllo** per ogni controllo, includendone almeno uno critico,
   quindi **Salva setup** per registrare tutte le modifiche.

Il nome del setup deve essere univoco. Ogni salvataggio che modifica dati,
PDF, classe, pallinature o tolleranze crea automaticamente una nuova revisione;
i controlli già conclusi restano legati alla revisione usata al momento del
collaudo.

### Navigazione PDF

- Rotella mouse: zoom.
- Tasto centrale mouse + trascina: pan.
- Doppio click fuori da balloon: reset zoom/pan.
- Pulsanti pagina: cambio pagina PDF.

## Modalita Collaudo

1. Apri **Controllo** dalla schermata di avvio.
2. Seleziona setup, fornitore e operatore.
3. Inserisci Cod. Lotto e quantità totale, quindi scegli piano e modalità di
   esecuzione. La quantità da controllare viene calcolata dai piani della
   Classe di Collaudo.
4. Verifica il riepilogo del campionamento e avvia il controllo.
5. Registra le misure:
   - per i controlli dimensionali, inserisci il valore numerico;
   - per i controlli Si/No, seleziona Si oppure No.
6. L'esito PASS/FAIL viene calcolato automaticamente.
7. I FAIL da accettare in deroga si selezionano con una checkbox; al salvataggio
   un solo dialogo richiede motivazione e responsabile per tutte le misure selezionate.
8. Le misure restano in memoria fino a quando tutte quelle previste sono state
   compilate e viene premuto **Salva controllo / Genera report**.
9. Il controllo viene salvato atomicamente nello storico prima di chiedere se
   generare il PDF e se stampare l'etichetta.
10. PDF ed etichetta sono opzionali: annullare il percorso del PDF o non
    stampare l'etichetta non annulla il controllo già salvato.

Chiudendo la finestra o premendo **Interrompere Controllo** prima del
salvataggio, un avviso informa che tutti i dati della bozza saranno persi. La
bozza non viene registrata come lotto aperto o annullato.

Con piu di 2 campioni e disponibile anche il controllo sequenziale, organizzato per controllo/pallinatura invece che per campione.

## Storico Lotti

La schermata **STORICO LOTTI** permette di:

- scegliere prima il setup;
- vedere i lotti associati a quel setup;
- visualizzare Data, Operatore, Cod. Lotto, revisione setup, piano di
  campionamento, campioni, Esito e Stato;
- mostrare soltanto controlli salvati e conclusi;
- rigenerare il report PDF di un lotto completo.

La ristampa dell'etichetta non fa parte dello storico lotti.

## Database

Il database e SQLite.

Tabelle principali:

- `setups`: setup di controllo e PDF associato.
- `controls`: pallinature e controlli del setup.
- `setup_revisions`: versioni immutabili dei setup, con UUID e hash contenuto.
- `revision_controls`: snapshot dei controlli appartenenti a ogni revisione.
- `lots`: controlli conclusi, collegati alla revisione usata.
- `measurements`: misure definitive per lotto, controllo revisionato e campione.

Lo schema versione 3 elimina durante la migrazione i vecchi lotti aperti o
annullati. Eventuali nomi setup duplicati preesistenti vengono resi univoci con
il suffisso `[duplicato ID]`; da quel momento un indice SQLite impedisce nuovi
duplicati anche se differiscono soltanto per maiuscole/minuscole.

Il percorso del database e definito da `db_path` in `qc_inspector.conf`.

Note importanti:

- Il database locale `qc_database.sqlite` e un dato runtime e non deve essere pubblicato come sorgente.
- Il build portable ricrea un database vuoto a ogni esecuzione di `build.sh`.
- Il pacchetto `.deb` preserva il database esistente durante gli aggiornamenti.

## Report PDF

Il report contiene:

- dati setup, revisione, identificatore UUID, lotto, operatore e data;
- riepilogo dei controlli, relativa criticità e misure per campione;
- esito per controllo;
- esito globale del lotto;
- dettaglio delle deroghe con motivazione, autorizzante, operatore e data/ora;
- pagine del disegno PDF con balloon colorati.

Colori usati nel report esportato:

- verde: PASS;
- rosso: FAIL;
- arancione: FAIL accettato in deroga.

## Etichette

La stampa etichette usa:

- `label_printer`
- `labels_qta`
- `label_enable`

L'etichetta viene generata come PDF e inviata alla stampante tramite comando `lp`.

## Documentazione tecnica

La mappa tecnica locale del progetto e:

```text
docs/PROJECT_MAP.md
```

Prima di modificare funzioni, classi, database, configurazioni o flussi applicativi, aggiornare anche `docs/PROJECT_MAP.md` se il file e incluso nel workspace.

## Test e verifiche

Suite automatica:

```bash
python -m unittest discover -s tests -v
```

Verifica script di build:

```bash
bash -n build.sh
bash -n build_deb.sh
```

Build portable:

```bash
./build.sh
```

Build `.deb`:

```bash
./build_deb.sh
```

## Estensioni future possibili

- Statistiche Ppk per controlli dimensionali (Cp/Cpk sono già presenti nella modalità sequenziale).
- Export Excel del riepilogo misure.
- Gestione utenti e autenticazione.
- Grafici di controllo.
- Import/export setup in formato JSON.
- Ricerca e filtri avanzati nello storico lotti.

### Suoni personalizzati e prova audio

In **Configurazione → Opzioni** puoi scegliere file diversi per PASS e FAIL.
**Sfoglia** seleziona un file; **Predefinito** ripristina il suono incluso;
**Prova** riproduce la scelta anche prima del salvataggio e mostra eventuali
errori audio. Premi **Salva opzioni** per applicarla alle misure successive.
I file non vengono copiati: mantienili in una cartella accessibile agli utenti
che usano l'applicazione. I formati riproducibili dipendono dai codec installati.

## Preparazione della prima release pubblica

Il candidato è in verifica: non è ancora definita una matrice di sistemi
certificati. La CI proposta usa Ubuntu 24.04 x86_64 e CPython 3.14.4;
questo non equivale a una prova di installazione desktop o multiutente.
La build locale richiede x86_64 e controlla le versioni installate contro
`constraints-release.txt`. Preparare il venv con
`pip install -r constraints-release.txt`, quindi installare il progetto.
Le build producono anche checksum `.sha256` verificabili con `sha256sum -c`.

Consultare [CHANGELOG.md](CHANGELOG.md), [BACKUP.md](BACKUP.md),
[CONTRIBUTING.md](CONTRIBUTING.md) e [SECURITY.md](SECURITY.md).
Icone e piani di campionamento sono creazioni originali dell'autore.
I suoni provengono da sound-theme-freedesktop; attribuzioni e licenze
Creative Commons sono riportate in THIRD_PARTY_NOTICES.md.
