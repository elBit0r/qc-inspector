#!/usr/bin/env python3
"""Genera il manuale operativo PDF con la versione del codice sorgente."""

from argparse import ArgumentParser
from io import BytesIO
from pathlib import Path
from runpy import run_path
from tempfile import NamedTemporaryFile

from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader

ROOT = Path(__file__).resolve().parents[1]
SCREENSHOTS = ROOT / "tools/manual/screenshots"
DEFAULT_OUTPUT = ROOT / "output/pdf/Manuale_operativo_QC_Inspector.pdf"
LATO_DIR = Path("/usr/share/fonts/truetype/lato")


def render_manual(output, version):
    for style in ("Regular", "Bold", "Heavy"):
        font_path = LATO_DIR / f"Lato-{style}.ttf"
        if not font_path.is_file():
            raise FileNotFoundError(
                "Font Lato mancanti. Su Debian o Ubuntu installa fonts-lato."
            )
        pdfmetrics.registerFont(TTFont(f"Lato-{style}", str(font_path)))
    pdfmetrics.registerFontFamily(
        "Lato-Regular", normal="Lato-Regular", bold="Lato-Bold"
    )
    W, H = A4
    M = 37
    CW = W - 2 * M
    NAVY = "#152B45"
    TEAL = "#006B66"
    INK = "#24374A"
    MUTED = "#4D6174"
    BORDER = "#CCD8E3"
    pdf = canvas.Canvas(output, pagesize=A4, invariant=True)
    pdf.setTitle("QC Inspector | Manuale operativo")
    pdf.setSubject(f"Istruzioni operative per QC Inspector {version}")
    pdf.setAuthor("QC Inspector")

    def color(hexval):
        return HexColor(hexval)

    def label(x, y, s, size=10, font="Lato-Bold", fill=NAVY):
        pdf.setFillColor(color(fill))
        pdf.setFont(font, size)
        pdf.drawString(x, y, s)

    def para(x, top, width, s, size=11.6, leading=15, fill=INK):
        p = Paragraph(
            s,
            ParagraphStyle(
                "body",
                fontName="Lato-Regular",
                fontSize=size,
                leading=leading,
                textColor=color(fill),
            ),
        )
        _, h = p.wrap(width, 1000)
        p.drawOn(pdf, x, top - h)
        return top - h

    def begin(n, section, title, subtitle, key):
        pdf.bookmarkPage(key)
        pdf.addOutlineEntry(title, key)
        pdf.setFillColor(color(NAVY))
        pdf.rect(0, H - 124, W, 124, fill=1, stroke=0)
        pdf.setFillColor(color("#4FD0BC"))
        pdf.rect(M, H - 47, 19, 2, fill=1, stroke=0)
        label(M + 28, H - 50, "QC INSPECTOR  /  " + section, 10, "Lato-Bold", "#C1E0E4")
        label(M, H - 87, title, 31, "Lato-Heavy", "#FFFFFF")
        label(M, H - 107, subtitle, 11, "Lato-Regular", "#DCE7F1")
        pdf.setStrokeColor(color(BORDER))
        pdf.line(M, 45, W - M, 45)
        label(M, 28, f"QC INSPECTOR {version}   /   MANUALE OPERATIVO", 8.5, fill=MUTED)
        label(W - M - 30, 28, f"{n:02d} / 16", 8.5, fill=MUTED)
        return H - 147

    def picture(y, name, caption, max_h=500, max_w=CW, crop=None):
        with Image.open(SCREENSHOTS / f"{name}.png") as file:
            im = file.copy() if crop is None else file.crop(crop)
        scale = min(max_w / im.width, max_h / im.height)
        w, h = im.width * scale, im.height * scale
        x = M + (CW - w) / 2
        pdf.drawImage(ImageReader(im), x, y - h, w, h)
        pdf.setStrokeColor(color(BORDER))
        pdf.setLineWidth(0.7)
        pdf.rect(x, y - h, w, h, stroke=1, fill=0)
        return para(M, y - h - 6, CW, caption, 9.2, 11, MUTED) - 16

    def steps(y, items, start=1):
        for number, item in enumerate(items, start):
            label(M + 1, y - 11, str(number) + ".", 10, fill=TEAL)
            y = para(M + 20, y, CW - 20, item) - 8
        return y

    def box(y, heading, body, tone="info"):
        bg, accent = ("#E8F5F2", TEAL) if tone == "info" else ("#FFF1D9", "#875014")
        p = Paragraph(
            body,
            ParagraphStyle(
                "note",
                fontName="Lato-Regular",
                fontSize=11.15,
                leading=14.5,
                textColor=color(INK),
            ),
        )
        _, h = p.wrap(CW - 28, 1000)
        height = h + 38
        pdf.setFillColor(color(bg))
        pdf.roundRect(M, y - height, CW, height, 7, fill=1, stroke=0)
        label(M + 14, y - 18, heading, 9.8, "Lato-Heavy", accent)
        p.drawOn(pdf, M + 14, y - 26 - h)
        return y - height - 12

    def end(y):
        assert y > 49, (pdf.getPageNumber(), y)
        pdf.showPage()

    y = begin(
        1,
        "FINESTRA PRINCIPALE",
        "Manuale operativo",
        "QC Inspector · Dalla preparazione del setup alla consultazione dei lotti.",
        "home",
    )
    y = picture(
        y,
        "home",
        "Finestra principale · Accesso alle quattro aree, ultimi collaudi e qualità fornitori.",
        315,
        crop=(0, 0, 1070, 730),
    )
    y = steps(
        y,
        [
            "<b>Programmazione</b> (pag. 2). Crea il setup da un disegno PDF o aggiorna un setup esistente.",
            "<b>Controllo</b> (pag. 4). Avvia il lotto, registra le misure e genera il report.",
            "<b>Configurazione</b> (pag. 9). Gestisci anagrafiche, classi, piani e impostazioni.",
            "<b>Storico lotti</b> (pag. 15). Consulta i collaudi salvati e recupera i report.",
        ],
    )
    y = box(
        y,
        "ULTIMI CONTROLLI E QUALITÀ FORNITORI",
        "La tabella mostra gli ultimi sei collaudi registrati. Nel grafico <b>Qualità fornitori</b>, scegli 6, 12 o 24 mesi e confronta i pezzi conformi, in deroga e FAIL. In basso, <b>Manuale d’uso</b> apre il manuale nel lettore PDF del sistema.",
    )
    y = para(
        M,
        y,
        CW,
        "Per il primo collaudo, usa <b>PF-001 - Piastra di fissaggio (esempio)</b> in un archivio di prova appena inizializzato. L’esempio <b>PROVA-001</b> inizia a pagina 4.",
        10.5,
        14,
        MUTED,
    )
    end(y)

    y = begin(
        2,
        "PROGRAMMAZIONE",
        "Gestisci i setup",
        "Cerca, apri o crea un setup di controllo.",
        "gestione",
    )
    y = picture(
        y,
        "gestione",
        "Gestione setup · Ricerca, classe di collaudo e stato del setup.",
        275,
    )
    y = steps(
        y,
        [
            "Dalla schermata principale apri <b>Programmazione</b>. Si apre <b>Gestione setup</b>.",
            "Digita parte del nome o del codice. Seleziona la riga e apri il setup. Per iniziare da un disegno nuovo, premi <b>Nuovo setup</b>.",
            "Per togliere un setup dall’elenco dei nuovi controlli, selezionalo e premi <b>Rendi obsoleto</b>. Usa <b>Riattiva setup</b> per renderlo di nuovo disponibile.",
            "Usa <b>Elimina setup</b> solo per un setup senza collaudi salvati. Verifica il numero di controlli indicato nella conferma.",
        ],
    )
    y = box(
        y,
        "REVISIONI",
        "Quando salvi una modifica, QC Inspector crea una revisione. Ogni lotto salvato resta collegato al disegno, alle quote e alle tolleranze usati per quel collaudo.",
    )
    end(y)

    y = begin(
        3,
        "PROGRAMMAZIONE",
        "Prepara il setup",
        "Associa ogni misura alla posizione sul disegno.",
        "setup",
    )
    y = picture(
        y,
        "setup",
        "PF-001 · Pallinatura 4 selezionata nel modulo Definizione controllo.",
        273,
    )
    y = steps(
        y,
        [
            "Apri <b>Programmazione</b> e premi <b>Nuovo setup</b>. Inserisci il nome e scegli la <b>Classe di Collaudo</b>.",
            "Premi <b>Carica PDF</b>, verifica il disegno e fai clic sulla quota da pallinare.",
            "Seleziona il tipo e la criticità. Per un controllo <b>Dimensionale</b>, inserisci nominale e tolleranze. Per <b>Sì/No</b>, descrivi la verifica.",
            "Premi <b>Applica controllo</b>. Ripeti per tutte le quote, includendo almeno una <b>C - CRITICA</b>.",
            "Verifica ordine e posizione delle pallinature. Premi <b>Salva setup</b>.",
        ],
    )
    y = box(
        y,
        "ESEMPIO · PALLINATURA 4",
        "<b>Diametro foro sinistro</b> · Dimensionale · C - CRITICA · Nominale <b>10,00 mm</b> · Inserisci <b>0,05 mm</b> in entrambi i campi delle tolleranze per ottenere i limiti da 9,95 a 10,05 mm.",
    )
    y = para(
        M,
        y,
        CW,
        "<b>Per correggere il disegno.</b> Seleziona una pallinatura per modificarne la scheda. Trascinala per spostarla. Usa <b>Sposta su</b> o <b>Sposta giù</b> per riordinarla, oppure <b>Elimina selezionato</b> per toglierla. Salva il setup per registrare le modifiche. Rotella per lo zoom, tasto centrale e trascinamento per spostare la vista, doppio clic fuori dalle pallinature per ripristinare la vista.",
        10.5,
        14,
        MUTED,
    )
    end(y)

    y = begin(
        4,
        "CONTROLLO",
        "Avvia il lotto",
        "Controlla i dati prima di iniziare a misurare.",
        "avvio",
    )
    y = picture(
        y,
        "avvio",
        "PROVA-001 · Quantità lotto 1 · Esteso · 1 pezzo da controllare.",
        430,
    )
    y = steps(
        y,
        [
            "In <b>Controllo</b>, seleziona <b>PF-001</b>, <b>Fornitore dimostrativo</b> e <b>Operatore dimostrativo</b>.",
            "Inserisci <b>PROVA-001</b> in <b>N° lotto</b> e <b>1</b> in <b>Q.tà del lotto</b>.",
            "Verifica <b>Tipo di piano</b> e <b>Q.tà da controllare</b>. Premi <b>Avvia controllo</b>.",
        ],
    )
    y = box(
        y,
        "LOTTO DA UN PEZZO",
        "Per ogni criticità presente verifica <b>n = 1</b>, <b>Ac = 0</b> e <b>Re = 1</b>.",
    )
    y = para(
        M,
        y,
        CW,
        "Per un lotto reale inserisci la quantità totale ricevuta. Leggi il motivo del piano suggerito e verifica il campionamento calcolato. Se manca un intervallo per quella quantità, verifica la tabella della classe in <b>Configurazione › Campionamento</b>.",
        10.4,
        14,
        MUTED,
    )
    end(y)

    y = begin(
        5,
        "CONTROLLO",
        "Registra le misure",
        "Segui i numeri delle pallinature sul disegno.",
        "misure",
    )
    y = picture(
        y,
        "misure",
        "PROVA-001 · Tutte le misure inserite. Il pulsante di salvataggio è attivo.",
    )
    y = steps(
        y,
        [
            "Seleziona il campione. Trova sul disegno la pallinatura della quota da misurare.",
            "Inserisci il valore misurato e premi <b>Invio</b>. Con PASS il cursore avanza. Se compare FAIL, ricontrolla pezzo e valore prima di proseguire. Per una verifica, premi <b>Sì</b> o <b>No</b>.",
            "Compila tutte le misure richieste. Verifica la barra di avanzamento e l’esito del lotto.",
            "Premi <b>Salva controllo / Genera report</b>. Per salvare il PDF, segui la pagina 8.",
        ],
    )
    y = box(
        y,
        "PROVA-001 · VALORI IN MM",
        "Per le cinque pallinature inserisci in ordine <b>120,00 · 60,00 · 8,00 · 10,00 · 70,00</b>. Esito atteso <b>PASS</b>. Usa il separatore decimale impostato in <b>Configurazione › Opzioni</b>.",
    )
    y = para(
        M,
        y,
        CW,
        "<b>Modalità standard.</b> Completa tutte le righe di un campione e poi passa al successivo. Per misurare la stessa quota su più pezzi, usa la modalità descritta a pagina 6.",
        10.5,
        14,
        MUTED,
    )
    end(y)

    y = begin(
        6,
        "CONTROLLO",
        "Misura per pallinatura",
        "Ripeti la stessa misura sui campioni previsti.",
        "sequenziale",
    )
    y = picture(
        y,
        "sequenziale",
        "Modalità sequenziale · Il tab della pallinatura contiene una riga per campione.",
    )
    y = steps(
        y,
        [
            "Prima di avviare il lotto, lascia attivo <b>Inserimento controllo per controllo</b> per lavorare per pallinatura. L’opzione è disponibile quando i campioni sono più di due.",
            "Apri il tab della quota oppure seleziona la pallinatura sul disegno.",
            "Registra il valore per ogni campione presente nel tab. Premi <b>Successivo</b> per passare alla quota seguente.",
            "Controlla l’avanzamento prima di salvare. Ogni quota richiede il numero di campioni della propria criticità.",
        ],
    )
    y = box(
        y,
        "ESEMPIO · PF-001, LOTTO DA 100",
        "Con il piano Normale predefinito, il foro sinistro (C) richiede 20 misure e la lunghezza (N) ne richiede 8. Il riepilogo dimensionale mostra la media e, da 10 misure con dispersione positiva e limiti validi, Cp e Cpk.",
    )
    end(y)

    y = begin(
        7,
        "CONTROLLO",
        "Gestisci un FAIL",
        "Registra la deroga solo dopo l’autorizzazione.",
        "deroga",
    )
    y = picture(
        y,
        "deroga",
        "PROVA-002 · Esempio di registrazione della deroga per la pallinatura 4.",
    )
    y = steps(
        y,
        [
            "Verifica la quota, il pezzo e il valore inserito. Se correggi il valore, verifica di nuovo l’esito.",
            "Se il FAIL è confermato e hai l’autorizzazione, spunta <b>Accetta in deroga</b> sulla riga.",
            "Completa le misure e premi <b>Salva controllo / Genera report</b>.",
            "Nel riepilogo verifica le righe. Compila <b>Motivazione</b> e <b>Autorizzato da</b>. Conferma.",
        ],
    )
    y = box(
        y,
        "ESEMPIO · FORO FUORI TOLLERANZA",
        "Il foro della pallinatura 4 deve stare tra <b>9,95 e 10,05 mm</b>. Con <b>10,10 mm</b> e le altre quattro misure conformi, il lotto unitario è <b>FAIL</b>. Dopo la deroga autorizzata il lotto è <b>ACCETTATO IN DEROGA</b> e la misura resta fuori tolleranza.",
        "warn",
    )
    y = para(
        M,
        y,
        CW,
        "<b>Prima di uscire.</b> Se confermi <b>Interrompere Controllo</b> o chiudi la finestra senza salvare, perdi la bozza e il lotto non compare nello Storico.",
        10.5,
        14,
        MUTED,
    )
    y = box(
        y,
        "ESITO DI UN LOTTO CAMPIONATO",
        "Entro <b>Ac</b> il lotto resta PASS. Quando una criticità raggiunge <b>Re</b>, il lotto è FAIL se resta un difetto non derogato tra le criticità che hanno raggiunto la soglia. Se tutti quei difetti sono derogati, il lotto è accettato in deroga.",
    )
    end(y)

    y = begin(
        8,
        "CONTROLLO",
        "Chiudi il lotto",
        "Salva il collaudo e verifica il report del singolo lotto.",
        "chiusura",
    )
    y = steps(
        y,
        [
            "Completa tutte le misure e premi <b>Salva controllo / Genera report</b>.",
            "Se richiesto, scegli <b>Sì</b> per generare il PDF e indica la destinazione. Se il salvataggio automatico è attivo, verifica il percorso comunicato dall’app.",
            "Nel report verifica codice lotto, piano, misure ed esito. Se la stampa automatica è attiva, verifica anche l’etichetta.",
        ],
    )
    y = picture(
        y,
        "report",
        "Report di PROVA-001 · Estratto con piano, misure ed esito PASS.",
        350,
        CW,
        (22, 116, 1478, 872),
    )
    y = box(
        y,
        "PDF O ETICHETTA MANCANTE",
        "Se compare la conferma di salvataggio, il lotto è già nello <b>Storico lotti</b>. Per recuperare il PDF vai a pagina 15. Per la stampa verifica <b>Configurazione › Etichetta</b>.",
    )
    end(y)

    y = begin(
        9,
        "CONFIGURAZIONE",
        "Operatori e fornitori",
        "Prepara le anagrafiche da selezionare all’avvio del collaudo.",
        "anagrafiche",
    )
    y = picture(
        y, "operatore", "Operatori · Scheda dell’operatore dimostrativo.", 181, 380
    )
    y = steps(
        y,
        [
            "Apri <b>Configurazione › Operatori</b> e premi <b>Nuovo operatore</b>. Inserisci nome e cognome. Aggiungi recapiti e note se servono, poi salva."
        ],
    )
    y = picture(
        y, "fornitore", "Fornitori · Scheda del fornitore dimostrativo.", 192, 380
    )
    y = steps(
        y,
        [
            "Apri <b>Fornitori</b> e premi <b>Nuovo fornitore</b>. Inserisci la ragione sociale. Se disponibili, aggiungi partita IVA o codice fiscale, referente e recapiti. Salva.",
            "Per aggiornare una voce, seleziona la riga e premi <b>Modifica</b>. Usa <b>Elimina</b> per rimuoverla dall’anagrafica. I nomi già registrati nei lotti rimangono nello storico.",
        ],
    )
    end(y)

    y = begin(
        10,
        "CONFIGURAZIONE",
        "Classi di collaudo",
        "Definisci quali piani e regole si applicano a un setup.",
        "classi",
    )
    y = picture(
        y, "classe", "Classi di campionamento · Impostazioni della classe DEFAULT.", 282
    )
    y = steps(
        y,
        [
            "Apri <b>Classi di campionamento</b> e premi <b>Nuova classe</b>. Inserisci un codice univoco e una descrizione.",
            "Imposta i giorni di validità dello storico e i PASS richiesti per passare da Esteso a Normale, poi da Normale a Ridotto.",
            "Decidi se un esito negativo riporta il suggerimento a Esteso e se le deroghe contano come esiti positivi. Salva.",
            "In <b>Campionamento</b> consulta le tre tabelle create per la classe. In <b>Programmazione</b> assegna la classe al setup.",
        ],
    )
    y = box(
        y,
        "ESEMPIO · PIANO SUGGERITO",
        "Con i valori mostrati, un PASS Esteso valido per la stessa coppia setup-fornitore fa proporre Normale. Due PASS Normali validi fanno proporre Ridotto. Senza storico valido viene proposto Esteso. All’avvio puoi scegliere un piano diverso.",
    )
    y = para(
        M,
        y,
        CW,
        "Per eliminare una classe, assegna prima un’altra classe ai setup collegati. La classe predefinita resta sempre disponibile.",
        10.6,
        14,
        MUTED,
    )
    end(y)

    y = begin(
        11,
        "CONFIGURAZIONE",
        "Verifica il campionamento",
        "Controlla la classe, il piano e le soglie applicate.",
        "config",
    )
    y = picture(
        y,
        "config",
        "Configurazione › Campionamento · Tabelle della classe DEFAULT.",
        233,
    )
    y = steps(
        y,
        [
            "In <b>Operatori</b> e <b>Fornitori</b>, verifica che siano presenti le voci da usare nel lotto.",
            "In <b>Campionamento</b>, seleziona la classe del setup e il piano <b>Esteso</b>, <b>Normale</b> o <b>Ridotto</b> per consultare la tabella. Se modifichi le soglie, premi <b>Salva tabelle</b>.",
            "All’avvio del lotto leggi <b>n</b> (pezzi da controllare), <b>Ac</b> (difettosi ammessi) e <b>Re</b> (soglia di rifiuto) per ciascuna criticità presente.",
        ],
    )
    y = box(
        y,
        "ESEMPIO · LOTTO DA 100, PIANO NORMALE PREDEFINITO",
        "Con C, I e N presenti, controlla le quote <b>C su 20 pezzi</b>, le <b>I su 13</b> e le <b>N su 8</b>. Nel campo <b>Q.tà da controllare</b> compare <b>20</b>.",
    )
    y = steps(
        y,
        [
            "Per modificare un valore fai doppio clic sulla cella. Per modificare una soglia di rifiuto cambia <b>Ac</b>. Il programma aggiorna <b>Re = Ac + 1</b>.",
            "Usa <b>Aggiungi riga</b> o <b>Elimina riga</b> per gli intervalli. Parti da 2, verifica che gli intervalli siano consecutivi e imposta l’ultimo massimo a infinito. Premi <b>Salva tabelle</b> dopo aver controllato la validazione.",
        ],
        start=4,
    )
    y = para(
        M,
        y,
        CW,
        "<b>Ripristina predefiniti</b> ricarica il piano selezionato. Premi <b>Salva tabelle</b> per registrare il ripristino. Più FAIL della stessa criticità sullo stesso pezzo contano come un solo pezzo difettoso.",
        10.5,
        14,
        MUTED,
    )
    end(y)

    y = begin(
        12,
        "CONFIGURAZIONE",
        "Opzioni e report",
        "Imposta l’inserimento delle misure e l’uscita dei PDF.",
        "opzioni",
    )
    y = picture(
        y,
        "opzioni",
        "Opzioni · Separatore decimale, audio e percorsi dei dati.",
        198,
        CW,
        (0, 0, 1240, 492),
    )
    y = steps(
        y,
        [
            "In <b>Opzioni</b>, scegli punto o virgola e imposta il feedback audio. Usa <b>Prova</b> per verificare i suoni PASS e FAIL, poi premi <b>Salva opzioni</b>. Riapri la finestra operativa per usare il nuovo separatore.",
            "Consulta <b>Database</b> e <b>Cartella PDF</b> per trovare l’archivio dei dati e i disegni. Usa <b>Sfoglia…</b> per aprire la cartella.",
        ],
    )
    y = picture(
        y,
        "configreport",
        "Report · Impostazioni per logo, testo a piè di pagina e destinazione.",
        198,
        CW,
        (0, 0, 1240, 492),
    )
    y = steps(
        y,
        [
            "In <b>Report</b>, imposta logo e testo a piè di pagina. Scegli la cartella di destinazione se vuoi il salvataggio automatico, poi premi <b>Salva opzioni report</b>.",
        ],
    )
    y = box(
        y,
        "DOVE TROVARE I REPORT AUTOMATICI",
        "Nella cartella scelta, apri la sottocartella del <b>fornitore</b>, poi quelle dell’<b>anno</b> e del <b>mese</b> del lotto.",
    )
    end(y)

    y = begin(
        13,
        "CONFIGURAZIONE",
        "Etichetta",
        "Imposta la stampante e verifica il modello con una prova.",
        "etichetta",
    )
    y = picture(
        y,
        "etichetta",
        "Etichetta · Modello a sinistra e anteprima con dati di esempio a destra.",
    )
    y = steps(
        y,
        [
            "Apri <b>Configurazione › Etichetta</b>. Seleziona <b>Stampante CUPS</b>. Se manca la stampante, premi <b>Aggiorna</b> e controlla che sia configurata in CUPS.",
            "Imposta <b>Numero di copie</b>, larghezza e altezza in millimetri in base al supporto disponibile.",
            "Scrivi il testo del modello. Usa <b>Inserisci campo</b> per aggiungere dati come lotto ed esito. Verifica il risultato nell’anteprima.",
            "Premi <b>Stampa di prova</b> per controllare la resa. Se vuoi stampare alla chiusura di ogni collaudo, abilita l’opzione automatica e premi <b>Salva etichetta</b>.",
        ],
    )
    y = box(
        y,
        "ESEMPIO · CONTENUTO",
        "Usa <b># Controllo qualità</b> come titolo. Sotto, inserisci <b>{lotto}</b> e <b>{esito}</b> usando il selettore dei campi.",
    )
    end(y)

    y = begin(
        14,
        "CONFIGURAZIONE",
        "Backup e ripristino",
        "Salva database e disegni tecnici in un archivio ZIP.",
        "backup",
    )
    y = picture(
        y,
        "backup",
        "Backup · Scelta della destinazione e comandi di esportazione e ripristino.",
    )
    label(M, y - 9, "Crea una copia", 14)
    y = steps(
        y - 23,
        [
            "Apri <b>Configurazione › Backup</b>, premi <b>Sfoglia…</b> e scegli la cartella.",
            "Premi <b>Esegui backup</b>. Verifica il percorso dell’archivio indicato nella conferma.",
            "Conserva a parte eventuali report esportati e i file di configurazione.",
        ],
    )
    label(M, y - 9, "Ripristina i dati", 14)
    y = steps(
        y - 23,
        [
            "Chiudi Programmazione, Controllo e Storico lotti. Premi <b>Ripristina backup…</b> e seleziona lo ZIP.",
            "Scegli <b>Aggiungi ai dati esistenti</b> per importare il contenuto. Se trovi un setup omonimo puoi rinominare quello importato. Con <b>Sostituisci</b> vengono sostituiti anche i lotti e le misure locali di quel setup.",
            "Per tornare interamente ai dati dello ZIP, scegli <b>Ripristino completo</b>. Verifica che nessun altro utente stia lavorando sui dati prima di confermare.",
        ],
    )
    y = box(
        y,
        "RIPRISTINO COMPLETO",
        "Il ripristino completo sostituisce il database e i disegni locali. QC Inspector crea una copia di sicurezza dei dati correnti nella destinazione scelta.",
        "warn",
    )
    end(y)

    y = begin(
        15,
        "STORICO LOTTI",
        "Consulta i collaudi",
        "Cerca un lotto, leggi le misure e recupera il PDF.",
        "storico",
    )
    y = picture(
        y,
        "storico",
        "Lotti e statistiche · PROVA-001 con esito PASS e stato CHIUSO.",
        238,
    )
    y = steps(
        y,
        [
            "Apri <b>Storico lotti</b> e scegli il setup. Puoi cercarlo digitando parte del nome.",
            "In <b>Lotti e statistiche</b>, seleziona il lotto. Verifica revisione, quantità, piano, esito e stato. Usa i grafici per leggere la conformità per lotto e i FAIL per pallinatura.",
            "Per esportare il PDF del lotto selezionato, premi <b>Rigenera report PDF</b> e scegli la destinazione.",
            "Apri <b>Dettaglio quote</b> per consultare numero di misure, media, minimo, massimo, deviazione standard e FAIL per quota.",
        ],
    )
    y = picture(
        y,
        "quote",
        "Dettaglio quote · Riepilogo dimensionale per le cinque pallinature di PF-001.",
        156,
    )
    end(y)

    y = begin(
        16,
        "STORICO LOTTI",
        "Report globale fornitori",
        "Confronta la qualità dei fornitori su un periodo.",
        "globale",
    )
    y = picture(
        y, "periodo", "Finestra di selezione delle date del report globale.", 151, 405
    )
    y = steps(
        y,
        [
            "In <b>Storico lotti</b> premi <b>Stampa Report Globale</b>.",
            "Imposta <b>Data inizio</b> e <b>Data fine</b>. Premi <b>Genera report PDF</b> e scegli il file di destinazione.",
            "Leggi riepilogo, classifica fornitori e dettaglio dei lotti. Il PDF include i lotti completi, chiusi e non annullati di tutti i setup nel periodo.",
        ],
    )
    y = picture(
        y,
        "globale",
        "Estratto del report globale generato con il lotto dimostrativo.",
        238,
        CW,
        (32, 32, 1268, 595),
    )
    y = box(
        y,
        "COME LEGGERE I RISULTATI",
        "Ogni pezzo conta una volta. Un FAIL non derogato classifica il pezzo come FAIL. Se tutti i FAIL sono derogati, il pezzo è accettato in deroga. Le percentuali con meno di 30 pezzi controllati sono segnalate come poco rappresentative.",
    )
    end(y)
    pdf.save()


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    version = run_path(str(ROOT / "src/qc_inspector/__init__.py"))["__version__"]
    document = BytesIO()
    render_manual(document, version)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=args.output.parent, delete=False) as temporary:
        temporary_path = Path(temporary.name)
        try:
            temporary.write(document.getbuffer())
            temporary.close()
            temporary_path.chmod(0o644)
            temporary_path.replace(args.output)
        finally:
            temporary_path.unlink(missing_ok=True)
    print(f"Manuale QC Inspector {version}: {args.output}")


if __name__ == "__main__":
    main()
