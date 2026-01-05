# CODEX BRANCH WRITE TEST
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

# Erweiterte Maps mit allen möglichen Schreibweisen
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

# Alternative Spaltennamen (Sheet-Name → Code-Name)
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
    "fisch",
    "lachs",
    "garnelen",
    "garnele",
    "austern",
    "hamachi",
    "hummer",
    "seeteufel",
    "steinbutt",
    "kabeljau",
    "garnele",
    "auster",
    "sea",
]
GEFLUEGEL_KEYWORDS = [
    "ente",
    "enten",
    "wachtel",
    "huhn",
    "hähn",
    "huhn",
    "poularde",
]
ROTES_FLEISCH_KEYWORDS = [
    "rind",
    "rinder",
    "kalb",
    "reh",
    "lamm",
    "striploin",
    "steak",
    "vieh",
    "beef",
    "ragout",
]
DESSERT_KEYWORDS = ["dessert", "tarte", "kuchen", "pie", "eis", "süß", "sweet"]
VEGETARISCH_KEYWORDS = [
    "salat",
    "kürbis",
    "kohlrabi",
    "spätzle",
    "gemüse",
    "veggie",
]


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
        """Lädt alle Daten aus einem Worksheet, auch bei leeren Zeilen."""
        ws = sheet.worksheet(worksheet_name)
        # get_all_values() ignoriert leere Zeilen nicht
        all_values = ws.get_all_values()
        if not all_values:
            return pd.DataFrame()
        headers = all_values[0]
        data = all_values[1:]
        df = pd.DataFrame(data, columns=headers)
        # Entferne komplett leere Zeilen
        df = df.dropna(how="all")
        # Entferne Zeilen wo alle Werte leer sind (als String)
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
    """Mappt einen Wert auf einen numerischen Score, case-insensitiv."""
    clean_value = str(value).strip().lower()
    # Direkte Suche in der Map (case-insensitiv)
    for key, val in mapper.items():
        if key.lower() == clean_value:
            return val
    return 0  # Default wenn nichts gefunden


def get_column_value(row: pd.Series, column_name: str, default: str = "") -> str:
    """Holt einen Spaltenwert mit alternativen Spaltennamen."""
    # Hole alle möglichen Spaltennamen für dieses Feld
    possible_names = SPALTEN_ALTERNATIVEN.get(column_name, [column_name])

    for name in possible_names:
        # Direkte Suche
        if name in row.index:
            return str(row[name])
        # Case-insensitive Suche
        for col in row.index:
            if col.lower() == name.lower():
                return str(row[col])
    return default


def parse_weinfarbe(art_value: str) -> str:
    """Konvertiert Weinart (z.B. 'Rotwein') zu Farbe (z.B. 'rot')."""
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
    # Fallback: Original zurückgeben
    return lower


