# QC Inspector — componenti e materiali di terzi

Questo documento accompagna le distribuzioni binarie di QC Inspector. Le
versioni indicate sono quelle dell'ambiente con cui è stato verificato il
pacchetto 1.3.5 il 13 settembre 2026. Una build prodotta con versioni diverse
deve aggiornare inventario, avvisi, testi di licenza e sorgenti corrispondenti.

QC Inspector non modifica né rilicenzia questi componenti. I testi completi
disponibili sono nella directory `third_party/licenses/`.

## Componenti Python e runtime

| Componente | Versione verificata | Licenza dichiarata dal pacchetto | Uso nella distribuzione |
|---|---:|---|---|
| CPython | 3.14.4 | PSF License | Runtime incluso dal bundle PyInstaller |
| PyQt5 | 5.15.11 | GPL v3 | Binding GUI; incluso nel bundle |
| PyQt5-Qt5 / Qt | 5.15.19 | LGPL v3 | Librerie e plugin Qt inclusi nel bundle |
| PyQt5-sip | 12.18.0 | BSD-2-Clause | Runtime dei binding PyQt5 |
| PyMuPDF e MuPDF | 1.27.2.3 | AGPL v3 oppure licenza commerciale Artifex | Lettura, rendering e modifica PDF; incluso nel bundle sotto AGPL v3 |
| ReportLab | 4.5.1 | BSD-3-Clause | Generazione report ed etichette PDF |
| Pillow e librerie incorporate nella wheel | 12.2.0 | MIT-CMU e licenze riportate nel relativo file cumulativo | Dipendenza runtime di ReportLab; inclusa nel bundle |
| charset-normalizer | 3.4.7 | MIT | Dipendenza runtime di ReportLab |
| PyInstaller | 6.20.0 | GPL-2.0-or-later con Bootloader Exception; runtime hook Apache-2.0 | Strumento di build e bootloader incluso nell'eseguibile |
| PyInstaller hooks contrib | 2026.5 | GPL-2.0-or-later con eccezione PyInstaller | Strumento di build |
| altgraph | 0.17.5 | MIT | Dipendenza di build di PyInstaller |
| packaging | 26.2 | Apache-2.0 OR BSD-2-Clause | Dipendenza di build di PyInstaller |

Riferimenti di progetto e sorgente dichiarati dai rispettivi distributori:

- CPython: `https://www.python.org/downloads/source/`
- PyQt5 e PyQt5-sip: `https://www.riverbankcomputing.com/software/pyqt/`
- Qt: `https://download.qt.io/official_releases/qt/`
- PyMuPDF: `https://github.com/pymupdf/pymupdf`
- ReportLab: `https://www.reportlab.com/opensource/`
- Pillow: `https://github.com/python-pillow/Pillow`
- charset-normalizer: `https://github.com/jawah/charset_normalizer`
- PyInstaller: `https://github.com/pyinstaller/pyinstaller`

Font: il progetto non distribuisce file font propri. I report richiamano i
nomi PDF Base 14 `Helvetica` e `Helvetica-Bold`; il rendering usa i meccanismi
forniti da ReportLab, MuPDF e dal sistema.

## Librerie native

Il bundle PyInstaller verificato contiene inoltre librerie native provenienti
dalle wheel sopra indicate o dal sistema di build. Tra queste: Qt 5, MuPDF,
OpenSSL, SQLite, Pillow e i suoi codec, X11/XCB, Fontconfig, FreeType, PulseAudio,
ALSA, libsndfile, FLAC, Ogg/Vorbis, Opus, libpng, zlib, zstd, Brotli, PCRE2,
D-Bus, Kerberos, libffi, liblzma, ncurses/readline, systemd e librerie runtime
GNU. I rispettivi titolari mantengono copyright e licenze.

Il pacchetto Debian richiede GStreamer e CUPS come dipendenze di sistema.
La build comune a Debian e portable rimuove le copie di GStreamer e GLib
individuate da PyInstaller e usa quelle di sistema. Per le altre librerie
incorporate, per ogni release l'elenco
effettivo deve essere conservato insieme ai testi di licenza e ai sorgenti
corrispondenti della stessa build.

## Asset del progetto

