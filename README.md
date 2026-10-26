# ai-bot-FIDIT

Arhitektonski chatbot: Flask aplikacija koja odgovara na pitanja o arhitekturi koristeći Mistral API i sadržaj iz `backend/architecture_context.md`. Korisnik može učitati PDF, DOCX ili TXT dokument; tekst dokumenta se izdvaja, dijeli na manje dijelove i pretražuje prema sličnosti s pitanjem.

## Struktura projekta

```text
ai-bot-FIDIT/
├── backend/
│   ├── server.py
│   ├── architecture_context.md
│   ├── scraping.py
│   ├── tests/
│   └── uploads/
├── frontend/
│   ├── index.html
│   ├── script.js
│   ├── style.css
│   └── assets/
├── docs/
│   └── dokumentacija.md
├── .env.example
└── requirements.txt
```

## Što je promijenjeno i zašto

### Zamjena Gemini API-ja s Mistralom

U `backend/server.py` uklonjen je Gemini SDK i dodan Mistral SDK (`mistralai`). Chat zahtjev koristi `client.chat.complete(...)` i poruke s ulogama `system`, `user` i `assistant`. Odgovor se čita iz `response.choices[0].message.content`, umjesto iz `response.text`. Zadani model je `mistral-small-latest`.

Mistral se također koristi za izradu embeddinga modelom `mistral-embed`. Embeddingi omogućuju pronalazak dijelova učitanog dokumenta koji su najrelevantniji za korisnikovo pitanje; NumPy računa udaljenost vektora i odabire najbliže dijelove. Time se izbjegava dodatna FAISS ovisnost koja nema odgovarajuće instalacijske pakete za sve kombinacije Pythona i Windowsa.

Za lokalno testiranje može se uključiti i Gemini (`LLM_PROVIDER=gemini` u `.env`); Mistral ostaje zadani pružatelj. Detalji su u `docs/dokumentacija.md`.

### Zaštita API ključa

Ključ se ne zapisuje u Python kod. `python-dotenv` učitava ključeve iz lokalne `.env` datoteke u korijenu projekta. Datoteka `.gitignore` isključuje `.env` kako se pravi ključ ne bi slučajno podijelio. Datoteka `.env.example` služi kao predložak i ne sadrži stvarni ključ.

### Upload dokumenata

Sučelje (`frontend/index.html`) prikazuje kontrolu za odabir datoteke, a `frontend/script.js` šalje datoteku na Flask rutu `/upload`. Backend prihvaća:

- PDF (`.pdf`), čitan pomoću PyPDF2
- Word Open XML (`.docx`), čitan pomoću python-docx
- obični tekst (`.txt`)

Stari Word format `.doc` nije podržan; spremite ga kao `.docx` prije učitavanja. Izdvojeni tekst dijeli se na preklapajuće dijelove. Za svako korisničko pitanje sustav pronalazi relevantne dijelove i dodaje ih u kontekst chat zahtjeva. Ako još nije učitan dokument, koristi se `backend/architecture_context.md`.

### Pamćenje razgovora

Backend pamti posljednjih 12 poruka po sesiji, pa chatbot razumije popratna pitanja poput „A stana?”.

### Kratki i detaljni odgovori

Chatbot na svako pitanje prvo odgovara u 1–2 rečenice. Ispod odgovora nudi detaljno objašnjenje, koje korisnik dobiva klikom na gumb „Prikaži detaljno objašnjenje” ili odgovorom „da” u chatu (odgovor „ne” zatvara ponudu). Detaljni odgovor koristi više dijelova učitanog dokumenta i uključuje primjere i objašnjenja.

## Preduvjeti

- Python 3.12 ili noviji
- Mistral API ključ (ili Gemini ključ za lokalno testiranje) i pristup internetu

## Instalacija i pokretanje

Naredbe se pokreću iz korijena projekta.

**Linux / macOS**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

**Windows PowerShell**

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Otvorite `.env` i upišite vlastiti ključ:

```env
MISTRAL_API_KEY=vas_stvarni_mistral_api_kljuc
MISTRAL_CHAT_MODEL=mistral-small-latest
```

Ako Mistral vrati grešku da model nije dostupan u vašoj pretplati, postavite `MISTRAL_CHAT_MODEL` na model koji vam je omogućen u Mistral konzoli.

Pokretanje backenda:

```bash
python backend/server.py
```

Dok backend radi, otvorite **http://localhost:5000** u pregledniku (backend sam poslužuje sučelje iz mape `frontend`). Ne otvarajte `frontend/index.html` dvoklikom: preglednici stranicama s adresom `file://` ograničavaju slanje zahtjeva na `localhost`, pa gumb „Pošalji” ne bi radio.

Učitani dokument i povijest razgovora čuvaju se samo u memoriji; nakon ponovnog pokretanja servera dokument treba ponovno učitati.

## Testovi

```bash
cd backend
python -m unittest discover -s tests -t .
```

## Napomena

Ovo je lokalni studentski projekt. Backend se pokreće s Flask debug načinom rada; nemojte ga izlagati javnom internetu u tom obliku. Chatbot nije zamjena za stručni ni pravni savjet.
