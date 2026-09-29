# QC Inspector - Istruzioni d'uso

QC Inspector serve per programmare controlli qualità su un PDF tecnico e poi
registrare le misure di collaudo su uno o più campioni.

L'app ha quattro funzioni principali:

- **Programmazione**: si prepara il setup, si carica il PDF e si posizionano le pallinature.
- **Controllo**: si esegue il collaudo, si registrano le misure, si genera il report e, se abilitata, si stampa l'etichetta.
- **Storico lotti**: si consultano i controlli conclusi e si rigenerano i report.
- **Configurazione**: si gestiscono operatori, fornitori, classi di collaudo,
  regole automatiche e piani di campionamento.

Dalla schermata principale il pulsante **Manuale d’uso**, accanto alla
versione, apre questo documento con l'applicazione predefinita del sistema.

La schermata principale mostra inoltre gli ultimi controlli e il grafico
**Qualità fornitori**, filtrabile sugli ultimi 6, 12 o 24 mesi. Le barre
distinguono campioni conformi, accettati in deroga e FAIL; riportano anche
numerosità, non conformità, andamento rispetto al periodo precedente e un
avviso quando i dati disponibili sono insufficienti.

## Avvio

Con pacchetto `.deb`:

```bash
qc-inspector
```

In ambiente di sviluppo:

```bash
pip install --editable .
qc-inspector
```

Nel pacchetto portable, avviare l'eseguibile dalla cartella dell'app:

```bash
./qc-inspector
```

## Modalità Programmazione

Usare questa modalità per creare o modificare un setup di controllo.

1. Aprire **PROGRAMMAZIONE**.
2. Inserire il nome del setup e, se utile, la sua descrizione.
3. Selezionare la **Classe di Collaudo** dalla Configurazione.
4. Caricare il PDF del disegno tecnico.
5. Fare clic sul PDF per aggiungere una pallinatura.
6. Per ogni pallinatura compilare il controllo:
   - **Dimensionale**: quota nominale, tolleranza positiva e tolleranza negativa.
   - **Sì / No**: controllo di presenza o verifica senza valore numerico.
   - **Criticità**: `C — CRITICA`, `I — IMPORTANTE` oppure `N — NORMALE`.
   - Descrizione opzionale.
7. Premere **Applica controllo** per trasferire il controllo nel modello temporaneo.
8. Ripetere per tutte le pallinature.
9. Premere **Salva setup** per registrare tutte le modifiche nel database.

Il nome del setup è obbligatorio e univoco senza distinzione tra maiuscole e
minuscole. Ogni salvataggio che modifica il setup crea automaticamente una
nuova revisione identificata da un UUID. I controlli già conclusi continuano a
usare quote, tolleranze, pallinature e PDF della revisione originale.

All'apertura di Programmazione compare **Gestione setup**. È possibile cercare
un setup digitando una parte del nome o del codice, aprirlo, crearne uno nuovo
oppure eliminarlo. L'elenco mostra nome/codice, descrizione, classe e ultima
modifica. Dopo la scelta, la finestra di Programmazione viene aperta
massimizzata.

La Classe di Collaudo è obbligatoria e fa parte del setup: cambiarla abilita
**Salva setup**, viene rilevato come modifica non salvata e richiede conferma
alla chiusura. La finestra **Gestione setup** mostra la classe in una colonna
dedicata. I setup creati con versioni precedenti vengono associati
automaticamente alla classe `DEFAULT` o alla prima classe disponibile.

Ogni setup deve contenere almeno un controllo classificato `C — CRITICA`; in
caso contrario il salvataggio viene bloccato. Durante l'aggiornamento del
database, tutti i controlli appartenenti ai setup già esistenti vengono
classificati `C` una sola volta.

### Modifica dei controlli

- Clic su una pallinatura o su una riga della lista: carica il controllo nella maschera.
- Clic destro sulla pallinatura: elimina il controllo.
- Pulsante **Elimina selezionato**: elimina il controllo selezionato dalla lista.
- Pulsanti **Sposta su** e **Sposta giù**: cambiano l'ordine del controllo e
  rinumerano automaticamente le pallinature. Il nuovo ordine diventa definitivo
  soltanto premendo **Salva setup**.
