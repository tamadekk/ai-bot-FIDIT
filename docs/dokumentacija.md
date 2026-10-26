# Dokumentacija koda

Arhitektonski savjetnik je Flask aplikacija s jednostavnim web sučeljem. Korisnik postavlja pitanja o arhitekturi i uređenju prostora, a chatbot odgovara pomoću Mistral API-ja. Može se učitati vlastiti PDF, DOCX ili TXT dokument, iz kojeg chatbot uzima odgovore. Ova datoteka opisuje kako je to izvedeno, po zadatcima iz vježbe.

## Struktura projekta

| Datoteka | Uloga |
|---|---|
| `backend/server.py` | Flask poslužitelj: rute `/`, `/upload` i `/chat`, poziv modela, pretraga dokumenta, pamćenje razgovora |
| `backend/architecture_context.md` | Zadani kontekst koji se koristi dok korisnik ne učita dokument |
| `backend/tests/` | Unit testovi (`unittest`) |
| `frontend/index.html` | Stranica chata s poljem za pitanje i gumbom „Dodaj dokument” |
| `frontend/script.js` | Slanje pitanja i datoteka backendu, prikaz poruka, gumb za detaljno objašnjenje |
| `frontend/style.css` | Izgled chata, gumba i indikatora „Razmišljam...” |
| `frontend/assets/` | Logotipi i avatari korisnika i chatbota |
| `.env.example` | Predložak konfiguracije bez stvarnog ključa |
| `requirements.txt` | Python paketi |

Flask poslužuje i sučelje iz mape `frontend`, pa se aplikacija otvara na `http://localhost:5000`. Ako se `index.html` otvori izravno kao datoteku (`file://`), preglednik blokira zahtjeve prema `localhost` i gumb „Pošalji” ne radi.

## Zadatak 1: Mistral umjesto Geminija i zaštita ključa

### Gdje je API zamijenjen

Sve promjene su u `backend/server.py`. Iz izvornog koda uklonjen je Gemini SDK i dodan Mistral SDK (`mistralai`, verzija `3.3.0`, klasa `Mistral` iz `mistralai.client.sdk`). Isti klijent služi za chat i za embeddinge.

Razlike u implementaciji:

- Chat zahtjev ide preko `client.chat.complete(model=..., messages=...)`.
- Razgovor se šalje kao lista poruka s ulogama `system`, `user` i `assistant`. Uputa chatbotu i kontekst dokumenta su u prvoj poruci s ulogom `system`.
- Tekst odgovora čita se iz `response.choices[0].message.content`, a ne iz `response.text` kao kod Geminija.
- Embeddingi za pretragu dokumenta rade se modelom `mistral-embed` preko `client.embeddings.create`.

Chat model se čita iz `MISTRAL_CHAT_MODEL`, a zadana vrijednost je `mistral-small-latest`. Funkcija `complete_with_mistral` šalje poruke s temperaturom `0.5` i ograničenjem `max_tokens`, koje ovisi o tome traži li se kratki ili detaljni odgovor.

Ako Mistral vrati HTTP 429 (previše zahtjeva), backend vraća status 429 i poruku da korisnik pričeka pa pokuša ponovno. Ostale greške API-ja vraćaju se kao JSON s porukom i statusom 500, pa sučelje uvijek može prikazati što je pošlo krivo.

### Ključ iz `.env` datoteke

`python-dotenv` pri pokretanju učitava `.env` iz korijena projekta, a kod čita ključ s `os.getenv("MISTRAL_API_KEY")`. Ako ključ nedostaje, server se ne pokreće i javlja `MISSING_ENV: Dodaj MISTRAL_API_KEY u .env datoteku.`

```env
MISTRAL_API_KEY=vas_mistral_kljuc
MISTRAL_CHAT_MODEL=mistral-small-latest
```

Datoteka `.env` navedena je u `.gitignore`, pa ne ulazi u Git. U repozitoriju je samo `.env.example` bez stvarnog ključa.

### Opcionalni Gemini pružatelj

