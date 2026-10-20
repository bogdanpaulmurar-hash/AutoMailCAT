# Mesajul zilnic în Teams

După **Confirmă ziua** sau **Regenerează**, AutoMailCAT poate trimite singur mesajul „Distribuirea mailurilor pentru ziua dd.mm.yyyy”. Ai trei variante, pe care le alegi în **Echipă → Mesajul zilnic în Teams → Cum se trimite**.

| Variantă | Ce trebuie | Cum arată în Teams |
|---|---|---|
| Teams Workflow (recomandat) | un Workflow creat o singură dată în Teams | card cu titlu și secțiuni |
| E-mail către canal | adresa de e-mail a canalului | postare cu subiectul mailului |
| Îl copiez eu | nimic | apeși „Copiază mesajul” și îl lipești în chat |

## Varianta 1: Teams Workflow

Nu necesită licență premium. Îl creează o singură dată cineva din echipă (de obicei teamleaderul).

1. În Teams, deschide **Workflows**. Îl găsești în bara din stânga (sau la „⋯ Mai multe aplicații”), ori din meniul „⋯” al canalului → *Workflows*.
2. Caută șablonul **Send webhook alerts to a channel**. Pentru un chat de grup, alege **Send webhook alerts to a chat**.
3. Dă-i un nume, de exemplu „AutoMailCAT – Echipa X”, și confirmă contul cu care se conectează.
4. Alege **echipa** și **canalul** (sau chatul) unde apare mesajul, apoi **Save** / **Add workflow**.
5. Teams afișează o adresă lungă care începe cu `https://`. Apasă **Copy**.
6. În AutoMailCAT: **Echipă → Cum se trimite → Teams Workflow (webhook)**, lipește adresa în **Adresa Workflow-ului** și apasă **Salvează**.

Probă: în **Ziua de azi**, după confirmare, apasă **Trimite mesajul**.

Bine de știut:
- Mesajul apare în numele celui care a creat Workflow-ul. Dacă acea persoană pleacă din firmă, Workflow-ul trebuie refăcut de altcineva, apoi adresa nouă se pune în AutoMailCAT.
- Adresa Workflow-ului permite oricui o are să posteze în canal. Ține-o doar în setările AutoMailCAT, nu o trimite pe mail sau în chat.
- Dacă un canal privat nu apare în listă, folosește un canal standard sau un chat de grup.
- Dacă nu găsești Workflows în Teams, aplicația e blocată de IT: folosește varianta 2 sau 3.

## Varianta 2: e-mail către adresa canalului

1. În Teams, la canal: **⋯ → Get email address** (Obține adresa de e-mail) → **Copy**.
2. La **Advanced settings** poți alege cine are voie să trimită. „Doar membrii echipei” este suficient dacă PC-ul pe care rulează motorul folosește contul unui membru al echipei.
3. În AutoMailCAT: **Echipă → Cum se trimite → E-mail către adresa canalului**, lipește adresa și apasă **Salvează**.

Mailul pleacă din Outlook-ul PC-ului pe care rulează motorul, deci motorul trebuie să fie pornit în momentul confirmării. Dacă opțiunea „Get email address” lipsește, IT-ul a dezactivat-o: folosește varianta 1 sau 3.

## Varianta 3: copiere manuală

Este varianta implicită. După confirmare, în **Ziua de azi** apeși **Copiază mesajul** și îl lipești în canalul sau chatul echipei.
