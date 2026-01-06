# Hallo
import random
import re
from typing import Dict, List, Tuple

import gspread
import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials


# --- Konfiguration ---
SHEET_NAME = "Weinkarte, Speisekarte, Regeln"
SPEISEN_SPALTE = "Speisename"

INTENSITAETS_MAP = {
    "niedrig": 0, "Niedrig": 0, "NIEDRIG": 0,
    "mittel": 1, "Mittel": 1, "MITTEL": 1,
    "hoch": 2, "Hoch": 2, "HOCH": 2,
    "leicht": 0, "Leicht": 0,
    "leicht bis mittel": 1, "Leicht bis Mittel": 1, "Leicht bis mittel": 1,
    "mittel bis voll": 2, "Mittel bis Voll": 2, "Mittel bis voll": 2,
    "voll": 2, "Voll": 2,
    "kräftig": 2, "Kräftig": 2,
}
SUESSE_MAP = {
    "niedrig": 0, "Niedrig": 0, "NIEDRIG": 0,
    "mittel": 1, "Mittel": 1, "MITTEL": 1,
    "hoch": 2, "Hoch": 2, "HOCH": 2,
    "trocken": 0, "Trocken": 0, "TROCKEN": 0,
    "halbtrocken": 1, "Halbtrocken": 1,
    "feinherb": 1, "Feinherb": 1,
    "lieblich": 2, "Lieblich": 2,
    "süß": 2, "Süß": 2,
}

SPALTEN_ALTERNATIVEN = {
    "Farbe": ["Farbe", "Art", "Weinart", "Typ"],
    "Körper": ["Körper", "Koerper", "Body"],
    "Säure": ["Säure", "Saeure", "Acidity"],
    "Süße": ["Süße", "Suesse", "Sweetness"],
    "Tannin": ["Tannin", "Gerbstoff"],
    "Alkoholgehalt": ["Alkoholgehalt", "Alkohol", "Alcohol"],
    "Weinname": ["Weinname", "Name", "Wein"],
}

FISCH_KEYWORDS = [
    "fisch", "lachs", "garnelen", "garnele", "austern", "hamachi",
    "hummer", "seeteufel", "steinbutt", "kabeljau", "auster", "sea",
]
GEFLUEGEL_KEYWORDS = ["ente", "enten", "wachtel", "huhn", "hähn", "poularde"]
ROTES_FLEISCH_KEYWORDS = [
    "rind", "rinder", "kalb", "reh", "lamm", "striploin",
    "steak", "vieh", "beef", "ragout",
]
DESSERT_KEYWORDS = ["dessert", "tarte", "kuchen", "pie", "eis", "süß", "sweet"]
VEGETARISCH_KEYWORDS = ["salat", "kürbis", "kohlrabi", "spätzle", "gemüse", "veggie"]


# --- Helper & Caching ---
@st.cache_resource(show_spinner=False)
def get_gspread_client() -> gspread.Client:
    scopes = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/spreadsheets",
    ]
    creds_info = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
    return gspread.authorize(creds)


@st.cache_data(show_spinner=False, ttl=300)
def lade_daten() -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    client = get_gspread_client()
    sheet = client.open(SHEET_NAME)

    def worksheet_to_df(worksheet_name: str) -> pd.DataFrame:
        ws = sheet.worksheet(worksheet_name)
        all_values = ws.get_all_values()
        if not all_values:
            return pd.DataFrame()
        headers = all_values[0]
        data = all_values[1:]
        df = pd.DataFrame(data, columns=headers)
        df = df.dropna(how="all")
        df = df[~(df == "").all(axis=1)]
        return df

    weine_df = worksheet_to_df("Weinkarte")
    speisen_df = worksheet_to_df("Speisekarte")
    regeln_df = worksheet_to_df("Regeln")
    return weine_df, speisen_df, regeln_df


