# Dokumentacija koda

Ova datoteka opisuje implementaciju u projektnim datotekama: što je dodano ili promijenjeno, zašto je to napravljeno, kako radi te koje Python pakete aplikacija koristi.

## Datoteke i njihova uloga

### `backend/server.py` — Flask backend

Backend je prilagođen za korištenje Mistral API-ja i upload dokumenata.

- Učitava konfiguraciju iz `.env` datoteke pomoću `python-dotenv`.
- Čita `MISTRAL_API_KEY` iz varijable okruženja. Ako ključ nedostaje, prekida pokretanje jasnom porukom umjesto da nastavi bez ispravne konfiguracije.
- Čita naziv chat modela iz `MISTRAL_CHAT_MODEL`, a zadano koristi `mistral-small-latest`, koji je manji od prethodnog `mistral-large-latest`. Ako taj model nije dostupan računu, postavi varijablu na model koji je omogućen u Mistral konzoli.
- Stvara Mistral klijenta iz `mistralai.client.sdk`, koji se koristi za chat odgovore i izradu embeddinga. U `requirements.txt` je navedena verzija SDK-a `3.3.0`, čija klasa klijenta u ovom projektu uvozi iz tog podmodula.
- Učitava `backend/architecture_context.md` kao zadani kontekst za razgovor.
- Ruta `POST /upload` prihvaća PDF, DOCX i TXT datoteke. Naziv datoteke se obrađuje funkcijom `secure_filename`, a sadržaj se izdvaja odgovarajućim čitačem.
- Tekst dokumenta dijeli se na dijelove od najviše 800 znakova s preklapanjem od 120 znakova. Preklapanje smanjuje mogućnost da se važan kontekst izgubi na granici između dijelova.
- Svaki dio pretvara se u embedding pomoću Mistral modela `mistral-embed`. Pri pitanju se izradi embedding upita, a NumPy izračuna udaljenost između upita i dijelova dokumenta. U kontekst se uključe do tri najbliža dijela.
- Ruta `POST /chat` šalje korisnikovu poruku i pronađeni kontekst modelu navedenom u `MISTRAL_CHAT_MODEL`. Markdown odgovor pretvara se u HTML i vraća frontendu kao JSON.
- Ako Mistral vrati HTTP 429 zbog ograničenja broja zahtjeva, backend vraća status 429 i jasnu poruku da korisnik pričeka pa pokuša ponovno.
- Ako dokument nije učitan, koristi se sadržaj `backend/architecture_context.md`.

Podrška za Word odnosi se na `.docx` (noviji Office Open XML format), ne na stari binarni `.doc` format.

Učitani tekst i embeddingi čuvaju se samo u memoriji procesa. Ponovno pokretanje backenda briše indeks; dokument je tada potrebno ponovno učitati.

### `frontend/index.html` — sučelje

Stranica sadrži chat, polje za poruku i odabir datoteke. Kontrola za upload ograničava ponuđene tipove na PDF, DOCX i TXT. Uključuje `frontend/style.css` za izgled i `frontend/script.js` za komunikaciju s backendom.

### `frontend/script.js` — komunikacija preglednika s backendom

- Prikazuje poruke u razgovoru.
- Šalje pitanja kao JSON na `http://localhost:5000/chat`.
- Šalje odabranu datoteku kao `multipart/form-data` na `http://localhost:5000/upload`.
- Prikazuje poruke o uspješnom uploadu ili grešci.

### `frontend/style.css` — izgled

Sadrži stilove chata i dodane kontrole za upload dokumenta.

### `backend/architecture_context.md` — zadani kontekst

Tekstualni kontekst koji backend učitava pri pokretanju i koristi kada korisnik nije učitao vlastiti dokument.

### `.env` i `.env.example` — konfiguracija API ključa

- `.env` je lokalna datoteka u koju vlasnik instalacije upisuje vlastiti ključ:

  ```env
  MISTRAL_API_KEY=ovdje_unesi_svoj_stvarni_kljuc
  ```

