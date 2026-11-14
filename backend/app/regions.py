"""Where agents should look, per country. Users anywhere can override with
preferred_domains / site_region in their profile (PATCH /api/v1/me/preferences).
Unknown countries still work: Exa gets the user's country as user_location and
the city in the query, with no domain restriction."""

GROCERY = {
    "FI": {"s-kaupat.fi": "S-Group (Prisma/Alepa/S-market)", "k-ruoka.fi": "K-Group (K-Citymarket/K-Market)", "lidl.fi": "Lidl", "foodie.fi": "Foodie"},
    "SE": {"ica.se": "ICA", "coop.se": "Coop", "willys.se": "Willys", "lidl.se": "Lidl"},
    "EE": {"selver.ee": "Selver", "rimi.ee": "Rimi", "prismamarket.ee": "Prisma"},
    "DE": {"rewe.de": "REWE", "lidl.de": "Lidl", "edeka.de": "EDEKA", "kaufland.de": "Kaufland"},
    "GB": {"tesco.com": "Tesco", "sainsburys.co.uk": "Sainsbury's", "asda.com": "Asda", "ocado.com": "Ocado"},
    "US": {"walmart.com": "Walmart", "target.com": "Target", "kroger.com": "Kroger", "instacart.com": "Instacart"},
    "NL": {"ah.nl": "Albert Heijn", "jumbo.com": "Jumbo", "lidl.nl": "Lidl"},
    "FR": {"carrefour.fr": "Carrefour", "auchan.fr": "Auchan", "lidl.fr": "Lidl"},
    "CN": {"jd.com": "JD", "freshhema.com": "Hema"},
    "JP": {"aeonnetshop.com": "AEON", "itoyokado.co.jp": "Ito-Yokado"},
    "AU": {"woolworths.com.au": "Woolworths", "coles.com.au": "Coles", "aldi.com.au": "ALDI"},
    "CA": {"loblaws.ca": "Loblaws", "walmart.ca": "Walmart", "metro.ca": "Metro"},
}

PHARMACY = {
    "FI": ["yliopistonapteekki.fi", "apteekki.fi", "apotek1.fi", "fimea.fi", "terveyskirjasto.fi"],
    "SE": ["apoteket.se", "apotea.se", "kronansapotek.se", "1177.se"],
    "DE": ["shop-apotheke.com", "docmorris.de", "gesund.bund.de"],
    "GB": ["boots.com", "lloydspharmacy.com", "nhs.uk"],
    "US": ["cvs.com", "walgreens.com", "medlineplus.gov"],
}

SOCIAL = ["reddit.com", "instagram.com", "x.com", "tiktok.com", "facebook.com", "threads.net"]

EVENTS = {
    "FI": ["myhelsinki.fi", "visitfinland.com", "tiketti.fi", "lippu.fi", "kulttuurikalenteri.fi"],
}

CURRENCY = {"FI": "EUR", "EE": "EUR", "DE": "EUR", "NL": "EUR", "FR": "EUR", "SE": "SEK", "GB": "GBP", "US": "USD",
            "CN": "CNY", "JP": "JPY", "AU": "AUD", "CA": "CAD"}


def country(user):
    return ((user or {}).get("site_region") or (user or {}).get("country") or "").upper()[:2] or None


def grocery_domains(user):
    pref = (user or {}).get("preferred_domains") or []
    if pref:
        return list(pref)
    return list(GROCERY.get(country(user) or "", {}).keys())


def retailer_name(domain, user=None):
    for table in GROCERY.values():
        if domain in table:
            return table[domain]
    return domain


def pharmacy_domains(user):
    return PHARMACY.get(country(user) or "", [])


def currency(user):
    return (user or {}).get("currency") or CURRENCY.get(country(user) or "", "EUR")


def city(user):
    return (user or {}).get("city") or ""