def klassifiziere_speiseart(name: str) -> str:
    lower = name.lower()
    if any(keyword in lower for keyword in DESSERT_KEYWORDS):
        return "dessert"
    if any(keyword in lower for keyword in FISCH_KEYWORDS):
        return "fisch"
    if any(keyword in lower for keyword in ROTES_FLEISCH_KEYWORDS):
        return "rotes_fleisch"
    if any(keyword in lower for keyword in GEFLUEGEL_KEYWORDS):
        return "gefluegel"
    if any(keyword in lower for keyword in VEGETARISCH_KEYWORDS):
        return "vegetarisch"
    return "unbekannt"


def wert_map(mapper: Dict[str, int], value: str) -> int:
    clean_value = str(value).strip().lower()
    for key, val in mapper.items():
        if key.lower() == clean_value:
            return val
    return 0


def get_column_value(row: pd.Series, column_name: str, default: str = "") -> str:
    possible_names = SPALTEN_ALTERNATIVEN.get(column_name, [column_name])
    for name in possible_names:
        if name in row.index:
            return str(row[name])
        for col in row.index:
            if col.lower() == name.lower():
                return str(row[col])
    return default


def parse_weinfarbe(art_value: str) -> str:
    lower = art_value.lower().strip()
    if "rot" in lower:
        return "rot"
    if "weiß" in lower or "weiss" in lower:
        return "weiß"
    if "rosé" in lower or "rose" in lower:
        return "rosé"
    if "schaum" in lower or "champagner" in lower or "sekt" in lower or "crémant" in lower:
        return "schaumwein"
    if "orange" in lower:
        return "orange"
    return lower


def parse_alkohol(alkohol_value: str) -> int:
    match = re.search(r"(\d+)[,.]?(\d*)", alkohol_value)
    if match:
        try:
            prozent = float(match.group(1) + "." + (match.group(2) or "0"))
            if prozent < 12:
                return 0
            elif prozent < 14:
                return 1
            else:
                return 2
        except ValueError:
            pass
    return wert_map(INTENSITAETS_MAP, alkohol_value)


def baue_regel_lookup(regeln_df: pd.DataFrame) -> Dict[str, Dict[str, str]]:
    lookup: Dict[str, Dict[str, str]] = {}
    for _, row in regeln_df.iterrows():
        if not row.get("Kategorie"):
            continue
        lookup[row["Kategorie"]] = row.to_dict()
    return lookup


def generiere_sommelier_text(
    speise_name: str,
    speise_art: str,
    wein_name: str,
    wein_farbe: str,
    positive_kategorien: List[str],
) -> str:
    farbe_text = {
        "rot": "Rotwein",
        "weiß": "Weißwein",
        "rosé": "Rosé",
        "schaumwein": "Schaumwein",
        "orange": "Orange Wine",
    }.get(wein_farbe, "Wein")

    art_text = {
        "fisch": "Fischgericht",
        "gefluegel": "Geflügelgericht",
        "rotes_fleisch": "Fleischgericht",
        "vegetarisch": "vegetarische Gericht",
        "dessert": "Dessert",
    }.get(speise_art, "Gericht")

    saetze = []

    if "Weinfarbe & Speiseart" in positive_kategorien:
        if speise_art in {"fisch", "gefluegel", "vegetarisch"}:
            saetze.append(f"Dieser {farbe_text} ist ein idealer Begleiter für Ihr {art_text}.")
        elif speise_art == "rotes_fleisch":
            saetze.append(f"Die Struktur dieses {farbe_text}s harmoniert ausgezeichnet mit der Intensität des Fleisches.")
        elif speise_art == "dessert":
            saetze.append(f"Dieser {farbe_text} rundet Ihr {art_text} wunderbar ab.")
        else:
            saetze.append(f"Dieser {farbe_text} ergänzt Ihr Gericht auf elegante Weise.")

    if "Intensitätsabgleich (Gewicht)" in positive_kategorien:
        if not saetze:
            saetze.append("Die Fülle des Weins steht im perfekten Gleichgewicht mit der Aromatik Ihrer Speise.")
        else:
            saetze.append("Dabei stehen Wein und Speise in perfekter Balance zueinander.")

    if "Säure-Balance" in positive_kategorien or "Säure-Fett" in positive_kategorien:
        saetze.append("Die lebendige Säure sorgt für Frische am Gaumen und hebt die Aromen hervor.")

    if "Süße-Balance" in positive_kategorien:
        if speise_art == "dessert":
            saetze.append("Die feine Süße des Weins greift die Dessertnoten harmonisch auf.")
        else:
            saetze.append("Die Geschmacksprofile von Wein und Speise ergänzen sich harmonisch.")

    if "Tannin vs Fett" in positive_kategorien:
        saetze.append("Die samtigen Tannine umschmeicheln die reichhaltigen Aromen des Gerichts.")

    if "Textur" in positive_kategorien:
        saetze.append("Die Textur des Weins setzt einen spannenden Kontrast zur Speise.")

    if "Würze/Schärfe" in positive_kategorien:
        saetze.append("Der Wein mildert die Würze und schafft einen angenehmen Ausgleich.")

    if "Salz" in positive_kategorien:
        saetze.append("Die salzigen Nuancen des Gerichts werden vom Wein elegant aufgefangen.")

    if not saetze:
        saetze.append(f"Dieser {farbe_text} passt hervorragend zu Ihrer Wahl und verspricht ein genussvolles Zusammenspiel der Aromen.")

    return " ".join(saetze[:3])