- `.env.example` je predložak bez stvarnog ključa.
- `.env.example` također navodi zadani chat model kroz `MISTRAL_CHAT_MODEL`.
- `.gitignore` isključuje `.env` iz Git praćenja kako se tajna ne bi slučajno podijelila.

Stvarni API ključ ne treba upisivati u Python kod niti slati u ZIP ili javni repozitorij.

### `requirements.txt` — Python ovisnosti

Popis Python paketa koje je potrebno instalirati da bi backend radio.

## Paketi

| Paket | Namjena |
|---|---|
| `Flask` | Flask web-poslužitelj i API rute `/chat` i `/upload`. |
| `mistralai` | Mistral SDK za chat odgovore i embeddinge. |
| `python-dotenv` | Učitava API ključ iz lokalne `.env` datoteke. |
| `markdown` | Pretvara Markdown odgovor modela u HTML. |
| `PyPDF2` | Izdvaja tekst iz PDF-datoteka. |
| `python-docx` | Izdvaja tekst iz DOCX-datoteka. |
| `numpy` | Čuva embeddinge kao vektore i izračunava udaljenosti za pretragu relevantnih dijelova. |

Paketi se instaliraju iz mape projekta:

```powershell
python -m pip install -r requirements.txt
```

Za razvoj se preporučuje Python 3.12 ili 3.13 jer vrlo nove verzije Pythona možda još nisu podržane od svih paketa.

## Tok obrade pitanja i dokumenta

1. Korisnik odabere PDF, DOCX ili TXT datoteku u `frontend/index.html`.
2. `frontend/script.js` pošalje datoteku backendu na `/upload`.
3. `backend/server.py` izdvoji tekst, podijeli ga na dijelove i zatraži embedding svakog dijela od Mistrala.
4. Korisnik pošalje pitanje. Backend izradi embedding pitanja jačinom Mistrala i pomoću NumPy-ja pronađe najbliže dijelove dokumenta.
5. Pronađeni dijelovi šalju se kao kontekst uz pitanje na Mistral chat endpoint. Odgovor se vrati pregledniku i prikaže u razgovoru.

## Opcionalni Gemini pružatelj (za lokalno testiranje)

Zadani pružatelj je Mistral (Zadatak 1). Za lokalno testiranje bez valjanog Mistral ključa može se u `.env` postaviti:

```env
LLM_PROVIDER=gemini
GEMINI_API_KEY=vas_gemini_kljuc
GEMINI_CHAT_MODEL=gemini-3.5-flash-lite
```

Tada `backend/server.py` koristi paket `google-genai`: odgovori se generiraju funkcijom `complete_with_gemini` (sistemska poruka šalje se kao `system_instruction`, a uloga `assistant` preimenuje se u `model`), a embeddingi modelom `gemini-embedding-001`. Ostatak aplikacije (memorija, kratki/detaljni odgovori, upload) radi jednako. Nakon promjene `.env` backend treba potpuno ugasiti i ponovno pokrenuti.

## Kratki i detaljni odgovori (Zadatak 4)

Chatbot na svako novo pitanje prvo daje **kratki odgovor (1–2 rečenice)**, a korisnik zatim može zatražiti **detaljno objašnjenje** klikom na gumb ili odgovorom „da”/„ne” u chatu.

### Backend (`backend/server.py`)

