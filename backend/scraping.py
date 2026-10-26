import requests
from bs4 import BeautifulSoup

new_urls = ["https://egradnja.hr/razgovor/kresimir-damjanovic-arhitektura-je-i-istrazivanje-ne-samo-gradnja-794",
            "https://egradnja.hr/intervju/kako-ce-3d-printanje-gradevina-utjecati-na-buducnost-odrzive-gradnje-218",
            "https://egradnja.hr/intervju/najzelenija-zgrada-je-ona-koja-vec-postoji-zasto-obnavljati-ne-rusiti-1028",
            "https://egradnja.hr/nekretnine/odrziva-adaptacija-stana-u-zagrebu-kako-obnoviti-prostor-uz-minimalan-ekoloski-otisak",
            "https://egradnja.hr/prostori/dgnb-alat-za-odrzivu-gradnju-u-sluzbi-zdravlja-1122"
            ]




def get_article_text(url):
    response = requests.get(url)
    if response.status_code!=200:
        print(f"ne mogu sohvatiti {url}")
        return ""
    
    soup = BeautifulSoup(response.text, "html.parser")
    content_div = soup.find("body")
    if not content_div:
        print(f"Nije pronađen sadržaj za {url}")
        return ""
    
    paragraphs = soup.find("body").find_all("p")
    article_text = "\n".join(p.get_text(strip=True) for p in paragraphs)
    return article_text

with open("architecture_context.md", "a", encoding="utf-8") as f:
    for url in new_urls:
        print(f"Scrapam: {url}")
        article = get_article_text(url)
        if article:
            f.write(f"\n\n--- Članak sa {url} ---\n\n")
            f.write(article)