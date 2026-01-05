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
    page_title="AI Sommelier",
    page_icon="🍷",
    layout="centered",
)

# Custom CSS für schöneres Design
st.markdown("""
<style>
    .main-header {
        text-align: center;
        padding: 1rem 0 2rem 0;
    }
    .wine-card {
        background: linear-gradient(135deg, #f5f0eb 0%, #e8e0d8 100%);
        border-radius: 12px;
        padding: 1.5rem;
        margin: 1rem 0;
        border-left: 4px solid #722F37;
    }
    .wine-name {
        font-size: 1.3rem;
        font-weight: bold;
        color: #722F37;
        margin-bottom: 0.5rem;
    }
    .wine-description {
        font-size: 1rem;
        color: #4a4a4a;
        line-height: 1.6;
        margin-top: 0.8rem;
    }
    .stButton > button {
        background-color: #722F37;
        color: white;
        border-radius: 8px;
        padding: 0.5rem 2rem;
        font-size: 1.1rem;
        border: none;
        width: 100%;
    }
    .stButton > button:hover {
        background-color: #5a252c;
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-header">', unsafe_allow_html=True)
st.title("AI Sommelier")
st.markdown("*Ihr persönlicher Weinberater für das perfekte Pairing*")
st.markdown('</div>', unsafe_allow_html=True)

try:
    weine_df, speisen_df, regeln_df = lade_daten()
except Exception as exc:
    st.error(f"Daten konnten nicht geladen werden: {exc}")
    st.stop()

if speisen_df.empty or weine_df.empty:
    st.warning("Keine Daten gefunden.")
    st.stop()

# Sidebar mit Info
st.sidebar.markdown("### Über")
st.sidebar.markdown(f"**{len(weine_df)}** Weine verfügbar")
st.sidebar.markdown(f"**{len(speisen_df)}** Gerichte")

st.markdown("### Wählen Sie Ihr Gericht")
speise_name = st.selectbox(
    "Gericht",
    speisen_df[SPEISEN_SPALTE].tolist(),
    label_visibility="collapsed"
)

st.markdown("")  # Spacing

if st.button("Passende Weine finden"):
    with st.spinner("Analysiere Geschmacksprofile..."):
        try:
            top_matches, speise_art = berechne_top_matches(speisen_df, weine_df, regeln_df, speise_name)
        except Exception as exc:
            st.error(f"Fehler: {exc}")
        else:
            if not top_matches:
                st.info("Keine passenden Weine gefunden.")
            else:
                st.markdown("---")
                st.markdown(f"### Unsere Empfehlungen")

                for i, match in enumerate(top_matches, 1):
                    st.markdown(f"""
                    <div class="wine-card">
                        <div class="wine-name">{i}. {match['weinname']}</div>
                        <div class="wine-description">{match['beschreibung']}</div>
                    </div>
                    """, unsafe_allow_html=True)