- Trascinamento con il pulsante sinistro su una pallinatura: sposta la pallinatura
  sul disegno senza modificarne numero e ordine. Anche la nuova posizione viene
  registrata soltanto con **Salva setup**.

Il tipo di un controllo già salvato non deve essere cambiato. Se serve passare
da dimensionale a Sì/No, eliminare il controllo e ricrearlo.

**Applica controllo** aggiorna soltanto il modello di lavoro: non scrive ancora
nel database. Se si cambia controllo con dati non applicati, il programma
propone **Applica**, **Scarta** o **Annulla**. Se si chiude la finestra, si crea
un nuovo setup o se ne apre un altro con modifiche non salvate, viene invece
proposto **Salva**, **Scarta** o **Annulla**.

Se si carica un PDF diverso mentre il setup contiene già dei controlli, il
programma permette di mantenerli, eliminarli dal modello oppure annullare la
sostituzione.

### Eliminazione di un setup

- Nella finestra **Gestione setup**, selezionare il setup e premere **Elimina setup**.
- La conferma indica quanti controlli configurati verranno cancellati.
- Un setup già collegato a un controllo salvato nello storico non può essere
  eliminato; può invece essere modificato creando una nuova revisione.

### Navigazione PDF

- Rotella mouse: zoom.
- Tasto centrale + trascina: spostamento.
- Doppio clic sul PDF fuori dalle pallinature: reset zoom/spostamento.
- Pulsanti freccia: cambio pagina PDF.

## Modalità Controllo

Usare questa modalità per eseguire il collaudo di un lotto.

1. Aprire **CONTROLLO**.
2. Nella maschera iniziale compilare:
   - setup da caricare; digitare una parte del nome per filtrare rapidamente l'elenco;
   - fornitore, scegliendolo dalla Configurazione; digitare una parte della ragione sociale per filtrare l'elenco;
   - numero lotto;
   - quantità totale del lotto;
   - piano di campionamento **Esteso**, **Normale** o **Ridotto**, scegliendolo
     dal menu a tendina colorato;
   - quantità da controllare, calcolata automaticamente;
   - eventuale controllo sequenziale;
   - operatore, scegliendolo dalla Configurazione.
3. Premere **Avvia controllo**. Il lotto viene creato e si apre direttamente la schermata di inserimento misure.

Selezionando il setup vengono mostrati anche la sua **Descrizione** e la
**Classe di Collaudo** in campi non modificabili. Dopo la scelta del fornitore,
il riquadro dello storico indica quanti controlli esistono già per la stessa
coppia setup-fornitore, quanti sono conclusi e gli ultimi cinque con data,
lotto, esito e stato.

Il programma suggerisce il piano **Esteso**, **Normale** o **Ridotto** in base
allo storico; l'operatore può sempre selezionarne manualmente uno diverso. Ogni
voce del menu utilizza un colore distinto per rendere evidente il piano attivo.

Il programma individua l'intervallo della quantità lotto nel piano della
**Classe di Collaudo del setup**. Legge quindi `n`, `Ac` e `Re` per ogni
criticità presente. I valori sono mostrati nei riquadri **Critica**,
**Importante** e **Normale**, insieme all'intervallo applicato.

Ogni criticità mantiene il proprio valore `n`, limitato alla quantità del
lotto. Il valore più alto compare nel campo **Q.tà da controllare**.
Per un lotto unitario si applicano sempre `n=1`, `Ac=0`, `Re=1`.
Se manca un intervallo valido, l'avvio viene bloccato.

Il controllo sequenziale è disponibile quando la quantità da controllare è
maggiore di due ed è selezionato di default. Se
durante la modifica della quantità il valore passa temporaneamente a uno o due,
la scelta della modalità sequenziale viene ripristinata appena la quantità torna
maggiore di due.

Il piano scelto e i valori `n/Ac/Re` applicati vengono conservati nel lotto e
usati nel controllo reale, nello Storico, nelle statistiche, nell'etichetta e
nel report PDF.

Nella schermata operativa il divisore tra disegno e misure può essere trascinato
per adattare lo spazio alle dimensioni del monitor.

### Come funziona il piano di campionamento

Il piano determina **quanti componenti controllare per ciascuna criticità** e quante
unità difettose accettare. Un controllo C, I o N viene quindi richiesto soltanto
nei primi `n` componenti previsti per la propria criticità.