def berechne_match(
    speise: pd.Series,
    wein: pd.Series,
    regel_lookup: Dict[str, Dict[str, str]],
) -> Dict[str, object]:
    score = 0
    details: List[Dict[str, str]] = []

    speise_art = klassifiziere_speiseart(speise[SPEISEN_SPALTE])
    speise_fett = wert_map(INTENSITAETS_MAP, get_column_value(speise, "Fettgehalt", "mittel"))
    speise_wuerze = wert_map(INTENSITAETS_MAP, get_column_value(speise, "Würze", "mittel"))
    speise_intensitaet = max(speise_fett, speise_wuerze)

    wein_koerper = wert_map(INTENSITAETS_MAP, get_column_value(wein, "Körper", "mittel"))
    wein_saeure = wert_map(INTENSITAETS_MAP, get_column_value(wein, "Säure", "mittel"))
    wein_suesse = wert_map(SUESSE_MAP, get_column_value(wein, "Süße", "niedrig"))
    wein_tannin = wert_map(INTENSITAETS_MAP, get_column_value(wein, "Tannin", "niedrig"))
    wein_farbe = parse_weinfarbe(get_column_value(wein, "Farbe", ""))
    wein_alkohol = parse_alkohol(get_column_value(wein, "Alkoholgehalt", "mittel"))

    aromaprofil = get_column_value(speise, "Aromaprofil", "").lower()
    speise_saeure = wert_map(INTENSITAETS_MAP, get_column_value(speise, "Säure", "mittel"))
    speise_suesse = wert_map(SUESSE_MAP, get_column_value(speise, "Süße", "niedrig"))

    def fuege_regel_hinzu(kategorie: str, delta: int, erklaerung: str) -> None:
        nonlocal score
        if delta == 0:
            return
        score += delta
        info = regel_lookup.get(kategorie, {})
        details.append({
            "Kategorie": kategorie,
            "Punkte": f"{delta:+d}",
            "Erklärung": erklaerung,
            "Regelbeschreibung": info.get("Regelbeschreibung", ""),
            "Quelle": info.get("Quelle", ""),
        })

    diff_intensitaet = abs(speise_intensitaet - wein_koerper)
    if diff_intensitaet == 0:
        fuege_regel_hinzu("Intensitätsabgleich (Gewicht)", 2, "Körper und Intensität ausbalanciert.")
    elif diff_intensitaet >= 2:
        fuege_regel_hinzu("Intensitätsabgleich (Gewicht)", -2, "Gewicht driftet stark auseinander.")

    if speise_art in {"fisch", "gefluegel", "vegetarisch"}:
        if wein_farbe in {"weiß", "schaumwein"}:
            fuege_regel_hinzu("Weinfarbe & Speiseart", 2, "Helles Gericht mit hellem Wein.")
        elif wein_farbe == "rot" and wein_tannin >= 1:
            fuege_regel_hinzu("Weinfarbe & Speiseart", -2, "Tanninreicher Rotwein überlagert.")
    elif speise_art == "rotes_fleisch":
        if wein_farbe == "rot":
            fuege_regel_hinzu("Weinfarbe & Speiseart", 2, "Kräftiges Fleisch verlangt Rotwein.")
        elif wein_farbe in {"weiß", "schaumwein"}:
            fuege_regel_hinzu("Weinfarbe & Speiseart", -2, "Zu wenig Struktur für rotes Fleisch.")

    if wein_saeure >= speise_saeure:
        fuege_regel_hinzu("Säure-Balance", 2, "Wein hat genug Säure.")
    else:
        fuege_regel_hinzu("Säure-Balance", -2, "Säure des Weins reicht nicht.")

    if speise_fett >= 2:
        if wein_saeure >= 2:
            fuege_regel_hinzu("Säure-Fett", 2, "Hohe Säure balanciert Fett.")
        elif wein_saeure == 0:
            fuege_regel_hinzu("Säure-Fett", -2, "Fettige Speise, säurearmer Wein.")

    if speise_art == "rotes_fleisch" or speise_fett >= 2:
        if wein_tannin >= 2:
            fuege_regel_hinzu("Tannin vs Fett", 2, "Tannine schneiden durch Fett.")

    if speise_art == "fisch" and wein_tannin >= 1:
        fuege_regel_hinzu("Tannin vs Fisch", -2, "Tannin macht Fisch metallisch.")

    if speise_suesse >= 2:
        if wein_suesse >= speise_suesse:
            fuege_regel_hinzu("Süße-Balance", 2, "Genug Restsüße für süße Speise.")
        else:
            fuege_regel_hinzu("Süße-Balance", -2, "Süße Speise, trockener Wein.")
    elif speise_suesse == 0 and wein_suesse == 0:
        fuege_regel_hinzu("Süße-Balance", 1, "Trocken harmoniert.")

    if "salzig" in aromaprofil and wein_tannin >= 1:
        fuege_regel_hinzu("Salz", 2, "Salz puffert Tannin.")

    if "umami" in aromaprofil:
        if wein_tannin >= 2:
            fuege_regel_hinzu("Umami", -2, "Umami verstärkt Tannin.")
        elif wein_tannin == 0:
            fuege_regel_hinzu("Umami", 1, "Sanftes Tannin passt zu Umami.")

    if speise_wuerze >= 2 or "scharf" in aromaprofil:
        if wein_suesse >= 1:
            fuege_regel_hinzu("Würze/Schärfe", 2, "Restsüße mildert Schärfe.")
        if wein_alkohol >= 2:
            fuege_regel_hinzu("Würze/Schärfe", -1, "Alkohol verstärkt Schärfe.")

    if "herb" in aromaprofil or "bitter" in aromaprofil:
        if wein_tannin >= 2:
            fuege_regel_hinzu("Bitterkeit", -2, "Bitter plus Tannin wirkt hart.")
        elif wein_tannin == 0:
            fuege_regel_hinzu("Bitterkeit", 1, "Feines Tannin vermeidet Bitterkeit.")

    if "cremig" in aromaprofil or "buttrig" in aromaprofil:
        if wein_farbe == "schaumwein" or wein_saeure >= 2:
            fuege_regel_hinzu("Textur", 1, "Straffe Struktur setzt Cremigkeit in Szene.")

    if wein_farbe == "schaumwein" and speise_art in {"fisch", "vegetarisch"}:
        fuege_regel_hinzu("Temperatur", 1, "Gekühlter Schaumwein passt zu leichter Speise.")

    return {
        "weinname": get_column_value(wein, "Weinname", "Unbekannt"),
        "punkte": score,
        "gründe": details,
    }


