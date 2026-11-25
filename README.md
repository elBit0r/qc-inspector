# QC Inspector — Controllo qualità da disegno tecnico

[![CI](https://github.com/elBit0r/qc-inspector/actions/workflows/ci.yml/badge.svg)](https://github.com/elBit0r/qc-inspector/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/elBit0r/qc-inspector)](https://github.com/elBit0r/qc-inspector/releases)
[![Licenza: AGPL-3.0-only](https://img.shields.io/badge/licenza-AGPL--3.0--only-blue)](LICENSE)

**QC Inspector è un'applicazione desktop per programmare, eseguire e documentare
controlli qualità su componenti e prodotti utilizzando un disegno tecnico in
formato PDF come riferimento.**

Sul disegno si posizionano richiami numerati (**pallinature**) associati alle
caratteristiche da verificare, definendo tipo di controllo, valore nominale,
tolleranze e criticità.

Durante il collaudo l'operatore inserisce le misure rilevate oppure l'esito di
controlli Sì/No. Il software verifica automaticamente la conformità rispetto
ai criteri impostati e registra i risultati per lotto. Al termine può generare
un report PDF contenente le misure e il disegno pallinato.

**[Scarica QC Inspector dalle release GitHub](https://github.com/elBit0r/qc-inspector/releases)**

## Funzioni principali

- **Pallinatura del disegno:** aggiunta, spostamento e riordino dei richiami sul PDF.
- **Controlli dimensionali e Sì/No:** definizione delle caratteristiche da verificare
  e della loro criticità: critica, importante o normale.
- **Setup riutilizzabili:** salvataggio del piano di controllo del componente, con
  revisioni che mantengono il riferimento usato nei collaudi precedenti.
- **Campionamento per lotto:** piani ESTESO, NORMALE e RIDOTTO configurabili,
  con quantità da controllare e soglie di accettazione distinte per criticità.
- **Registrazione delle misure:** inserimento per campione o per controllo,
  valutazione PASS/FAIL e gestione delle accettazioni in deroga.
- **Storico e report:** consultazione dei lotti, statistiche, valutazione dei
  fornitori e rigenerazione dei report PDF.
- **Etichette:** stampa opzionale dell'etichetta del lotto tramite CUPS.

## Come si usa

Per il **primo collaudo**, un database nuovo include il setup
**PF-001 - Piastra di fissaggio (esempio)** con cinque controlli già pallinati,
**Operatore dimostrativo** e **Fornitore dimostrativo**. In **Controllo** scegli
questi tre elementi, inserisci il lotto `PROVA-001` con quantità `1` e premi
**Avvia controllo**. Usa i valori nominali indicati sul disegno per ottenere un
PASS. Su un database già esistente puoi creare un setup di prova importando il
[PDF della piastra](src/qc_inspector/assets/examples/piastra-fissaggio-esempio.pdf).

Per preparare un collaudo su un tuo disegno:

1. **Prepara il controllo.** In Programmazione crea un setup, carica il disegno
   PDF e seleziona la Classe di Collaudo. Posiziona le pallinature e definisci i
   controlli, includendone almeno uno critico. Premi **Applica controllo** per
   ciascuno e **Salva setup** per registrare il lavoro.
2. **Avvia il collaudo.** Se necessario, crea operatore e fornitore in
   **Configurazione**. In **Controllo** selezionali insieme al setup e inserisci i dati del lotto.
   Scegli il piano di campionamento e verifica la quantità di componenti da controllare.
3. **Misura i componenti.** Seguendo i richiami sul disegno, inserisci le misure
   rilevate o le risposte Sì/No. Il programma mostra gli esiti e l'avanzamento.
4. **Salva i risultati.** Completate le misure, premi **Salva controllo / Genera
   report**. Il lotto viene registrato nello storico; report PDF e stampa
   dell'etichetta dipendono dalle opzioni configurate.

Le misure del collaudo restano in memoria fino al salvataggio finale.
Chiudendo o interrompendo il controllo prima di salvarlo, vengono perse dopo
la conferma dell'operatore.

## Schermate di esempio

Un esempio di controllo su una piastra forata. Le schermate sono tratte da una
versione precedente e alcune voci dell'interfaccia possono differire.

### Programmazione

Pallinatura del disegno e definizione delle quote da controllare.

![Programmazione di una piastra di prova con pallinature e definizione delle tolleranze](Screenshots/programmazione.png)

### Avvio del controllo

Dati del lotto e quantità da controllare in base al piano di campionamento.

![Avvio di un controllo con dati del lotto e campionamento distinto per criticità](Screenshots/avvio_controllo.png)

### Misurazione dei componenti

Inserimento delle misure, esiti e confronto con i limiti di tolleranza.

![Controllo sequenziale con misure dei campioni, esiti PASS e indicatore della media](Screenshots/controllo.png)

### Piani di campionamento

Configurazione della numerosità del campione (n), della soglia di accettazione
(Ac) e della soglia di rifiuto (Re) per ciascuna criticità.

![Configurazione del piano esteso con intervalli di lotto e parametri di campionamento](Screenshots/setup_campionamento.png)

## Installazione e avvio

### Dai sorgenti

Il progetto dichiara **Python 3.10 o successivo** come requisito minimo.
I test locali sono stati eseguiti con **Python 3.14.4**; anche la CI è configurata
per questa versione. Le altre versioni non sono attualmente verificate dalla CI.
Dalla cartella del progetto:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --editable .
python main.py
```

Le dipendenze Python vengono installate automaticamente. Con l'ambiente attivo
puoi avviare il programma anche con `qc-inspector`. In PyCharm puoi eseguire
il `main.py` nella root usando l'interprete del progetto.

Su Ubuntu, Qt Multimedia richiede `libpulse-mainloop-glib0`. Per il feedback
audio servono anche le librerie e i plugin GStreamer:

```bash
sudo apt install libpulse-mainloop-glib0 libgstreamer1.0-0 libgstreamer-plugins-base1.0-0 gstreamer1.0-plugins-base gstreamer1.0-plugins-good
```

La stampa delle etichette richiede il client CUPS (`cups-client`) e una
stampante configurata.

### Da un pacchetto `.deb` su Debian o Ubuntu

Apri la [pagina delle release](https://github.com/elBit0r/qc-inspector/releases)
e scarica il file `.deb` dalla sezione **Assets** della versione desiderata.
Consulta le note della release per i requisiti di sistema, quindi esegui dalla
cartella in cui hai salvato il pacchetto:

```bash
sudo apt install ./nome-pacchetto.deb
sudo usermod -aG qc-inspector "$USER"
```

Chiudi la sessione e rientra per attivare il gruppo, quindi avvia **QC Inspector**
dal menu delle applicazioni oppure con `qc-inspector`.

### Da un pacchetto `.rpm` su Fedora

Scarica il file `.rpm` dalla sezione **Assets** della release e installalo
dalla cartella in cui lo hai salvato:

```bash
sudo dnf install ./nome-pacchetto.rpm
sudo usermod -aG qc-inspector "$USER"
```

Chiudi la sessione e rientra per attivare il gruppo, quindi avvia
**QC Inspector** dal menu delle applicazioni oppure con `qc-inspector`.

### Dall'archivio portable

Estrai l'archivio, entra nella cartella `qc-inspector`, copia
`qc_inspector.conf.sample` come `qc_inspector.conf` e avvia `./qc-inspector`.
Con i percorsi predefiniti, al primo avvio il programma crea il database e
salva i PDF accanto all'eseguibile. Usa una cartella in cui puoi scrivere.
Su Ubuntu, installa le dipendenze audio indicate sopra per i suoni di esito.

## Configurazione e documentazione

Da **Configurazione** puoi gestire operatori, fornitori, classi e piani di
campionamento. Nella scheda **Opzioni** trovi il separatore decimale, i suoni di
esito e i percorsi del database e dei PDF. La scheda **Etichetta** contiene
stampante CUPS, copie, stampa automatica e un editor del formato con anteprima.
Nella scheda **Report** puoi configurare logo, piè di pagina, cartella di
destinazione e salvataggio automatico.

Il pulsante **Manuale d’uso** nella finestra principale apre il PDF nel lettore
predefinito del sistema. Nei pacchetti `.deb` e `.rpm` il PDF si trova in
`/opt/qc-inspector/Manuale_operativo_QC_Inspector.pdf`. Nella versione portable
si trova accanto all’eseguibile. Se avvii dai sorgenti, il comando
`.venv/bin/python tools/generate_manual.py` genera il PDF in `output/pdf/`.
La scheda **Backup** esporta e ripristina database e disegni. Per includere
anche la configurazione, segui la procedura manuale in
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
