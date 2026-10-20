# Ghid de utilizare AutoMailCAT

Pentru teamleaderi, înlocuitori și oricine configurează o echipă. Nu sunt necesare cunoștințe de programare.

## 1. Ce trebuie pe PC

- Windows, cu **Outlook clasic** deschis și căsuța partajată vizibilă în lista de foldere din stânga.
- **Python 3.10 sau mai nou**, de pe python.org. La instalare bifează *Add python.exe to PATH*.
- Folderul comun al echipei, sincronizat din Teams/SharePoint: în Teams, la canal → *Fișiere* → *Sincronizare* (sau *Adaugă comandă rapidă la OneDrive*).

Motorul trebuie să ruleze pe **un singur PC** al echipei, dar AutoMailCAT poate fi instalat pe mai multe: pe celelalte doar se configurează, iar dacă PC-ul principal se închide, unul dintre ele preia automat.

## 2. Instalare

1. Pe GitHub: **Code → Download ZIP**. Dezarhivează, de exemplu în `Documente\AutoMailCAT`.
2. Dublu-clic pe **install.bat**. Durează un minut. Ca AutoMailCAT să pornească odată cu Windows, poți bifa mai târziu opțiunea în **Instalare**.
3. Dublu-clic pe **start.bat**. Se deschide pagina AutoMailCAT în browser, iar lângă ceas apare iconița (plic cu bifă). Clic dreapta pe iconiță: Deschide, Procesează acum, Pauză, Ieșire.

Pentru o probă fără Outlook folosește **start-demo.bat**: echipă, agenți, reguli și căsuță fictive.

## 3. Prima configurare a unei echipe

### 3.1 Folderul echipei (Instalare)
**Instalare → Adaugă o echipă → Alege folder…**, selectează folderul sincronizat al echipei. Dacă folderul e nou, completează și numele echipei și căsuța partajată. Înlocuitorul face același lucru pe PC-ul lui, cu același folder, și vede aceleași setări.

### 3.2 Echipa (Echipă)
- **Căsuța partajată**: numele exact din lista de foldere a Outlook-ului (sau adresa ei).
- **Cum apare echipa în mailuri**: formele în care oamenii scriu numele echipei, câte una pe rând.
- **Ce face cu mailul**: pune categoria, mută mailul în folderul agentului, sau ambele.
- **Categoria pentru „de verificat”**: unde ajung mailurile pe care nu le poate aloca nimănui.
- **Logica de alocare**: fiecare pas poate fi pornit sau oprit. Tot aici alegi ce se întâmplă când nici backup-ul nu e disponibil și ce se întâmplă înainte de confirmarea zilei.
- **Cine poate modifica**: utilizatorii Windows cu drept de modificare. Gol = oricine are acces la folder.

### 3.3 Agenții (Agenți)
Pentru fiecare agent: prenume, nume, adresă de e-mail, categoria din Outlook (implicit „Prenume Nume”), folderul (în modul cu foldere; butonul **Alege din Outlook** listează folderele căsuței), backup-urile în ordine și alte forme ale numelui.

După ce ai agenții și regulile: **Echipă → Creează categoriile lipsă în Outlook**.

### 3.4 Regulile (Reguli)
Regulile se citesc de sus în jos, ca în Outlook. Le ordonezi trăgându-le cu mouse-ul sau cu săgețile.

| Câmp | Exemplu | Înseamnă |
|---|---|---|
| Conține TOATE cuvintele | `factur*` și `restant*` | ambele trebuie să apară |
| Conține CEL PUȚIN UNUL | `downtime`, `mentenanta` | ajunge unul |
| NU conține niciunul | `anulat*` | dacă apare, regula nu se aplică |
| Expeditorul conține | `newsletter.test` | adresa sau numele expeditorului |
| Cine primește mailul | un agent / rotație / nimeni | „nimeni” = doar categorie sau folder |