def berechne_top_matches(
    speisen_df: pd.DataFrame,
    weine_df: pd.DataFrame,
    regeln_df: pd.DataFrame,
    speise_name: str,
) -> Tuple[List[Dict[str, object]], str]:
    if speise_name not in speisen_df[SPEISEN_SPALTE].values:
        raise ValueError(f"Speise '{speise_name}' nicht gefunden.")

    speise = speisen_df[speisen_df[SPEISEN_SPALTE] == speise_name].iloc[0]
    speise_art = klassifiziere_speiseart(speise_name)
    regel_lookup = baue_regel_lookup(regeln_df)

    matches: List[Dict[str, object]] = []
    for idx, wein in weine_df.iterrows():
        result = berechne_match(speise, wein, regel_lookup)
        art_raw = get_column_value(wein, "Farbe", "")
        wein_farbe = parse_weinfarbe(art_raw)

        positive_kategorien = [
            g["Kategorie"] for g in result["gründe"]
            if g["Punkte"].startswith("+")
        ]

        result["beschreibung"] = generiere_sommelier_text(
            speise_name=speise_name,
            speise_art=speise_art,
            wein_name=result["weinname"],
            wein_farbe=wein_farbe,
            positive_kategorien=positive_kategorien,
        )
        matches.append(result)

    random.shuffle(matches)
    matches.sort(key=lambda item: item["punkte"], reverse=True)
    return matches[:3], speise_art