def parse_alkohol(alkohol_value: str) -> int:
    """Konvertiert Alkohol-Prozent zu Intensität (0-2)."""
    # Versuche Prozent zu parsen (z.B. "12,5%" oder "13.5%")
    match = re.search(r"(\d+)[,.]?(\d*)", alkohol_value)
    if match:
        try:
            prozent = float(match.group(1) + "." + (match.group(2) or "0"))
            if prozent < 12:
                return 0  # niedrig
            elif prozent < 14:
                return 1  # mittel
            else:
                return 2  # hoch
        except ValueError:
            pass
    # Fallback zu Text-Mapping
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
    """Generiert einen natürlichen Sommelier-Text für ein Wein-Speise-Pairing."""

    # Weinfarbe in lesbaren Text
    farbe_text = {
        "rot": "Rotwein",
        "weiß": "Weißwein",
        "rosé": "Rosé",
        "schaumwein": "Schaumwein",
        "orange": "Orange Wine",
    }.get(wein_farbe, "Wein")

    # Speiseart in lesbaren Text
    art_text = {
        "fisch": "Fischgericht",
        "gefluegel": "Geflügelgericht",
        "rotes_fleisch": "Fleischgericht",
        "vegetarisch": "vegetarische Gericht",
        "dessert": "Dessert",
    }.get(speise_art, "Gericht")

    # Textbausteine basierend auf positiven Kategorien
    saetze = []

    # Hauptaussage zur Kombination
    if "Weinfarbe & Speiseart" in positive_kategorien:
        if speise_art in {"fisch", "gefluegel", "vegetarisch"}:
            saetze.append(f"Dieser {farbe_text} ist ein idealer Begleiter für Ihr {art_text}.")
        elif speise_art == "rotes_fleisch":
            saetze.append(f"Die Struktur dieses {farbe_text}s harmoniert ausgezeichnet mit der Intensität des Fleisches.")
        elif speise_art == "dessert":
            saetze.append(f"Dieser {farbe_text} rundet Ihr {art_text} wunderbar ab.")
        else:
            saetze.append(f"Dieser {farbe_text} ergänzt Ihr Gericht auf elegante Weise.")

    # Körper/Intensität
    if "Intensitätsabgleich (Gewicht)" in positive_kategorien:
        if not saetze:
            saetze.append(f"Die Fülle des Weins steht im perfekten Gleichgewicht mit der Aromatik Ihrer Speise.")
        else:
            saetze.append("Dabei stehen Wein und Speise in perfekter Balance zueinander.")

    # Säure
    if "Säure-Balance" in positive_kategorien or "Säure-Fett" in positive_kategorien:
        saetze.append("Die lebendige Säure sorgt für Frische am Gaumen und hebt die Aromen hervor.")

    # Süße
    if "Süße-Balance" in positive_kategorien:
        if speise_art == "dessert":
            saetze.append("Die feine Süße des Weins greift die Dessertnoten harmonisch auf.")
        else:
            saetze.append("Die Geschmacksprofile von Wein und Speise ergänzen sich harmonisch.")

    # Tannin
    if "Tannin vs Fett" in positive_kategorien:
        saetze.append("Die samtigen Tannine umschmeicheln die reichhaltigen Aromen des Gerichts.")

    # Textur
    if "Textur" in positive_kategorien:
        saetze.append("Die Textur des Weins setzt einen spannenden Kontrast zur Speise.")

    # Würze
    if "Würze/Schärfe" in positive_kategorien:
        saetze.append("Der Wein mildert die Würze und schafft einen angenehmen Ausgleich.")

    # Salz
    if "Salz" in positive_kategorien:
        saetze.append("Die salzigen Nuancen des Gerichts werden vom Wein elegant aufgefangen.")

    # Fallback wenn keine speziellen Kategorien
    if not saetze:
        saetze.append(f"Dieser {farbe_text} passt hervorragend zu Ihrer Wahl und verspricht ein genussvolles Zusammenspiel der Aromen.")

    # Maximal 2-3 Sätze für einen flüssigen Text
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
    # Weinfarbe: "Rotwein" → "rot", "Weißwein" → "weiß", etc.
    wein_farbe = parse_weinfarbe(get_column_value(wein, "Farbe", ""))
    # Alkohol: "12,5%" → 1 (mittel)
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
        details.append(
            {
                "Kategorie": kategorie,
                "Punkte": f"{delta:+d}",
                "Erklärung": erklaerung,
                "Regelbeschreibung": info.get("Regelbeschreibung", ""),
                "Quelle": info.get("Quelle", ""),
            }
        )

    # Intensitätsabgleich
    diff_intensitaet = abs(speise_intensitaet - wein_koerper)
    if diff_intensitaet == 0:
        fuege_regel_hinzu(
            "Intensitätsabgleich (Gewicht)",
            2,
            "Körper und Intensität von Speise und Wein sind ausbalanciert.",
        )
    elif diff_intensitaet >= 2:
        fuege_regel_hinzu(
            "Intensitätsabgleich (Gewicht)",
            -2,
            "Gewicht von Speise und Wein driftet stark auseinander.",
        )

    # Weinfarbe & Speiseart
    if speise_art in {"fisch", "gefluegel", "vegetarisch"}:
        if wein_farbe in {"weiß", "schaumwein"}:
            fuege_regel_hinzu(
                "Weinfarbe & Speiseart",
                2,
                "Helles Gericht mit hellem/Schaumwein kombiniert.",
            )
        elif wein_farbe == "rot" and wein_tannin >= 1:
            fuege_regel_hinzu(
                "Weinfarbe & Speiseart",
                -2,
                "Roter, tanninreicher Wein kann helle Speisen überlagern.",
            )
    elif speise_art == "rotes_fleisch":
        if wein_farbe == "rot":
            fuege_regel_hinzu(
                "Weinfarbe & Speiseart",
                2,
                "Kräftiges Fleisch verlangt nach Rotwein.",
            )
        elif wein_farbe in {"weiß", "schaumwein"}:
            fuege_regel_hinzu(
                "Weinfarbe & Speiseart",
                -2,
                "Helle Weine liefern zu wenig Struktur für rotes Fleisch.",
            )

    # Säure-Balance
    if wein_saeure >= speise_saeure:
        fuege_regel_hinzu(
            "Säure-Balance",
            2,
            "Wein hat gleiche oder höhere Säure als die Speise.",
        )
    else:
        fuege_regel_hinzu(
            "Säure-Balance",
            -2,
            "Säure des Weins reicht nicht an die Speise heran.",
        )

    # Säure-Fett
    if speise_fett >= 2:
        if wein_saeure >= 2:
            fuege_regel_hinzu(
                "Säure-Fett",
                2,
                "Hoher Fettgehalt wird durch hohe Säure balanciert.",
            )
        elif wein_saeure == 0:
            fuege_regel_hinzu(
                "Säure-Fett",
                -2,
                "Fettige Speise trifft auf säurearmen Wein.",
            )

    # Tannin vs Fett
    if speise_art == "rotes_fleisch" or speise_fett >= 2:
        if wein_tannin >= 2:
            fuege_regel_hinzu(
                "Tannin vs Fett",
                2,
                "Stramme Tannine schneiden durch Fett/Protein.",
            )

    # Tannin vs Fisch
    if speise_art == "fisch" and wein_tannin >= 1:
        fuege_regel_hinzu(
            "Tannin vs Fisch",
            -2,
            "Tanninreicher Rotwein macht Fisch metallisch.",
        )

    # Süße-Balance
    if speise_suesse >= 2:
        if wein_suesse >= speise_suesse:
            fuege_regel_hinzu(
                "Süße-Balance",
                2,
                "Süße Speise mit genügend Restsüße im Wein abgeholt.",
            )
        else:
            fuege_regel_hinzu(
                "Süße-Balance",
                -2,
                "Süße Speise lässt trockenen Wein flach wirken.",
            )
    elif speise_suesse == 0 and wein_suesse == 0:
        fuege_regel_hinzu(
            "Süße-Balance",
            1,
            "Trockene Speise und trockener Wein harmonieren.",
        )

    # Salz
    if "salzig" in aromaprofil:
        if wein_tannin >= 1:
            fuege_regel_hinzu(
                "Salz",
                2,
                "Salz puffert Tannin – passt gut zu strukturreichem Wein.",
            )

    # Umami
    if "umami" in aromaprofil:
        if wein_tannin >= 2:
            fuege_regel_hinzu(
                "Umami",
                -2,
                "Umami verstärkt Tannin – milderer Wein wäre besser.",
            )
        elif wein_tannin == 0:
            fuege_regel_hinzu(
                "Umami",
                1,
                "Feines Umami profitiert von sanftem Tanninprofil.",
            )

    # Würze/Schärfe
    if speise_wuerze >= 2 or "scharf" in aromaprofil:
        if wein_suesse >= 1:
            fuege_regel_hinzu(
                "Würze/Schärfe",
                2,
                "Restsüße mildert Schärfe der Speise.",
            )
        if wein_alkohol >= 2:
            fuege_regel_hinzu(
                "Würze/Schärfe",
                -1,
                "Hoher Alkohol kann Schärfe verstärken.",
            )

    # Bitterkeit
    if "herb" in aromaprofil or "bitter" in aromaprofil:
        if wein_tannin >= 2:
            fuege_regel_hinzu(
                "Bitterkeit",
                -2,
                "Bittere Komponenten plus Tannin können hart wirken.",
            )
        elif wein_tannin == 0:
            fuege_regel_hinzu(
                "Bitterkeit",
                1,
                "Feines Tannin vermeidet zusätzliche Bitterkeit.",
            )

    # Textur
    if "cremig" in aromaprofil or "buttrig" in aromaprofil:
        if wein_farbe == "schaumwein" or wein_saeure >= 2:
            fuege_regel_hinzu(
                "Textur",
                1,
                "Prickelnde/straffe Struktur setzt cremige Speise in Szene.",
            )

    # Temperatur (nur weiche Gewichtung)
    if wein_farbe == "schaumwein" and speise_art in {"fisch", "vegetarisch"}:
        fuege_regel_hinzu(
            "Temperatur",
            1,
            "Gekühlter Schaumwein hält leichte Speise frisch.",
        )

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
    """Berechnet die Top-Matches und gibt auch die Speiseart zurück."""
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

        # Positive Kategorien sammeln für Sommelier-Text
        positive_kategorien = [
            g["Kategorie"] for g in result["gründe"]
            if g["Punkte"].startswith("+")
        ]

        # Sommelier-Text generieren
        result["beschreibung"] = generiere_sommelier_text(
            speise_name=speise_name,
            speise_art=speise_art,
            wein_name=result["weinname"],
            wein_farbe=wein_farbe,
            positive_kategorien=positive_kategorien,
        )
        matches.append(result)

    # Zufällige Reihenfolge bei gleichem Score (Tiebreaker)
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