Il calcolo usa quattro informazioni:

1. **Classe di Collaudo del setup**: viene scelta in Programmazione e identifica
   il gruppo di tabelle da utilizzare.
2. **Tipo di piano**: Esteso, Normale o Ridotto. Il programma lo suggerisce
   usando lo storico della coppia setup-fornitore e le regole della Classe di
   Collaudo; l'utente può comunque cambiarlo nella finestra **Avvia controllo**.
3. **Quantità totale del lotto**: serve a individuare la riga il cui intervallo
   `Lotto min – Lotto max` contiene la quantità indicata. Il simbolo `∞`
   significa che l'intervallo non ha un limite massimo.
4. **Criticità presenti nel setup**: C = Critica, I = Importante e N = Normale.
   Conta la presenza della criticità, non il numero di controlli appartenenti a
   quella criticità.

Dalla riga individuata il programma legge `n`, `Ac` e `Re` per ogni criticità
presente. Il valore `n` resta separato per C, I e N. Il massimo determina
quanti campioni mostrare:

```text
n applicato alla criticità = minimo tra n della criticità e quantità del lotto
quantità massima mostrata = massimo tra n(C), n(I), n(N) applicati
```

Il limite alla quantità del lotto impedisce di richiedere più componenti di
quelli presenti. Un lotto composto da un solo componente viene controllato per
intero. Se nessun intervallo comprende la quantità del lotto, il programma
segnala l'errore e non permette di avviare il controllo.

#### Esempio 1 — criticità diverse

Si seleziona il piano **Normale**, il lotto contiene **100 componenti** e il setup ha
controlli C, I e N. La quantità 100 appartiene all'intervallo `91–150`. Con i valori
predefiniti della relativa riga:

```text
C: n = 20
I: n = 13
N: n = 8
```

Il valore massimo è 20, ma i controlli C sono richiesti su **20 componenti**, quelli
I su **13 componenti** e quelli N su **8 componenti**.

#### Esempio 2 — il numero dei controlli non cambia il campione

Con lo stesso lotto e lo stesso piano, un setup con un controllo C e dieci
controlli N mostra ancora **20 componenti**. Il controllo C compare 20 volte, mentre
ciascuno dei dieci controlli N compare 8 volte. Ogni setup salvabile deve
contenere almeno un controllo C, che viene quindi sempre incluso nel calcolo
insieme alle eventuali criticità I e N.

#### Piano suggerito dallo storico

Dopo avere selezionato setup e fornitore, il programma propone automaticamente
**Esteso**, **Normale** o **Ridotto**. La proposta usa soltanto i controlli
conclusi e non annullati della stessa coppia e rispetta le regole configurate
nella relativa Classe di Collaudo. Sotto il menu sono mostrati motivo e data
dell'ultimo controllo considerato.

Le regole sono configurate separatamente per ogni Classe di Collaudo:

- durata di validità dello storico;
- numero di PASS Estesi necessari per proporre il piano Normale;
- numero di PASS Normali necessari per proporre il piano Ridotto;
- eventuale ritorno al piano Esteso dopo un esito negativo;
- eventuale conteggio dei lotti accettati in deroga come esiti positivi.

Vengono considerati soltanto lotti conclusi, non annullati e compresi nel
periodo di validità. Se non esiste uno storico valido viene proposto il piano
**Esteso**. Un controllo più vecchio del periodo configurato non contribuisce
alla progressione.

L'operatore può sempre scegliere manualmente un piano differente. La scelta
manuale non viene sostituita quando cambia la quantità del lotto o viene
ricalcolato il campionamento.

#### Esempio 3 — campione maggiore del lotto

Si seleziona il piano **Esteso**, il lotto contiene **2 componenti** e il valore
richiesto per C è `n = 8`. Il calcolo finale applica `min(8, 2)`: vengono
controllati **entrambi i componenti**, senza creare campioni inesistenti.

#### Quante registrazioni vengono richieste

La voce **Q.tà da controllare** indica il massimo numero di campioni, non
il numero totale di campi da compilare. Il totale delle registrazioni è:

```text
somma di n(criticità del controllo), per tutti i controlli del setup
```