- Nu contează literele mari sau diacriticele: „factură” = „factura”.
- `*` la final prinde orice terminație: `factur*` → factura, facturi, facturilor.
- O regulă fără agent și cu „Oprește evaluarea” debifat este **informativă**: adaugă categoriile ei (ex. „Downtime”) și mailul își continuă drumul. Așa un mail poate primi mai multe categorii.

În dreapta, **Testează un mail**: scrii subiectul și textul și vezi pas cu pas cui ar ajunge. Testul folosește și modificările nesalvate și nu schimbă nimic în Outlook.

## 4. În fiecare dimineață

1. Deschide **Ziua de azi**. Propunerea este copiată din ultima zi lucrată.
2. Pentru fiecare agent alege:
   - **În rotație**: primește mailuri prin rotație.
   - **Exclus**: alt task, training, ședință… Alegi motivul din listă și ce primește totuși (firele lui, mailurile în care e numit, To/CC, reguli, importanță High).
   - **Absent**: mailurile pentru el merg la backup.
3. **Intervale**: ordinea poate fi diferită în intervale diferite (ex. 08:00–12:00 și 12:00–17:00). Trage numele în ordinea dorită. Agenții excluși sau absenți rămân în listă, dar sunt săriți automat.
4. **Confirmă ziua** și răspunde la întrebări:
   - ce se întâmplă cu mailurile sosite înainte de confirmare (se împart acum sau rămân pentru împărțire manuală);
   - rotația începe de la primul sau continuă;
   - se trimite sau nu mesajul zilnic.
5. Mesajul „Distribuirea mailurilor pentru ziua dd.mm.yyyy” pleacă în Teams sau îl copiezi cu **Copiază mesajul**. Vezi [TEAMS-MESAJ.md](TEAMS-MESAJ.md).

## 5. Schimbări în timpul zilei

Modifici ce s-a schimbat (de exemplu cineva devine *Absent*) și apeși **Regenerează**. Alegi din listă:
- motivul schimbării (rămâne în istoricul zilei);
- ce se întâmplă cu mailurile deja alocate azi celor care nu mai sunt în rotație: rămân la ei / merg la backup / se împart din nou / ajung la „De verificat”;
- dacă rotația continuă sau reîncepe;
- dacă se retrimite mesajul.

Mailurile la care cineva a schimbat manual categoria nu sunt mutate.

## 6. Jurnal

Fiecare mail procesat, cu ora, agentul și pasul care a decis (fir, nume, regulă, rotație…). Clic pe un rând arată explicația completă. Poți filtra după agent sau după pas.

## 7. Întrebări frecvente

**Ce se întâmplă dacă se închide laptopul pe care rulează motorul?** După câteva minute (setarea *Alt PC preia motorul după*) preia alt PC pe care AutoMailCAT e pornit cu Outlook deschis. Dacă nu e niciunul, mailurile se procesează la următoarea pornire.

**Un agent a mutat sau recategorisit manual un mail. Îl strică AutoMailCAT?** Nu. Un mail care are deja categoria unui agent nu mai e atins, iar reply-urile urmează categoria pusă de om.

**De ce nu s-a pus categoria pe agentul numit în mail?** Cel mai des, în mail apare doar prenumele, sau lipsește numele echipei. Pagina Reguli → Testează arată exact motivul.

**Pot folosi virgula în numele unei categorii?** Nu. Outlook folosește virgula (sau punct și virgula) ca separator între categorii.

**Merge cu noul Outlook?** Nu. Noul Outlook nu permite unei aplicații să lucreze cu mailurile. E nevoie de Outlook clasic.

**Unde sunt jurnalul aplicației și setările locale?** În `%LOCALAPPDATA%\AutoMailCAT` (folderul `logs`). Setările echipei sunt în folderul comun al echipei.

## 8. DevPilot

Dacă folosești DevPilot: **Add tool** → Python → alege `automailcat.py`, apoi **From devpilot.tool.json**. Opțiunile AutoMailCAT apar în hub, iar iconița, pornirea cu Windows și ținerea PC-ului treaz sunt preluate de DevPilot. Fără DevPilot, AutoMailCAT le gestionează singur.