Za testiranje bez Mistral ključa može se u `.env` postaviti:

```env
LLM_PROVIDER=gemini
GEMINI_API_KEY=vas_gemini_kljuc
GEMINI_CHAT_MODEL=gemini-3.5-flash-lite
```

Tada `complete_with_gemini` koristi paket `google-genai`. Sistemska poruka šalje se kao `system_instruction`, uloga `assistant` preimenuje se u `model`, a embeddingi se rade modelom `gemini-embedding-001`. Ostatak aplikacije radi jednako. Bez `LLM_PROVIDER`, ili s vrijednošću `mistral`, koristi se Mistral. Nakon promjene `.env` server treba ugasiti i ponovno pokrenuti, jer Flask u debug načinu pri automatskom ponovnom učitavanju zadržava stare varijable.

## Zadatak 2: Upload dokumenta

1. Korisnik klikne „Dodaj dokument” i odabere datoteku. `script.js` je šalje kao `multipart/form-data` na `POST /upload`.
2. Backend provjerava ekstenziju (`pdf`, `docx`, `txt`), čisti naziv funkcijom `secure_filename` i sprema datoteku u `backend/uploads/`.
3. `extract_text` izdvaja tekst: PDF preko `PyPDF2`, DOCX preko `python-docx`, a TXT se čita kao UTF-8.
4. `chunk_text` dijeli tekst na dijelove od 800 znakova s preklapanjem od 120 znakova, da rečenica na granici dva dijela ne izgubi kontekst. Prazni dijelovi se preskaču.
5. `index_document` za svaki dio traži embedding i sprema ih zajedno u `DOCUMENT_STORE`.

Pri svakom pitanju `find_relevant_context` izračuna embedding pitanja i pomoću NumPy-ja pronađe dijelove dokumenta s najmanjom udaljenosti. Kratki odgovor dobiva 3 najbliža dijela, a detaljni 8. Dok dokument nije učitan, kontekst je `backend/architecture_context.md`.

Ako indeksiranje ne uspije (npr. API vrati grešku), `/upload` vraća JSON s porukom umjesto HTML stranice s greškom. Stari Word format `.doc` nije podržan; datoteku treba spremiti kao `.docx`. Dokument i embeddingi čuvaju se samo u memoriji, pa ga nakon ponovnog pokretanja servera treba ponovno učitati.

## Zadatak 3: Pamćenje razgovora

Svaki preglednik dobiva svoj `session_id` (UUID spremljen u `localStorage`), koji `script.js` šalje uz svako pitanje. Backend po tom ID-u čuva razgovor u rječniku `CONVERSATION_MEMORY`.

- `remember_exchange` nakon svakog odgovora sprema par poruka (korisnik i asistent).
- `trim_conversation_history` zadržava posljednjih 12 poruka (`MAX_CONVERSATION_HISTORY`), da zahtjev prema modelu ne raste bez granice.
- `build_chat_messages` slaže zahtjev ovim redom: sistemska poruka s uputom i kontekstom dokumenta, zatim povijest razgovora, pa novo pitanje.

Budući da model vidi prethodne poruke, razumije popratna pitanja. Na „Daj mi tri glavna savjeta.” nakon sažetka dokumenta odgovara savjetima iz tog dokumenta, a na „A stana?” nakon pitanja o vikendici odgovara o uređenju stana. Povijest se čuva u memoriji procesa i briše se pri ponovnom pokretanju servera.

## Zadatak 4: Kratki i detaljni odgovori

Na svako novo pitanje chatbot prvo odgovara u 1–2 rečenice. Ispod odgovora nudi detaljno objašnjenje, koje korisnik traži gumbom „Prikaži detaljno objašnjenje” ili porukom „da”. Poruka „ne” zatvara ponudu.

### Backend

`ANSWER_MODE_SETTINGS` definira dva načina:

| Način | Uputa modelu | `max_tokens` | Dijelova dokumenta |
|---|---|---|---|
| `short` | `SHORT_ANSWER_INSTRUCTION`: odgovori u 1–2 rečenice | 200 | 3 |
| `detailed` | `DETAILED_ANSWER_INSTRUCTION`: sve relevantne informacije, primjeri i objašnjenja | 2000 | 8 |

`PENDING_DETAIL_QUESTIONS` po sesiji pamti zadnje pitanje na koje je dan kratki odgovor. Detaljni odgovor uvijek se generira za to pitanje, a ne za samu poruku „da”. `classify_detail_reply` poruku pretvara u mala slova, uklanja interpunkciju i prepoznaje potvrdne odgovore (`da`, `može`, `naravno`, `svakako`...) i odrečne (`ne`, `ne hvala`, `nema potrebe`...).

Ruta `POST /chat` radi ovako:

| Zahtjev | Uvjet | Rezultat |
|---|---|---|
| `{"message": "<pitanje>"}` | | Kratki odgovor, pitanje se pamti kao „na čekanju”, `offer_detail: true` |
| `{"message": "da"}` | postoji pitanje na čekanju | Detaljni odgovor na to pitanje, `offer_detail: false` |
| `{"detail": true}` (gumb) | postoji pitanje na čekanju | Detaljni odgovor; u povijest se upisuje „Želim detaljno objašnjenje.” |
| `{"message": "ne"}` | postoji pitanje na čekanju | „U redu. Slobodno postavite novo pitanje.”, bez poziva API-ja |
| `{"message": "da"}` ili `"ne"` | nema pitanja na čekanju | Obrađuje se kao obično pitanje |
| `{"detail": true}` | nema pitanja na čekanju | HTTP 400 |

Pitanje na čekanju briše se tek nakon uspješnog detaljnog odgovora. Ako API vrati grešku, korisnik može ponovno kliknuti gumb ili napisati „da”.

Model vraća Markdown, a backend ga pretvara u HTML paketom `markdown`. Modeli često stave listu odmah ispod rečenice bez praznog retka, a Python-Markdown takvu listu prikaže kao običan tekst sa zvjezdicama. Funkcija `separate_lists_from_paragraphs` zato prije pretvorbe ubacuje prazan redak ispred prve stavke liste.

### Frontend

- Kad odgovor ima `offer_detail: true`, `appendDetailOffer` ispod kratkog odgovora dodaje pitanje i gumb „Prikaži detaljno objašnjenje”.
- Klik na gumb (`requestDetailedAnswer`) prikazuje korisničku poruku i šalje `{ detail: true }` na `/chat`.
- `closeDetailOffers` pri svakoj novoj poruci onemogućuje stare gumbe, jer se detaljno objašnjenje odnosi samo na zadnje pitanje.
- Dok se čeka odgovor, `showThinkingIndicator` prikazuje poruku „Razmišljam” s animiranim točkicama, a polje za unos i gumb „Pošalji” su onemogućeni da korisnik ne pošalje isto pitanje dvaput.
- Korisničke poruke i greške prikazuju se kao običan tekst (`textContent`). Samo HTML koji vrati backend umeće se kao HTML.

## Zadatak 5: Testiranje

### Unit testovi

Testovi koriste lažni API klijent, pa ne troše API pozive i rade bez ključa.

| Datoteka | Što provjerava |
|---|---|
| `test_conversation_memory.py` | da se povijest skraćuje na zadnjih 12 poruka i da se šalje modelu uz novo pitanje |
| `test_short_detailed_answers.py` | prepoznavanje „da”/„ne”, kratki odgovor s ponudom, detaljni odgovor na „da” i na gumb, „ne” bez poziva API-ja, „da” bez pitanja na čekanju, gumb bez pitanja na čekanju (400) |
| `test_document_search.py` | preskakanje praznih dijelova, preklapanje dijelova, zadani kontekst bez dokumenta, odabir najbližeg dijela |
| `test_reply_formatting.py` | da se liste ispod rečenice prikazuju kao HTML liste |

Pokretanje (16 testova):

```bash
cd backend
python -m unittest discover -s tests -t .
```