Esempio: con un controllo C da 20 componenti, un controllo I da 10 e un controllo N
da 5 vengono richieste `20 + 10 + 5 = 35` registrazioni. In modalità Standard,
dal componente 6 non compare più il controllo N e dal componente 11 non compare più il
controllo I. In modalità **Inserimento controllo per controllo**, i tre tab
contengono rispettivamente 20, 10 e 5 righe.

`Ac` indica il numero massimo di **campioni difettosi accettabili** per
criticità. `Re` indica la soglia di rifiuto ed è calcolato come `Ac + 1`.
Più misure FAIL della stessa criticità sullo stesso campione contano come un
solo campione difettoso.

Se i difettosi restano entro `Ac` per ogni criticità, il lotto è **PASS**.
Questo vale anche in presenza di misure FAIL, comprese quelle in deroga.
Se una criticità raggiunge `Re`, l'esito dipende dalle deroghe:

- **FAIL**: resta almeno un difetto non derogato in una criticità che ha
  raggiunto la soglia di rifiuto.
- **ACCETTATO IN DEROGA**: tutti i difetti delle criticità che hanno raggiunto
  la soglia di rifiuto sono stati autorizzati in deroga.

Nella schermata delle misure setup, fornitore, lotto, piano, quantità e operatore sono
mostrati come informazioni non modificabili. Setup e modalità sequenziale non
devono essere selezionati nuovamente.

## Configurazione

Aprire **CONFIGURAZIONE** dalla schermata iniziale. Nel tab **Operatori** si possono
creare, modificare ed eliminare nome e cognome, e-mail, telefono e note. Nel tab
**Fornitori** sono disponibili ragione sociale, partita IVA/codice fiscale,
referente, e-mail, telefono e note.

Il tab **Classi di campionamento** permette di aggiungere, modificare ed
eliminare le classi. Ogni riga contiene **Codice Classe** e **Descrizione
Classe**; entrambi sono obbligatori e il codice non può essere duplicato, anche
usando maiuscole o minuscole diverse. Nella creazione e modifica si impostano
anche validità temporale dello storico, PASS Estesi necessari per il Normale,
PASS Normali necessari per il Ridotto, reset dopo esito negativo e trattamento
delle deroghe. Creando una classe vengono generati
automaticamente i suoi piani **ESTESO**, **NORMALE** e **RIDOTTO**, già
popolati con i dati originali. Eliminando la classe vengono eliminati anche i
tre piani associati. Una classe assegnata ad almeno un setup non può essere
eliminata: il messaggio indica i setup vincolati e occorre prima cambiare la
loro Classe di Collaudo. La classe predefinita non può mai essere eliminata.

Il tab **Campionamento** contiene le tre tabelle modificabili **ESTESO**,
**NORMALE** e **RIDOTTO**. Per ogni intervallo di quantità del lotto sono
riportati `n` (componenti da controllare), `Ac` (non conformi accettabili) e `Re`
(non conformi che determinano il rifiuto) per controlli critici, importanti e
normali. I valori iniziali riproducono il modello
`piani_campionamento_ingresso.xlsx` e vengono poi salvati nel database.

Il menu **Classe di campionamento** sopra le tabelle determina quale gruppo di
tre piani viene visualizzato e modificato. Cambiando classe le tabelle vengono
ricaricate immediatamente. Se la classe corrente contiene modifiche non
salvate, il programma propone **Salva**, **Scarta** o **Annulla** prima del
cambio.

La legenda e le colonne usano lo stesso colore per rendere immediata la
criticità della misura: rosso chiaro per **C = CRITICA**, giallo chiaro per
**I = IMPORTANTE** e verde chiaro per **N = NORMALE**. Passando il mouse sui
tre badge viene mostrata la descrizione completa della relativa tipologia di
misura. Le intestazioni delle colonne spiegano invece il significato dei
parametri `n`, `Ac` e `Re`.

- **Misura Critica**: il mancato rispetto compromette funzionalità, sicurezza
  o intercambiabilità del componente; richiede controllo dimensionale al 100% e
  tolleranze strette.
- **Misura Importante**: influisce sull'accoppiamento o sulle prestazioni del
  componente, con un margine di tolleranza maggiore rispetto alla critica;
  viene controllata a campionamento.
- **Misura Normale**: quota di riferimento generale senza impatto diretto su
  funzionalità o accoppiamenti; segue la tolleranza generale e un controllo
  occasionale.