# --- Streamlit UI ---
st.set_page_config(
    page_title="Sommelier",
    page_icon="🍷",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;500;600&family=Playfair+Display:wght@400;500;600;700&display=swap');

    .stApp {
        background: linear-gradient(180deg, #1C080C 0%, #0D0506 50%, #2D0C12 100%);
    }

    #MainMenu, footer, header {visibility: hidden;}
    .stDeployButton {display: none;}

    h1, h2, h3 {
        font-family: 'Playfair Display', serif !important;
    }
    p, span, div, label, .stMarkdown {
        font-family: 'Cormorant Garamond', serif !important;
    }

    .header {
        text-align: center;
        padding: 2rem 0 1.5rem;
    }
    .header-icon {
        width: 70px;
        height: 70px;
        margin: 0 auto 1rem;
        background: linear-gradient(135deg, #D4AF37 0%, #B8962E 100%);
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        box-shadow: 0 4px 20px rgba(212, 175, 55, 0.3);
    }
    .header-icon svg {
        width: 35px;
        height: 35px;
        fill: #0D0506;
    }
    .header-title {
        font-family: 'Playfair Display', serif !important;
        font-size: 2.2rem;
        font-weight: 600;
        letter-spacing: 5px;
        color: #F5E6D3;
        margin: 0;
    }
    .header-subtitle {
        font-family: 'Cormorant Garamond', serif !important;
        font-size: 1rem;
        color: #D4AF37;
        letter-spacing: 3px;
        margin-top: 0.5rem;
    }

    .stTextInput > div > div > input {
        background: rgba(13, 5, 6, 0.8) !important;
        border: 1px solid rgba(212, 175, 55, 0.3) !important;
        border-radius: 12px !important;
        padding: 0.8rem 1rem !important;
        color: #F5E6D3 !important;
        font-family: 'Cormorant Garamond', serif !important;
        font-size: 1.1rem !important;
    }
    .stTextInput > div > div > input::placeholder {
        color: rgba(245, 230, 211, 0.5) !important;
    }
    .stTextInput > div > div > input:focus {
        border-color: #D4AF37 !important;
        box-shadow: 0 0 0 2px rgba(212, 175, 55, 0.2) !important;
    }
    .stTextInput > label {
        color: #D4AF37 !important;
        font-size: 0.9rem !important;
        letter-spacing: 1px !important;
    }

    .stButton > button {
        background: linear-gradient(135deg, #D4AF37 0%, #B8962E 100%) !important;
        color: #0D0506 !important;
        border: none !important;
        border-radius: 12px !important;
        padding: 0.7rem 2rem !important;
        font-family: 'Cormorant Garamond', serif !important;
        font-size: 1.1rem !important;
        font-weight: 600 !important;
        letter-spacing: 1px !important;
        width: 100% !important;
    }
    .stButton > button:hover {
        box-shadow: 0 4px 16px rgba(212, 175, 55, 0.3);
    }

    .result-title {
        font-family: 'Playfair Display', serif !important;
        font-size: 1.4rem;
        color: #D4AF37;
        text-align: center;
        margin: 2rem 0 0.5rem;
        letter-spacing: 1px;
    }
    .result-speise {
        font-family: 'Cormorant Garamond', serif !important;
        font-size: 1rem;
        color: rgba(245, 230, 211, 0.7);
        text-align: center;
        margin-bottom: 1.5rem;
    }

    .wine-card {
        background: linear-gradient(135deg, rgba(45, 12, 18, 0.9) 0%, rgba(28, 8, 12, 0.9) 100%);
        border: 1px solid #B8962E;
        border-radius: 14px;
        padding: 1.2rem;
        margin: 1rem 0;
    }
    .wine-card-header {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        margin-bottom: 0.5rem;
    }
    .wine-name {
        font-family: 'Playfair Display', serif !important;
        font-size: 1.15rem;
        font-weight: 600;
        color: #F5E6D3;
        margin: 0;
    }
    .wine-badge {
        background: linear-gradient(135deg, #D4AF37 0%, #B8962E 100%);
        color: #0D0506;
        font-size: 0.75rem;
        font-weight: 700;
        padding: 0.25rem 0.6rem;
        border-radius: 8px;
    }
    .wine-description {
        font-size: 1rem;
        color: rgba(245, 230, 211, 0.85);
        line-height: 1.6;
        margin-top: 0.5rem;
    }

    .error-msg {
        background: rgba(114, 47, 55, 0.3);
        border: 1px solid #722F37;
        border-radius: 10px;
        padding: 1rem;
        color: #F5E6D3;
        text-align: center;
        margin-top: 1.5rem;
    }
</style>
""", unsafe_allow_html=True)

# Header
st.markdown("""
<div class="header">
    <div class="header-icon">
        <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
            <path d="M6 2h12v7c0 3.31-2.69 6-6 6s-6-2.69-6-6V2zm6 11c2.21 0 4-1.79 4-4V4H8v5c0 2.21 1.79 4 4 4zm-1 3.93V20H8v2h8v-2h-3v-3.07c3.39-.49 6-3.39 6-6.93V0H5v9c0 3.54 2.61 6.44 6 6.93z"/>
        </svg>
    </div>
    <h1 class="header-title">Ihr Weinberater</h1>
</div>
""", unsafe_allow_html=True)

# Daten laden
try:
    weine_df, speisen_df, regeln_df = lade_daten()
except Exception as exc:
    st.error(f"Daten konnten nicht geladen werden: {exc}")
    st.stop()

if speisen_df.empty or weine_df.empty:
    st.warning("Keine Daten gefunden.")
    st.stop()


# Hilfsfunktion
def finde_passende_speise(eingabe: str) -> List[str]:
    eingabe_lower = eingabe.lower().strip()
    return [s for s in speisen_df[SPEISEN_SPALTE].tolist() if eingabe_lower in s.lower()]


# Eingabebereich
gericht = st.text_input("Ihr Gericht")
ausschluss = st.text_input("Nicht gewünscht")
submitted = st.button("Wein empfehlen")

# Ergebnisanzeige
if submitted and gericht.strip():
    treffer = finde_passende_speise(gericht)

    if treffer:
        speise_name = treffer[0]

        try:
            top_matches, _ = berechne_top_matches(speisen_df, weine_df, regeln_df, speise_name)

            st.markdown('<p class="result-title">Weinempfehlung</p>', unsafe_allow_html=True)
            st.markdown(f'<p class="result-speise">für {speise_name}</p>', unsafe_allow_html=True)

            for match in top_matches:
                st.markdown(f"""
                <div class="wine-card">
                    <div class="wine-card-header">
                        <span class="wine-name">{match['weinname']}</span>
                        <span class="wine-badge">{match['punkte']} Pkt</span>
                    </div>
                    <div class="wine-description">{match['beschreibung']}</div>
                </div>
                """, unsafe_allow_html=True)

        except Exception:
            st.markdown('<div class="error-msg">Leider konnte keine Empfehlung erstellt werden.</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="error-msg">Gericht "{gericht}" wurde nicht gefunden. Bitte versuchen Sie es erneut.</div>', unsafe_allow_html=True)