### Rezultati testiranja na stvarnim upitima

Test je proveden 26. 10. 2026. Učitan je dokument `uredjenje_interijera.txt` (vodič za uređenje malih prostora s primjerima vikendice i gradskog stana od 45 m²), a upiti su poslani redom u istoj sesiji. Odgovori je generirao Gemini (`gemini-3.5-flash-lite`, `LLM_PROVIDER=gemini`), jer Mistral ključ korišten pri razvoju nije bio valjan. Logika aplikacije ista je za oba pružatelja.

| # | Upit | Što se provjerava | Rezultat |
|---|---|---|---|
| 1 | Sažmi glavnu temu učitanog dokumenta. | odgovor iz dokumenta, kratki oblik | „Glavna tema dokumenta je uređenje malih stambenih prostora kako bi bili što funkcionalniji i ugodniji.” Dvije rečenice i ponuda detalja. ✅ |
| 2 | Daj mi tri glavna savjeta. | popratno pitanje se odnosi na dokument | Tri savjeta iz dokumenta: prirodno svjetlo i ogledala, svijetli neutralni tonovi, multifunkcionalni namještaj. ✅ |
| 3 | klik na „Prikaži detaljno objašnjenje” | detaljni odgovor na gumb | Razrada sva tri savjeta s podnaslovima i listama (zavjese, ogledala, krevet s ladicama, sklopivi stol, police do stropa) te primjerom stana od 45 m². ✅ |
| 4 | Imaš li primjer za uređenje interijera vikendice? | primjer iz dokumenta | Vikendica u planinama: drvo i kamen, kamin kao središte dnevnog boravka, vunene deke, tople boje, staklena stijena prema pogledu. ✅ |
| 5 | A stana? | pamćenje teme razgovora | Odgovor o gradskom stanu od 45 m²: otvoreni koncept, kuhinjski otok kao blagovaonski stol, biljke, zidne police. Chatbot je prepoznao da se i dalje govori o uređenju interijera. ✅ |
| 6 | da | detaljni odgovor na „da” | Detaljna razrada uređenja stana od 45 m² u pet cjelina (otvoreni koncept, kuhinjski otok, skandinavski stil, zidne police, biljke). ✅ |
| 7 | Koje boje preporučuješ za malu sobu? | novo pitanje nakon detaljnog odgovora | „Preporučujem svijetle i neutralne tonove poput bijele, bež ili svijetlosive...” Jedna rečenica i nova ponuda detalja. ✅ |
| 8 | ne | odbijanje detalja | „U redu. Slobodno postavite novo pitanje.” bez poziva API-ja. ✅ |

Kratki odgovori su u svim slučajevima imali jednu ili dvije rečenice, a detaljni su koristili sadržaj dokumenta. Prije ispravka iz Zadatka 4 liste u detaljnim odgovorima prikazivale su se kao tekst sa zvjezdicama; nakon ispravka prikazuju se kao prave liste.

## Paketi

| Paket | Namjena |
|---|---|
| `Flask` | web poslužitelj i rute `/`, `/chat`, `/upload` |
| `mistralai` | Mistral SDK za chat i embeddinge |
| `google-genai` | opcionalni Gemini pružatelj |
| `python-dotenv` | učitavanje ključa iz `.env` |
| `markdown` | pretvorba Markdown odgovora u HTML |
| `PyPDF2` | tekst iz PDF datoteka |
| `python-docx` | tekst iz DOCX datoteka |
| `numpy` | embeddingi kao vektori i izračun udaljenosti |

```bash
python -m pip install -r requirements.txt
```

Preporučeni Python je 3.12 ili 3.13, jer najnovije verzije možda još nisu podržane u svim paketima.

## Što ne dijeliti

U ZIP ili repozitorij ne idu `.env` sa stvarnim ključem, virtualno okruženje `.venv`, `__pycache__` ni mapa `backend/uploads` s učitanim dokumentima. Primatelj izrađuje vlastiti `.env` prema `.env.example` i ponovno učitava dokumente.