- Doppio clic su una cella per modificarla con un editor che accetta solo interi.
- **Aggiungi riga** crea un nuovo intervallo dopo l'ultimo.
- **Elimina riga** rimuove la riga selezionata senza modificare automaticamente
  gli intervalli adiacenti; se nasce un buco viene mostrato subito l'intervallo
  mancante e il salvataggio resta bloccato finché non viene corretto.
- **Lotto max infinito (∞)** imposta come illimitato il massimo dell'ultima riga.
- **Ripristina predefiniti**, presente in ogni tabella, ricarica soltanto il
  profilo selezionato dalla copia originale conservata separatamente nel
  database. Anche il ripristino diventa definitivo solo con **Salva tabelle**.
- **Salva tabelle** verifica e registra tutte e tre le tabelle insieme.

Le colonne `Re` sono calcolate automaticamente come `Ac + 1` e non sono
modificabili direttamente. Per cambiare una soglia di rifiuto occorre quindi
modificare il relativo valore `Ac`.

La validazione viene aggiornata sotto ogni tabella dopo ciascuna modifica.
Il salvataggio verifica questi requisiti:

- Il primo intervallo inizia da 2.
- Gli intervalli sono consecutivi e senza sovrapposizioni.
- Il limite infinito compare solo nell'ultima riga.
- I valori rispettano `n ≥ 1` e `0 ≤ Ac < Re ≤ n`.
- Negli intervalli finiti, `n` non supera il massimo del lotto.

Il nome dell'operatore e la ragione sociale del fornitore sono obbligatori e non
possono essere duplicati. Gli operatori salvati vengono proposti nel menu del
Controllo; i lotti gia registrati conservano comunque il nome storico anche se
l'operatore viene successivamente modificato o eliminato.

## Modalità Standard

La modalità standard crea un tab per ogni campione.

Esempio: con 5 campioni vengono creati:

```text
Campione 1
Campione 2
Campione 3
Campione 4
Campione 5
```

Dentro ogni tab si inseriscono tutte le misure previste per quel campione.
Ogni riga mostra anche la criticità assegnata al controllo in Programmazione.

## Modalità Controllo Sequenziale

La modalità sequenziale è disponibile quando il numero campioni è maggiore di 2.
Quando disponibile, è selezionata di default.

Questa modalità crea un tab per ogni controllo/pallinatura.

Esempio: se il setup contiene le pallinature 1, 2 e 3, vengono creati:

```text
Controllo 1
Controllo 2
Controllo 3
```

Dentro ogni tab si inserisce la misura dello stesso controllo per tutti i
campioni. La criticità del controllo è indicata nell'intestazione del tab.

Esempio: 5 campioni e controllo "Diametro foro":

```text
Controllo 1 - Diametro foro
Campione 1: misura
Campione 2: misura
Campione 3: misura
Campione 4: misura
Campione 5: misura
```

Quando si seleziona una pallinatura nel PDF, viene selezionato anche il tab del
controllo corrispondente.

## Inserimento misure

Per controlli dimensionali:

- inserire il valore numerico;
- la misura viene conservata nella bozza in memoria;
- il risultato PASS/FAIL viene mostrato subito.
- confermando con **Invio** una misura PASS, il cursore passa alla misura
  successiva; in caso di FAIL rimane sul campo corrente.

Per controlli Sì/No:

- premere **Sì** o **No**;
- il risultato PASS/FAIL viene mostrato subito.
- dopo una risposta PASS il cursore avanza; una risposta FAIL mantiene il
  controllo corrente.

### Accettazione di un FAIL in deroga

Quando una misura risulta **FAIL**, selezionare la checkbox **Accetta in
deroga**. La selezione puo essere modificata liberamente durante il controllo e
non registra subito la deroga.

Premendo **Salva controllo / Genera report**, un unico dialogo riepiloga tutte le misure
selezionate. Sono obbligatori e vengono applicati a tutte le misure elencate:

- la motivazione della deroga;
- il nome del responsabile che l'ha autorizzata.

Confermando il dialogo, il programma registra automaticamente anche l'operatore
e la data/ora. Le misure restano tecnicamente FAIL ma vengono riportate come
derogate. Se il dialogo deroga viene annullato, il controllo resta in bozza. La
successiva scelta di non generare il PDF non annulla invece il controllo già
salvato.

