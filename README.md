# QC Inspector — Controllo qualità dei pezzi

**QC Inspector è un'applicazione desktop per eseguire e documentare il controllo
qualità di pezzi meccanici e di altri componenti o prodotti, utilizzando un
disegno in formato PDF come riferimento.**

Sul disegno si posizionano le **pallinature**, cioè i richiami numerati che
identificano le quote o le caratteristiche da verificare. A ogni richiamo si
associano il tipo di controllo, il valore nominale, le tolleranze e la criticità.
Durante il collaudo, l'operatore misura i pezzi con i propri strumenti e inserisce
nel programma i valori rilevati oppure l'esito di una verifica Sì/No.

Il software confronta le misure con i limiti impostati, mostra gli esiti
**PASS/FAIL** e conserva i risultati per lotto. Al termine è possibile generare
un report PDF con le misure e il disegno pallinato.

## Funzioni principali

- **Pallinatura del disegno:** aggiunta, spostamento e riordino dei richiami sul PDF.
- **Controlli dimensionali e Sì/No:** definizione delle caratteristiche da verificare
  e della loro criticità: critica, importante o normale.
- **Setup riutilizzabili:** salvataggio del piano di controllo del pezzo, con
  revisioni che mantengono il riferimento usato nei collaudi precedenti.
- **Campionamento per lotto:** piani ESTESO, NORMALE e RIDOTTO configurabili,
  con quantità da controllare e soglie di accettazione distinte per criticità.
- **Registrazione delle misure:** inserimento per campione o per controllo,
  valutazione PASS/FAIL e gestione delle accettazioni in deroga.
- **Storico e report:** consultazione dei lotti, statistiche, valutazione dei
  fornitori e rigenerazione dei report PDF.
- **Etichette:** stampa opzionale dell'etichetta del lotto tramite CUPS.

## Come si usa

1. **Prepara il controllo.** In Programmazione crea un setup, carica il disegno
   PDF e seleziona la Classe di Collaudo. Posiziona le pallinature e definisci i
   controlli, includendone almeno uno critico. Premi **Applica controllo** per
   ciascuno e **Salva setup** per registrare il lavoro.
2. **Avvia il collaudo.** Seleziona setup, fornitore, operatore e dati del lotto.
   Scegli il piano di campionamento e verifica la quantità di pezzi da controllare.
3. **Misura i pezzi.** Seguendo i richiami sul disegno, inserisci le misure
   rilevate o le risposte Sì/No. Il programma mostra gli esiti e l'avanzamento.
4. **Salva i risultati.** Completate le misure, premi **Salva controllo / Genera
   report**. Il lotto viene registrato nello storico; report PDF e stampa
   dell'etichetta sono facoltativi.

Le misure del collaudo restano in memoria fino al salvataggio finale.
Chiudendo o interrompendo il controllo prima di salvarlo, vengono perse dopo
la conferma dell'operatore.

## Schermate di esempio

Un esempio di controllo su una piastra forata.

### Programmazione

Pallinatura del disegno e definizione delle quote da controllare.

![Programmazione di una piastra di prova con pallinature e definizione delle tolleranze](Screenshots/programmazione.png)

### Avvio del controllo

Dati del lotto e quantità da controllare in base al piano di campionamento.

![Avvio di un controllo con dati del lotto e campionamento distinto per criticità](Screenshots/avvio_controllo.png)

### Misurazione dei pezzi

Inserimento delle misure, esiti e confronto con i limiti di tolleranza.

![Controllo sequenziale con misure dei campioni, esiti PASS e indicatore della media](Screenshots/controllo.png)

### Piani di campionamento

Configurazione della numerosità del campione (n), della soglia di accettazione
(Ac) e della soglia di rifiuto (Re) per ciascuna criticità.

![Configurazione del piano esteso con intervalli di lotto e parametri di campionamento](Screenshots/setup_campionamento.png)

## Installazione e avvio

### Dai sorgenti

È richiesto **Python 3.10 o successivo**. Dalla cartella del progetto:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --editable .
python main.py
```

Le dipendenze Python vengono installate automaticamente. Con l'ambiente attivo
puoi avviare il programma anche con `qc-inspector`. In PyCharm puoi eseguire
il `main.py` nella root usando l'interprete del progetto.

Su Ubuntu, per il feedback audio:

```bash
sudo apt install libgstreamer1.0-0 libgstreamer-plugins-base1.0-0 gstreamer1.0-plugins-base gstreamer1.0-plugins-good
```

La stampa delle etichette richiede il client CUPS (`cups-client`) e una
stampante configurata.

### Da un pacchetto `.deb`

Se disponi di un pacchetto compatibile con il tuo sistema:

```bash
sudo apt install ./nome-pacchetto.deb
sudo usermod -aG qc-inspector "$USER"
```

Chiudi la sessione e rientra per attivare il gruppo, quindi avvia **QC Inspector**
dal menu delle applicazioni oppure con `qc-inspector`.

### Dall'archivio portable

Estrai l'archivio, entra nella cartella `qc-inspector`, copia
`qc_inspector.conf.sample` come `qc_inspector.conf` e avvia `./qc-inspector`.
Su Ubuntu sono necessarie le dipendenze audio indicate sopra.

## Configurazione e documentazione

Da **Configurazione** puoi gestire operatori, fornitori, classi e piani di
campionamento. Nella scheda **Opzioni** trovi stampante, copie delle etichette,
separatore decimale, suoni di esito e testo del footer dei report.

Il **Manuale d'uso** è disponibile nel launcher e nel
[file incluso nel progetto](src/qc_inspector/ISTRUZIONI_USO.md).
Per conservare e ripristinare database, disegni e configurazione, consulta
[BACKUP.md](BACKUP.md).

Per contribuire o segnalare problemi:
[CONTRIBUTING.md](CONTRIBUTING.md) · [SECURITY.md](SECURITY.md) ·
[CHANGELOG.md](CHANGELOG.md).

## Licenza

QC Inspector è distribuito sotto **GNU AGPL v3 soltanto** (`AGPL-3.0-only`).
Vedi [LICENSE](LICENSE) e [NOTICE.md](NOTICE.md).

Icone e piani di campionamento sono creazioni originali dell'autore. I suoni
provengono da sound-theme-freedesktop e mantengono le proprie licenze Creative
Commons. Attribuzioni, licenze delle dipendenze e indicazioni sui sorgenti
corrispondenti per la distribuzione dei binari sono in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
