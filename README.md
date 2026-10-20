# AutoMailCAT

**Română** · [English](#english)

AutoMailCAT împarte automat mailurile dintr-o căsuță Outlook partajată între agenții unei echipe. Pentru fiecare mail nou alege agentul și îi pune categoria (sau mută mailul în folderul lui), după reguli pe care echipa le setează singură, fără cod.

Rulează pe Windows, cu Outlook clasic deschis, ca aplicație Python pornită dintr-un `.bat` (nu este un `.exe`). Interfața se deschide în browser, în română sau engleză.

## Cum alege agentul

Ordinea de verificare pentru fiecare mail:

0. **Reguli informative** (ex. downtime): adaugă categoriile lor, apoi verificarea continuă.
1. **Același fir de discuție**: reply-ul rămâne la agentul care a preluat firul. Dacă cineva a schimbat manual categoria, contează categoria nouă.
2. **Agent numit**: adresa lui în To/CC, sau numele + prenumele + numele echipei în subiect, text sau To/CC.
3. **Reguli cu cuvinte-cheie**, de sus în jos, ca în Outlook: *toate cuvintele*, *cel puțin unul*, *niciunul*, *expeditorul conține*, doar importanță High. Regula poate da mailul unui agent, următorului din rotație sau nimănui (doar categorie / folder).
4. **Rotație strictă** în ordinea intervalului orar curent. Cei excluși (training, alt task…) sau absenți sunt săriți.
5. **De verificat**: o categorie separată, când nimic nu se aplică.

Dacă agentul ales lipsește, mailul merge la **backup-ul lui**, apoi la backup-ul backup-ului. Un agent exclus din rotație poate primi totuși, la alegere: firele lui, mailurile în care e numit, cele în care e în To/CC, cele din reguli sau cele cu importanță High.

## Ziua de lucru

1. Dimineața, teamleaderul (sau înlocuitorul) deschide **Ziua de azi**: propunerea este copiată din ziua anterioară.
2. Pentru fiecare agent alege *În rotație*, *Exclus* (cu motiv) sau *Absent*.
3. Trage numele în ordinea dorită, pe unul sau mai multe intervale orare.
4. **Confirmă ziua**: câteva întrebări cu răspunsuri din listă, apoi mesajul „Distribuirea mailurilor pentru ziua dd.mm.yyyy” pleacă în Teams.
5. Dacă cineva anunță târziu că lipsește: modifici și apeși **Regenerează**. Alegi dacă mailurile deja alocate lui rămân, merg la backup, se împart din nou sau ajung la „De verificat”.

Pagina **Jurnal** arată pentru fiecare mail de ce a ajuns la cine. Pagina **Reguli** are un tester în care încerci un mail fără să schimbi nimic.

## Instalare

Ai nevoie de Windows, **Outlook clasic** și **Python 3.10+** (de pe python.org, cu „Add python.exe to PATH” bifat).

1. Descarcă proiectul (Code → Download ZIP) și dezarhivează-l, de exemplu în `Documente\AutoMailCAT`.
2. Dublu-clic pe `install.bat` (sau `install.bat /autostart` ca să pornească odată cu Windows).
3. Dublu-clic pe `start.bat`. Se deschide interfața, iar lângă ceas apare iconița AutoMailCAT.
4. În **Instalare**, adaugă folderul echipei: un folder din Teams/SharePoint sincronizat pe PC, unde stau setările comune. Toți cei care configurează (teamleader, înlocuitor) adaugă același folder.
5. În **Echipă** completezi căsuța partajată, apoi agenții și regulile.

Vrei doar să încerci? `start-demo.bat` pornește o echipă și o căsuță fictive, fără Outlook.

Ghid complet: [docs/GHID-UTILIZARE.md](docs/GHID-UTILIZARE.md) · Mesajul zilnic în Teams: [docs/TEAMS-MESAJ.md](docs/TEAMS-MESAJ.md)

## Mai multe PC-uri, mai multe echipe

- Fiecare echipă are folderul ei comun și căsuța ei partajată. O instalare poate urmări mai multe echipe.
- **Motorul** (partea care pune categoriile) rulează pe **un singur PC** pe echipă, cel cu Outlook deschis. Dacă acel PC se închide, preia automat altul în câteva minute (configurabil). Se poate alege un PC preferat.
- Mailurile sosite cât timp niciun PC nu rulează se procesează la următoarea pornire.
- Pe ceilalți agenți nu trebuie instalat nimic. Ei văd doar categoriile în Outlook.

## Cu DevPilot sau fără

AutoMailCAT merge singur. Dacă folosești [DevPilot](https://github.com/bogdanpaulmurar-hash/DevPilot), îl adaugi ca tool (Python, `automailcat.py`): fișierul [`devpilot.tool.json`](devpilot.tool.json) îi descrie opțiunile (Deschide, Ziua de azi, Procesează acum, Pauză…). Când e pornit din DevPilot, AutoMailCAT nu mai pune iconița lui în tray, nu își mai face pornirea cu Windows și nu mai ține PC-ul treaz, pentru că acestea sunt preluate de DevPilot.

## Limitări

- Doar **Outlook clasic**: noul Outlook pentru Windows nu are interfața COM de care e nevoie. Microsoft a anunțat suport pentru Outlook clasic cel puțin până în 2029.
- Conținutul atașamentelor nu este citit, doar numele lor.
- Motorul lucrează doar când un PC al echipei e pornit, cu Outlook deschis.

---

## English

AutoMailCAT shares the mails of a shared Outlook mailbox among the agents of a team. For every new mail it chooses the agent and sets his category (or moves the mail to his folder), following rules the team sets up itself, without code.

It runs on Windows with the classic Outlook open, as a Python app started from a `.bat` file (no `.exe`). The interface opens in the browser, in Romanian or English.

### How the agent is chosen

0. **Information rules** (e.g. downtime) add their categories; evaluation continues.
1. **Same conversation**: a reply stays with the agent who owns the thread (a category changed by hand wins).
2. **Agent named**: his address in To/CC, or first name + last name + team name in the subject, body or To/CC.
3. **Keyword rules**, top to bottom like Outlook rules: *all words*, *at least one*, *none of*, *sender contains*, high importance only. A rule gives the mail to an agent, to the next in rotation, or to nobody (category / folder only).
4. **Strict rotation** in the order of the current time interval; agents out of rotation or absent are skipped.
5. **To check**: a separate category when nothing applies.

An absent agent's mails go to his **backup**, then to the backup's backup. An agent out of rotation can still receive, as chosen per day: his own conversations, mails naming him, mails with him in To/CC, rule mails or high importance mails.

### The working day

Each morning the team leader (or stand-in) opens **Today**, marks every agent *in rotation*, *out of rotation* (with a reason) or *absent*, drags the names into order for one or more time intervals and presses **Confirm the day**. A few drop-down questions later the message "Distribuirea mailurilor pentru ziua dd.mm.yyyy" goes to Teams. Late changes: edit and press **Regenerate**, choosing what happens to mails already assigned to someone who is no longer available.

### Setup

Windows, **classic Outlook**, **Python 3.10+**. Download the ZIP, run `install.bat`, then `start.bat`. Under **Setup**, add the team folder (a Teams/SharePoint folder synced on the PC); under **Team**, the shared mailbox, then agents and rules. `start-demo.bat` starts a fictional team and mailbox without Outlook.

Guides: [docs/USER-GUIDE.md](docs/USER-GUIDE.md) · Daily message in Teams: [docs/TEAMS-MESSAGE.md](docs/TEAMS-MESSAGE.md) · Technical overview: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

### With or without DevPilot

AutoMailCAT works on its own. Added to [DevPilot](https://github.com/bogdanpaulmurar-hash/DevPilot), it is described by [`devpilot.tool.json`](devpilot.tool.json) and leaves the tray icon, start with Windows and keep-awake to DevPilot (`DEVPILOT_SUPPRESS`).

### Limits

Classic Outlook only (the new Outlook for Windows has no COM object model); attachment contents are not read, only their names; the engine works only while a team PC with Outlook is on.

### Development

```
python -m unittest discover -s tests -t .
python automailcat.py --demo --no-tray
```

Standard library only, plus `pywin32` (Outlook) and optionally `pystray` + `Pillow` (tray icon).