Se il valore della misura viene modificato, la selezione della checkbox viene
rimossa automaticamente. La deroga cambia l'esito complessivo soltanto quando
evita il rifiuto previsto da `Ac/Re`: se tutti i difetti della criticità che ha
superato la soglia sono derogati, il lotto è **ACCETTATO IN DEROGA**; se ne
rimane almeno uno non derogato, il lotto è **FAIL**. I difetti entro `Ac` sono
ammessi dal piano e il lotto resta **PASS**.

Il separatore decimale è configurabile nel file `qc_inspector.conf`:

```text
decimal_separator = .
```

oppure:

```text
decimal_separator = ,
```

## Fine controllo

Il pulsante **Salva controllo / Genera report** è disponibile solo dopo aver
completato tutte le misure previste.

1. Il lotto, la revisione del setup, il piano, le misure e le eventuali deroghe
   vengono salvati insieme in un'unica transazione.
2. Soltanto dopo il salvataggio viene chiesto se generare subito il PDF.
3. Se le etichette sono abilitate, viene chiesto separatamente se stamparle.
4. La finestra comunica il risultato e si chiude.

Se si sceglie di non generare il PDF, si annulla il selettore del file oppure
si verifica un errore di report o stampa, il controllo resta comunque salvato.
Il report può essere rigenerato in seguito dallo **Storico lotti**.

### Chiusura delle finestre

- Chiudendo con la X o premendo **Interrompere Controllo** viene avvisato che i
  dati della bozza saranno persi. Confermando non viene creato alcun record
  aperto o annullato; scegliendo **No**, la finestra resta aperta.
- La finestra Programmazione chiede conferma prima di chiudersi, perché eventuali
  valori presenti nei campi e non salvati potrebbero andare persi.
- Storico lotti può essere chiuso direttamente. Se nelle tabelle di
  **Configurazione > Campionamento** sono presenti modifiche non salvate, alla
  chiusura viene proposto **Salva**, **Scarta** o **Annulla**.
- Il menu principale non si chiude finché esiste una finestra operativa aperta;
  indica quali finestre devono essere chiuse e ne porta una in primo piano.

## Storico lotti

Aprire **STORICO LOTTI** e scegliere il setup. Il selettore permette di cercare
digitando anche soltanto una parte del nome, senza distinzione tra maiuscole e
minuscole. La scheda **Lotti e statistiche** mostra per ogni lotto quantità,
piano applicato, revisione setup, componenti controllati, PASS, FAIL, deroghe, esito
e stato. Sono presenti soltanto controlli conclusi e salvati.

Il riepilogo e i grafici considerano soltanto i lotti chiusi e non annullati e
mostrano conformità dei campioni per lotto e FAIL per pallinatura. La scheda delle
misure dimensionali riporta, per ogni quota, numero di misure, media, minimo,
massimo, deviazione standard e FAIL.

Per ricreare il PDF di un singolo lotto, selezionare la relativa riga e premere
**Rigenera report PDF**. Il comando è disponibile soltanto se tutte le misure
previste risultano registrate.

## Report globale fornitori

Nella finestra **STORICO LOTTI**, premere **Stampa Report Globale** e scegliere
data inizio e data fine. Il PDF considera tutti i setup e soltanto i lotti
completi, chiusi e non annullati.

Ogni campione viene contato come un singolo componente: la presenza di almeno un
FAIL non derogato classifica il componente come **FAIL**; in assenza di FAIL aperti,
almeno una misura derogata lo classifica come **ACCETTATO IN DEROGA**;
altrimenti il componente e **PASS**. Il report mostra totali, percentuali, classifica
fornitori, avviso per meno di 30 componenti controllati e dettaglio dei lotti.

## Dove vengono salvati i dati

I percorsi sono definiti nel file `qc_inspector.conf`.

Configurazione predefinita per pacchetto `.deb`:

```text
db_path = /var/qc-inspector/qc_database.sqlite
pdf_dir = /var/qc-inspector/pdf
```

### Database

Il database SQLite contiene:

- setup salvati;
- revisioni immutabili dei setup e snapshot di controlli e pallinature;
- lotti conclusi legati alla revisione utilizzata;
- misure registrate;
- esito finale dei lotti.