- **Načini odgovora.** `ANSWER_MODE_SETTINGS` definira dva načina, `short` i `detailed`. Svaki ima vlastitu uputu modelu (`SHORT_ANSWER_INSTRUCTION`, `DETAILED_ANSWER_INSTRUCTION`), ograničenje duljine (`max_tokens`: 200 za kratki, 2000 za detaljni) i broj dijelova dokumenta koji se šalju kao kontekst (3 za kratki, 8 za detaljni). Detaljni odgovor tako dobiva više sadržaja iz dokumenta i može uključiti sve relevantne informacije, primjere i objašnjenja.
- **`build_chat_messages(user_message, session_id, answer_mode)`** dodaje uputu odabranog načina u sistemsku poruku i dohvaća odgovarajući broj relevantnih dijelova dokumenta.
- **`generate_reply(question, session_id, answer_mode)`** šalje zahtjev Mistralu s postavkama odabranog načina.
- **`PENDING_DETAIL_QUESTIONS`** pamti, po sesiji, posljednje pitanje na koje je dan kratki odgovor. Detaljno objašnjenje uvijek se generira za to pitanje, a ne za samu poruku „da”.
- **`classify_detail_reply(message)`** normalizira poruku (mala slova, bez interpunkcije) i prepoznaje potvrdne (`da`, `može`, `naravno`, …) i odrečne (`ne`, `ne hvala`, …) odgovore.
- **`remember_exchange(...)`** sprema par korisnik/asistent u povijest razgovora, tako da i kratki i detaljni odgovori ostaju dostupni za popratna pitanja (Zadatak 3).

Tok rute `POST /chat`:

| Ulaz | Uvjet | Rezultat |
|---|---|---|
| `{"message": "<pitanje>"}` | — | Kratki odgovor, pitanje se sprema kao „na čekanju”, `offer_detail: true` |
| `{"message": "da"}` | postoji pitanje na čekanju | Detaljni odgovor na to pitanje, `offer_detail: false` |
| `{"detail": true}` (klik na gumb) | postoji pitanje na čekanju | Detaljni odgovor, u povijest se zapisuje „Želim detaljno objašnjenje.” |
| `{"message": "ne"}` | postoji pitanje na čekanju | Poruka „U redu. Slobodno postavite novo pitanje.” bez poziva API-ja |
| `{"message": "da"}` / `{"message": "ne"}` | nema pitanja na čekanju | Obrađuje se kao obično pitanje |
| `{"detail": true}` | nema pitanja na čekanju | HTTP 400 |

Pitanje na čekanju briše se tek nakon uspješnog detaljnog odgovora, pa korisnik može ponoviti zahtjev ako Mistral API vrati grešku.

### Frontend (`frontend/script.js`, `frontend/style.css`)

- Odgovor backenda sadrži polje `offer_detail`. Kada je `true`, `appendDetailOffer` ispod kratkog odgovora dodaje tekst „Želite li detaljnije objašnjenje? …” i gumb **„Prikaži detaljno objašnjenje”**.
- Klik na gumb (`requestDetailedAnswer`) prikazuje korisničku poruku i šalje `{ detail: true }` na `/chat`.
- Pri slanju svake nove poruke ili klika `closeDetailOffers` onemogućuje sve postojeće gumbe, jer se detaljno objašnjenje uvijek odnosi samo na posljednje pitanje.
- Zajednička funkcija `postChatRequest` šalje zahtjev, prikazuje odgovor i obrađuje greške za obične poruke i za klik na gumb.
- Stilovi `.detail-offer` i `.detail-btn` u `frontend/style.css` oblikuju ponudu i gumb unutar poruke chatbota.

### Testovi

`backend/tests/test_short_detailed_answers.py` (uz lažni Mistral klijent, bez stvarnih API poziva) provjerava:

- prepoznavanje odgovora „da”/„ne”,
- da novo pitanje dobiva kratki odgovor (uputa i `max_tokens` za kratki način) i ponudu detalja,
- da „da” i klik na gumb vraćaju detaljni odgovor na pitanje na čekanju,
- da „ne” zatvara ponudu bez poziva API-ja,
- da „da” bez pitanja na čekanju ide kao obično pitanje, a klik bez pitanja vraća 400.

Pokretanje:

```powershell
cd backend
python -m unittest discover -s tests -t .
```

## Datoteke koje ne treba dijeliti kao dio ZIP-a

Ne uključujte `.env` sa stvarnim API ključem, virtualno okruženje `.venv`, Python cache (`__pycache__`) ni mapu `uploads` s privatnim dokumentima. U ZIP uključite `.env.example`, `requirements.txt` i sve potrebne izvorne datoteke i resurse. Primatelj treba izraditi svoj `.env`, unijeti vlastiti Mistral ključ i ponovno učitati dokumente.