# === LUXURIÖSES WEINBAR CSS ===
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,500;0,600;1,400&family=Playfair+Display:wght@400;500;600;700&display=swap');

    /* Haupthintergrund */
    .stApp {
        background: linear-gradient(180deg, #1C080C 0%, #0D0506 50%, #2D0C12 100%);
    }

    /* Verstecke Streamlit Elemente */
    #MainMenu, footer, header {visibility: hidden;}
    .stDeployButton {display: none;}

    /* Custom Fonts */
    h1, h2, h3, .header-title {
        font-family: 'Playfair Display', serif !important;
    }
    p, span, div, label, .stMarkdown {
        font-family: 'Cormorant Garamond', serif !important;
    }

    /* Header */
    .sommelier-header {
        text-align: center;
        padding: 2rem 0;
    }
    .header-icon {
        width: 80px;
        height: 80px;
        margin: 0 auto 1rem;
        background: linear-gradient(135deg, #D4AF37 0%, #B8962E 100%);
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        box-shadow: 0 4px 20px rgba(212, 175, 55, 0.3);
    }
    .header-icon svg {
        width: 40px;
        height: 40px;
        fill: #0D0506;
    }
    .header-title {
        font-family: 'Playfair Display', serif !important;
        font-size: 2.5rem;
        font-weight: 600;
        letter-spacing: 6px;
        color: #F5E6D3;
        margin: 0;
    }
    .header-subtitle {
        font-family: 'Cormorant Garamond', serif !important;
        font-size: 0.9rem;
        color: #D4AF37;
        text-transform: uppercase;
        letter-spacing: 4px;
        margin-top: 0.5rem;
    }

    /* Tab Navigation */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        justify-content: center;
        background: transparent;
        padding: 0 1rem;
    }
    .stTabs [data-baseweb="tab"] {
        background: transparent;
        border: 1px solid #B8962E;
        border-radius: 24px;
        padding: 0.6rem 1.5rem;
        color: #D4AF37;
        font-family: 'Cormorant Garamond', serif !important;
        font-size: 0.9rem;
        text-transform: uppercase;
        letter-spacing: 2px;
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #D4AF37 0%, #B8962E 100%) !important;
        color: #0D0506 !important;
        border-color: transparent;
        font-weight: 600;
    }
    .stTabs [data-baseweb="tab-panel"] {
        padding-top: 1rem;
    }
    .stTabs [data-baseweb="tab-highlight"] {
        display: none;
    }
    .stTabs [data-baseweb="tab-border"] {
        display: none;
    }

    /* Chat Container */
    .chat-container {
        background: rgba(13, 5, 6, 0.6);
        backdrop-filter: blur(10px);
        border-radius: 20px;
        border: 1px solid rgba(212, 175, 55, 0.1);
        padding: 1.5rem;
        margin: 1rem 0;
        min-height: 300px;
    }

    /* Chat Messages */
    .message-bot {
        display: flex;
        flex-direction: column;
        align-items: flex-start;
        margin-bottom: 1rem;
    }
    .message-user {
        display: flex;
        flex-direction: column;
        align-items: flex-end;
        margin-bottom: 1rem;
    }
    .message-label {
        font-size: 0.7rem;
        color: #D4AF37;
        text-transform: uppercase;
        letter-spacing: 3px;
        margin-bottom: 0.4rem;
        font-weight: 500;
    }
    .bubble-bot {
        background: linear-gradient(135deg, #722F37 0%, #8B3A44 100%);
        border-radius: 16px 16px 16px 4px;
        padding: 1rem 1.2rem;
        color: #F5E6D3;
        max-width: 85%;
        font-size: 1rem;
        line-height: 1.6;
    }
    .bubble-user {
        background: linear-gradient(135deg, #D4AF37 0%, #B8962E 100%);
        border-radius: 16px 16px 4px 16px;
        padding: 1rem 1.2rem;
        color: #0D0506;
        max-width: 85%;
        font-size: 1rem;
        line-height: 1.6;
    }

    /* Wine Cards */
    .wine-card {
        background: linear-gradient(135deg, rgba(45, 12, 18, 0.9) 0%, rgba(28, 8, 12, 0.9) 100%);
        border: 1px solid #B8962E;
        border-radius: 16px;
        padding: 1.2rem;
        margin: 0.8rem 0;
        position: relative;
    }
    .wine-card-header {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        margin-bottom: 0.5rem;
    }
    .wine-name {
        font-family: 'Playfair Display', serif !important;
        font-size: 1.2rem;
        font-weight: 600;
        color: #F5E6D3;
        line-height: 1.3;
        margin: 0;
    }
    .wine-badge {
        background: linear-gradient(135deg, #D4AF37 0%, #B8962E 100%);
        color: #0D0506;
        font-size: 0.75rem;
        font-weight: 700;
        padding: 0.25rem 0.6rem;
        border-radius: 10px;
        white-space: nowrap;
    }
    .wine-description {
        font-size: 0.95rem;
        color: rgba(245, 230, 211, 0.8);
        line-height: 1.5;
        margin-top: 0.6rem;
    }

    /* Input Styling */
    .stTextInput > div > div > input {
        background: rgba(13, 5, 6, 0.8) !important;
        border: 1px solid rgba(212, 175, 55, 0.3) !important;
        border-radius: 24px !important;
        padding: 0.8rem 1.2rem !important;
        color: #F5E6D3 !important;
        font-family: 'Cormorant Garamond', serif !important;
    }
    .stTextInput > div > div > input::placeholder {
        color: rgba(245, 230, 211, 0.5) !important;
    }
    .stTextInput > div > div > input:focus {
        border-color: #D4AF37 !important;
        box-shadow: 0 0 0 2px rgba(212, 175, 55, 0.2) !important;
    }

    /* Select Box */
    .stSelectbox > div > div {
        background: rgba(13, 5, 6, 0.8) !important;
        border: 1px solid rgba(212, 175, 55, 0.3) !important;
        border-radius: 16px !important;
        color: #F5E6D3 !important;
    }

    /* Buttons */
    .stButton > button {
        background: linear-gradient(135deg, #D4AF37 0%, #B8962E 100%) !important;
        color: #0D0506 !important;
        border: none !important;
        border-radius: 24px !important;
        padding: 0.7rem 2rem !important;
        font-family: 'Cormorant Garamond', serif !important;
        font-size: 1rem !important;
        font-weight: 600 !important;
        text-transform: uppercase !important;
        letter-spacing: 2px !important;
        transition: all 0.3s ease !important;
    }
    .stButton > button:hover {
        transform: scale(1.02);
        box-shadow: 0 4px 16px rgba(212, 175, 55, 0.3);
    }

    /* Profile Bars */
    .taste-item {
        margin-bottom: 1rem;
    }
    .taste-label {
        display: flex;
        justify-content: space-between;
        font-size: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 2px;
        margin-bottom: 0.4rem;
        color: rgba(245, 230, 211, 0.7);
    }
    .taste-bar {
        height: 8px;
        background: rgba(114, 47, 55, 0.3);
        border-radius: 4px;
        overflow: hidden;
    }
    .taste-fill {
        height: 100%;
        background: linear-gradient(90deg, #722F37 0%, #D4AF37 100%);
        border-radius: 4px;
    }

    /* Preference Tags */
    .pref-tag {
        display: inline-block;
        background: rgba(114, 47, 55, 0.5);
        border: 1px solid #722F37;
        border-radius: 12px;
        padding: 0.4rem 0.8rem;
        font-size: 0.85rem;
        color: #F5E6D3;
        margin: 0.2rem;
    }

    /* Cellar Grid */
    .cellar-grid {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 12px;
        margin: 1rem 0;
    }
    .cellar-slot {
        aspect-ratio: 1;
        border-radius: 12px;
        display: flex;
        align-items: center;
        justify-content: center;
    }
    .cellar-filled {
        background: linear-gradient(135deg, #722F37 0%, #8B3A44 100%);
    }
    .cellar-empty {
        border: 2px dashed rgba(212, 175, 55, 0.3);
    }

    /* Quick Actions */
    .quick-chip {
        display: inline-block;
        background: rgba(114, 47, 55, 0.4);
        border: 1px solid rgba(212, 175, 55, 0.2);
        border-radius: 20px;
        padding: 0.5rem 1rem;
        font-size: 0.85rem;
        color: #F5E6D3;
        margin: 0.2rem;
        cursor: pointer;
    }

    /* Section Title */
    .section-title {
        font-family: 'Playfair Display', serif !important;
        font-size: 1.2rem;
        color: #D4AF37;
        margin-bottom: 1rem;
        letter-spacing: 1px;
    }

    /* Info Text */
    .info-text {
        color: rgba(245, 230, 211, 0.6);
        font-size: 0.9rem;
        text-align: center;
    }

    /* Labels */
    .stTextInput label, .stSelectbox label, .stTextArea label {
        color: #D4AF37 !important;
        font-size: 0.85rem !important;
        text-transform: uppercase !important;
        letter-spacing: 2px !important;
    }
</style>
""", unsafe_allow_html=True)

# === HEADER ===
st.markdown("""
<div class="sommelier-header">
    <div class="header-icon">
        <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
            <path d="M6 2h12v7c0 3.31-2.69 6-6 6s-6-2.69-6-6V2zm6 11c2.21 0 4-1.79 4-4V4H8v5c0 2.21 1.79 4 4 4zm-1 3.93V20H8v2h8v-2h-3v-3.07c3.39-.49 6-3.39 6-6.93V0H5v9c0 3.54 2.61 6.44 6 6.93z"/>
        </svg>
    </div>
    <h1 class="header-title">SOMMELIER</h1>
    <p class="header-subtitle">Ihr Weinberater</p>
</div>
""", unsafe_allow_html=True)

# === DATEN LADEN ===
try:
    weine_df, speisen_df, regeln_df = lade_daten()
except Exception as exc:
    st.error(f"Daten konnten nicht geladen werden: {exc}")
    st.stop()

if speisen_df.empty or weine_df.empty:
    st.warning("Keine Daten gefunden.")
    st.stop()


# === HELPER FUNCTIONS ===
def finde_passende_speise(eingabe: str) -> List[str]:
    eingabe_lower = eingabe.lower().strip()
    return [s for s in speisen_df[SPEISEN_SPALTE].tolist() if eingabe_lower in s.lower()]


def parse_ausschluesse(text: str) -> Dict[str, List[str]]:
    text_lower = text.lower()
    ausschluesse = {"farben": [], "suesse": [], "koerper": [], "saeure": []}
    if any(x in text_lower for x in ["kein rot", "keinen rot", "nicht rot"]):
        ausschluesse["farben"].append("rot")
    if any(x in text_lower for x in ["kein weiß", "keinen weiß", "nicht weiß"]):
        ausschluesse["farben"].append("weiß")
    if any(x in text_lower for x in ["nicht trocken", "zu trocken"]):
        ausschluesse["suesse"].append("trocken")
    if any(x in text_lower for x in ["nicht süß", "zu süß"]):
        ausschluesse["suesse"].append("süß")
    if any(x in text_lower for x in ["keine säure", "zu sauer"]):
        ausschluesse["saeure"].append("hoch")
    return ausschluesse


def filter_weine(df: pd.DataFrame, ausschluesse: Dict[str, List[str]]) -> pd.DataFrame:
    gefiltert = df.copy()
    for idx, wein in df.iterrows():
        wein_farbe = parse_weinfarbe(get_column_value(wein, "Farbe", ""))
        if wein_farbe in ausschluesse["farben"]:
            gefiltert = gefiltert.drop(idx)
            continue
        wein_suesse = wert_map(SUESSE_MAP, get_column_value(wein, "Süße", ""))
        if "trocken" in ausschluesse["suesse"] and wein_suesse == 0:
            gefiltert = gefiltert.drop(idx)
    return gefiltert


def render_wine_card(name: str, beschreibung: str, punkte: int = 0):
    badge_html = f'<span class="wine-badge">{punkte} Pkt</span>' if punkte else ''
    st.markdown(f"""
    <div class="wine-card">
        <div class="wine-card-header">
            <span class="wine-name">{name}</span>
            {badge_html}
        </div>
        <div class="wine-description">{beschreibung}</div>
    </div>
    """, unsafe_allow_html=True)


def render_bot_message(text: str):
    st.markdown(f"""
    <div class="message-bot">
        <span class="message-label">Sommelier</span>
        <div class="bubble-bot">{text}</div>
    </div>
    """, unsafe_allow_html=True)


def render_user_message(text: str):
    st.markdown(f"""
    <div class="message-user">
        <div class="bubble-user">{text}</div>
    </div>
    """, unsafe_allow_html=True)


# === TAB NAVIGATION ===
tab_chat, tab_profil, tab_keller = st.tabs(["CHAT", "PROFIL", "KELLER"])


# === CHAT TAB ===
with tab_chat:
    # Chat Container Start
    st.markdown('<div class="chat-container">', unsafe_allow_html=True)

    # Session State für Chat
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = [
            {"role": "bot", "content": "Guten Abend! Ich bin Ihr persönlicher Sommelier. Wie darf ich Ihnen heute behilflich sein?"}
        ]
    if "last_speise" not in st.session_state:
        st.session_state.last_speise = None

    # Nachrichten anzeigen
    for msg in st.session_state.chat_messages:
        if msg["role"] == "bot":
            render_bot_message(msg["content"])
            if "wines" in msg:
                for wine in msg["wines"]:
                    render_wine_card(wine["name"], wine["beschreibung"], wine.get("punkte", 0))
        else:
            render_user_message(msg["content"])

    st.markdown('</div>', unsafe_allow_html=True)

    # Input Bereich
    st.markdown("")

    col1, col2 = st.columns([3, 2])
    with col1:
        user_input = st.text_input("Ihr Gericht", placeholder="z.B. Rinderfilet, Lachs...", label_visibility="collapsed")
    with col2:
        speise_dropdown = st.selectbox("Oder wählen", ["Bitte wählen..."] + speisen_df[SPEISEN_SPALTE].tolist(), label_visibility="collapsed")

    praeferenzen = st.text_input("Was sollen wir vermeiden?", placeholder="Optional: kein Rotwein, nicht zu trocken...", label_visibility="collapsed")

    # Quick Actions
    st.markdown("""
    <div style="margin: 0.5rem 0;">
        <span class="quick-chip">Rotwein</span>
        <span class="quick-chip">Weisswein</span>
        <span class="quick-chip">Champagner</span>
        <span class="quick-chip">Zum Dessert</span>
    </div>
    """, unsafe_allow_html=True)

    if st.button("Empfehlung anfragen"):
        # Bestimme Speise
        speise_name = None
        if user_input.strip():
            treffer = finde_passende_speise(user_input)
            if treffer:
                speise_name = treffer[0]
        elif speise_dropdown != "Bitte wählen...":
            speise_name = speise_dropdown

        if speise_name:
            # User Nachricht hinzufügen
            st.session_state.chat_messages.append({
                "role": "user",
                "content": f"Ich suche einen Wein zu {speise_name}."
            })

            # Weine berechnen
            aktuelle_weine = weine_df
            if praeferenzen.strip():
                ausschluesse = parse_ausschluesse(praeferenzen)
                aktuelle_weine = filter_weine(weine_df, ausschluesse)

            try:
                top_matches, speise_art = berechne_top_matches(speisen_df, aktuelle_weine, regeln_df, speise_name)

                # Bot Antwort
                wines_data = [{"name": m["weinname"], "beschreibung": m["beschreibung"], "punkte": m["punkte"]} for m in top_matches]
                st.session_state.chat_messages.append({
                    "role": "bot",
                    "content": f"Ausgezeichnete Wahl! Für {speise_name} empfehle ich Ihnen einen kräftigen, tanninreichen Rotwein. Hier sind meine Empfehlungen:",
                    "wines": wines_data
                })
            except Exception as e:
                st.session_state.chat_messages.append({
                    "role": "bot",
                    "content": f"Entschuldigung, ich konnte keine passenden Weine finden."
                })

            st.rerun()


# === PROFIL TAB ===
with tab_profil:
    st.markdown('<p class="section-title">Geschmacksprofil</p>', unsafe_allow_html=True)

    taste_data = [
        ("Süße", 25),
        ("Säure", 70),
        ("Tannin", 60),
        ("Körper", 55),
        ("Alkohol", 45),
    ]

    for label, value in taste_data:
        st.markdown(f"""
        <div class="taste-item">
            <div class="taste-label">
                <span>{label}</span>
                <span>{value}%</span>
            </div>
            <div class="taste-bar">
                <div class="taste-fill" style="width: {value}%;"></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown('<p class="section-title" style="margin-top: 2rem;">Präferenzen</p>', unsafe_allow_html=True)
    st.markdown("""
    <div>
        <span class="pref-tag">Bordeaux</span>
        <span class="pref-tag">Burgund</span>
        <span class="pref-tag">Bio-Weine</span>
        <span class="pref-tag">unter 50€</span>
        <span class="pref-tag">Barrique</span>
    </div>
    """, unsafe_allow_html=True)


# === KELLER TAB ===
with tab_keller:
    st.markdown('<p class="section-title">Mein Weinkeller</p>', unsafe_allow_html=True)

    # 3x3 Grid
    cols = st.columns(3)
    slots = [True, True, False, True, False, True, False, True, False]

    for i, filled in enumerate(slots):
        with cols[i % 3]:
            if filled:
                st.markdown("""
                <div class="cellar-slot cellar-filled">
                    <svg width="32" height="32" viewBox="0 0 24 24" fill="#F5E6D3">
                        <path d="M6 2h12v7c0 3.31-2.69 6-6 6s-6-2.69-6-6V2z"/>
                    </svg>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown("""
                <div class="cellar-slot cellar-empty">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="#B8962E" opacity="0.5">
                        <path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/>
                    </svg>
                </div>
                """, unsafe_allow_html=True)

    filled_count = sum(slots)
    empty_count = len(slots) - filled_count
    st.markdown(f'<p class="info-text">{filled_count} Flaschen im Keller · {empty_count} Plätze frei</p>', unsafe_allow_html=True)