Al primo avvio della versione 1.3.0 lo schema viene aggiornato alla versione 3:
prima viene creato un backup, poi i vecchi lotti aperti o annullati vengono
rimossi. Se esistono setup con lo stesso nome, quello collegato allo storico
conserva il nome e gli altri ricevono il suffisso `[duplicato ID]`.

La schermata iniziale mostra gli ultimi sei controlli con data/ora, codice
articolo (nome setup), descrizione, numero lotto, quantita lotto, quantita
controllata, operatore ed esito. Per i lotti creati prima dell'introduzione della quantita
lotto viene mostrato `—`.

Nel pacchetto `.deb` il database predefinito è:

```text
/var/qc-inspector/qc_database.sqlite
```

### PDF

Quando si carica un PDF in programmazione, il file viene copiato nella cartella
configurata da `pdf_dir`.

Il nome del PDF salvato è basato sull'hash SHA-256 del file. Questo evita
duplicati: se lo stesso PDF viene caricato più volte, viene riutilizzata la
stessa copia.

Nel pacchetto `.deb` la cartella predefinita è:

```text
/var/qc-inspector/pdf
```

### Configurazione

Nel pacchetto `.deb`:

```text
/etc/qc-inspector/qc_inspector.conf
```

Questo file contiene i percorsi e le impostazioni amministrative ed è in sola
lettura per gli operatori. Le opzioni salvate dalla schermata Configurazione
sono memorizzate separatamente in:

```text
/var/qc-inspector/qc_inspector.options.conf
```

Nel pacchetto portable:

```text
qc_inspector.conf
```

accanto all'eseguibile.

Nell'avvio dai sorgenti o da un package Python:

```text
$XDG_CONFIG_HOME/qc-inspector/qc_inspector.conf
$XDG_DATA_HOME/qc-inspector/
```

Se le variabili XDG non sono impostate vengono usati rispettivamente
`~/.config/qc-inspector` e `~/.local/share/qc-inspector`.

Se `db_path` o `pdf_dir` sono percorsi relativi, vengono risolti rispetto alla
cartella del file `.conf`.

## Permessi su installazione .deb

Per accedere al database e alla cartella PDF condivisa, l'utente deve appartenere
al gruppo:

```text
qc-inspector
```

Comando:

```bash
sudo usermod -aG qc-inspector <utente>
```

Dopo il comando, l'utente deve chiudere la sessione e rientrare.

## Etichette

Le etichette sono configurate in `qc_inspector.conf`:

```text
label_enable = YES
label_printer = Zebra-ZPL
labels_qta = 2
```

Per stampare serve il comando di sistema `lp`. Nel pacchetto `.deb` viene
richiesta la dipendenza `cups-client`.

Per disabilitare la stampa etichette:

```text
label_enable = NO
```

## Troubleshooting

### Non riesco ad aprire o salvare PDF/database

Verificare che l'utente sia nel gruppo `qc-inspector`:

```bash
groups
```

Se manca, aggiungerlo:

```bash
sudo usermod -aG qc-inspector <utente>
```

Poi uscire dalla sessione e rientrare.

### La stampa etichetta non funziona

Verificare che `lp` sia disponibile:

```bash
which lp
```

Verificare il nome stampante:

```bash
lpstat -p
```

Aggiornare `label_printer` in `qc_inspector.conf`.

### Il separatore decimale non è quello atteso

Controllare:

```text
decimal_separator = .
```

oppure:

```text
decimal_separator = ,
```

Riavviare l'app dopo la modifica.

### Non vedo correttamente alcune icone/testi

Alcuni simboli Unicode dipendono dai font installati sul sistema. Se un'icona
testuale non si vede, il problema è di font/fallback del sistema, non dei dati.

### Il report non è disponibile

Il report viene abilitato solo quando tutte le misure previste sono state
registrate.

Controllare la barra di avanzamento e completare tutti i tab.

### Ho interrotto un controllo

Se si preme **Interrompere Controllo** e si conferma l'avviso, la bozza viene
scartata e nessun lotto viene scritto nel database.

### Il report o l'etichetta non vengono generati

Il controllo è già salvato prima di queste operazioni e non resta aperto. Il
report può essere rigenerato dallo Storico; per la stampa verificare la
configurazione della stampante e ripetere secondo la procedura operativa.