| File | SHA-256 | Stato della provenienza |
|---|---|---|
| `assets/audio/error.oga` | `5eeef8230c3969453c019ab4289a95705254c502d664f42769a71ee73f484cc1` | `dialog-warning.oga`, sound-theme-freedesktop 0.8; Ivica Bukvic; CC-BY-SA (vedere dettagli sotto) |
| `assets/audio/pass.oga` | `f06d2f85aa1b4c66c2ce5c9cc98459b80a7850cc7454d369529001ca66978199` | `complete.oga`, sound-theme-freedesktop 0.8; Dr. Richard Boulanger et al; CC-BY-3.0 |
| `assets/icons/history.svg` | `f95532d4161ce3b50bc8406c0b9039402990ba97b1679018b61277688aee373f` | Icona originale del titolare di QC Inspector; paternità confermata il 29 settembre 2026 |
| `assets/icons/inspection.svg` | `e0cf3d27487b4db07af6bca9521e9f0e0005b5f4df450ab5ef8b73bada9db97a` | Icona originale del titolare di QC Inspector; paternità confermata il 29 settembre 2026 |
| `assets/icons/master-data.svg` | `e4c84c74c80dc338ba9d32ed708868c7ed994504ce5616b7d0ff205d104425c1` | Icona originale del titolare di QC Inspector; paternità confermata il 29 settembre 2026 |
| `assets/icons/programming.svg` | `ff442ebe01c8454d864678f601cf4ba2764f99f8024aa7c637a3e9d8e6f903e3` | Icona originale del titolare di QC Inspector; paternità confermata il 29 settembre 2026 |
| `assets/icons/qc-inspector-256.png` | `d6ef770f270b7ed4905eeb950d7653e0206f54e22e8d7fee6058aed64bfd8ca2` | Icona originale del titolare di QC Inspector; paternità confermata il 29 settembre 2026 |
| `assets/icons/qc-inspector.png` | `e5efa587b288d1773ceaf0ecf6a60436691f8da1f119531f50505f44ea7064bf` | Icona originale del titolare di QC Inspector; paternità confermata il 29 settembre 2026 |
| `main-icon.png` | `6980b9d9235bb5d14d7d90cb77cdd7628a5fb9d5a19765a988e4299b0f438340` | Icona originale del titolare di QC Inspector; paternità confermata il 29 settembre 2026 |

I valori iniziali dei piani `ESTESO`, `NORMALE` e `RIDOTTO` sono incorporati
in `src/qc_inspector/core/sampling_plans.py`. La cronologia li collega al file
di lavoro `piani_campionamento_ingresso.xlsx`, che non è distribuito.
Il 29 settembre 2026 il titolare di QC Inspector ha dichiarato di avere creato
personalmente le icone e i piani di campionamento. Questi materiali originali
accompagnano il progetto sotto AGPL-3.0-only. I piani sono elaborazioni
dell'autore: non sono presentati come tabelle ufficiali di uno standard.

### Attribuzioni dei suoni

I suoni provengono dal tema freedesktop utilizzato nell'ambiente GNOME.
Il confronto SHA-256 con i file nell'archivio originale
[sound-theme-freedesktop 0.8](https://people.freedesktop.org/~mccann/dist/sound-theme-freedesktop-0.8.tar.bz2)
ha confermato che i contenuti sono identici: è stato cambiato solo il nome.

- `pass.oga`: originale `stereo/complete.oga`, copyright **Dr. Richard
  Boulanger et al**, fonte [Berklee44v11](https://archive.org/details/Berklee44v11),
  licenza [Creative Commons Attribution 3.0 Unported](https://creativecommons.org/licenses/by/3.0/).
- `error.oga`: originale `stereo/dialog-warning.oga`, copyright **Ivica Bukvic**,
  fonte originale indicata da upstream: `http://gnome-look.org/content/show.php/%22Borealis%22+sound+theme?content=12584`.
  I CREDITS upstream indicano **CC-BY-SA** senza numero di versione;
  il pacchetto Ubuntu `sound-theme-freedesktop 0.8-7build1` riporta il testo
  [Creative Commons Attribution-ShareAlike 3.0 Unported](https://creativecommons.org/licenses/by-sa/3.0/).

I CREDITS originali e l'avviso copyright del pacchetto Ubuntu, comprensivo dei
testi CC-BY-3.0 e CC-BY-SA-3.0, sono conservati rispettivamente in
`third_party/licenses/sound-theme-freedesktop-CREDITS.txt` e
`third_party/licenses/sound-theme-freedesktop-copyright.txt`.
I suoni mantengono queste licenze; non sono rilicenziati sotto AGPL.

## Sorgenti corrispondenti

Per una release binaria AGPL/GPL/LGPL non basta indicare pagine web generiche.
La release deve offrire, con modalità conforme alle licenze applicabili, i
sorgenti corrispondenti completi delle versioni realmente distribuite,
compresi script e dati necessari alla ricostruzione e le eventuali modifiche.
Devono essere conservati almeno:

- archivio sorgente di QC Inspector relativo allo stesso tag del binario;
- sorgenti esatti di PyQt5, Qt, PyMuPDF/MuPDF e degli altri componenti
  copyleft inclusi;
- sorgenti e avvisi delle librerie native incorporate dal bundle;
- istruzioni riproducibili per ottenere il binario pubblicato.

Le URL di progetto nei metadati Python sono riferimenti utili, ma non
sostituiscono l'offerta o la consegna dei sorgenti richiesta dalla licenza.
