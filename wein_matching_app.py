import random
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
    "voll": 2, "Voll": 2,
    "kräftig": 2, "Kräftig": 2,
}
SUESSE_MAP = {
    "niedrig": 0, "Niedrig": 0, "NIEDRIG": 0,
    "mittel": 1, "Mittel": 1, "MITTEL": 1,
    "hoch": 2, "Hoch": 2, "HOCH": 2,
    "trocken": 0, "Trocken": 0, "TROCKEN": 0,
    "halbtrocken": 1, "Halbtrocken": 1,
    "lieblich": 2, "Lieblich": 2,
    "süß": 2, "Süß": 2,
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
    """Holt einen Spaltenwert case-insensitiv."""
    # Direkte Suche
    if column_name in row.index:
        return str(row[column_name])
    # Case-insensitive Suche
    for col in row.index:
        if col.lower() == column_name.lower():
            return str(row[col])
    return default


def baue_regel_lookup(regeln_df: pd.DataFrame) -> Dict[str, Dict[str, str]]:
    lookup: Dict[str, Dict[str, str]] = {}
    for _, row in regeln_df.iterrows():
        if not row.get("Kategorie"):
            continue
        lookup[row["Kategorie"]] = row.to_dict()
    return lookup


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
    wein_farbe = get_column_value(wein, "Farbe", "").lower()
    wein_alkohol = wert_map(INTENSITAETS_MAP, get_column_value(wein, "Alkoholgehalt", "mittel"))

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
) -> Tuple[List[Dict[str, object]], Dict[int, int]]:
    if speise_name not in speisen_df[SPEISEN_SPALTE].values:
        raise ValueError(f"Speise '{speise_name}' nicht gefunden.")

    speise = speisen_df[speisen_df[SPEISEN_SPALTE] == speise_name].iloc[0]
    regel_lookup = baue_regel_lookup(regeln_df)

    matches: List[Dict[str, object]] = []
    for idx, wein in weine_df.iterrows():
        result = berechne_match(speise, wein, regel_lookup)
        result["zeile"] = idx + 2  # +2 weil Header und 0-basiert
        result["wein_daten"] = {
            "Farbe": get_column_value(wein, "Farbe", ""),
            "Körper": get_column_value(wein, "Körper", ""),
            "Säure": get_column_value(wein, "Säure", ""),
            "Tannin": get_column_value(wein, "Tannin", ""),
            "Süße": get_column_value(wein, "Süße", ""),
        }
        matches.append(result)

    # Zufällige Reihenfolge bei gleichem Score (Tiebreaker)
    random.shuffle(matches)
    matches.sort(key=lambda item: item["punkte"], reverse=True)

    # Debug: Score-Verteilung speichern
    score_counts: Dict[int, int] = {}
    for m in matches:
        s = m["punkte"]
        score_counts[s] = score_counts.get(s, 0) + 1

    return matches[:3], score_counts


# --- Streamlit UI ---
st.title("🍷 AI Sommelier Matching")
st.markdown("Wähle eine Speise und erhalte datenbasierte Weinempfehlungen.")

try:
    weine_df, speisen_df, regeln_df = lade_daten()
except Exception as exc:  # pragma: no cover - UI Feedback
    st.error(f"❌ Daten konnten nicht geladen werden: {exc}")
    st.stop()

if speisen_df.empty or weine_df.empty:
    st.warning("Keine Daten in den Google Sheets gefunden.")
    st.stop()

# Debug-Info: Anzahl geladener Datensätze
st.sidebar.markdown("### 📊 Geladene Daten")
st.sidebar.write(f"🍷 Weine: **{len(weine_df)}**")
st.sidebar.write(f"🍽️ Speisen: **{len(speisen_df)}**")
st.sidebar.write(f"📋 Regeln: **{len(regeln_df)}**")

speise_name = st.selectbox("Speise auswählen", speisen_df[SPEISEN_SPALTE].tolist())

if st.button("🔍 Weinempfehlungen anzeigen"):
    with st.spinner("Berechne Empfehlungen..."):
        try:
            top_matches, score_counts = berechne_top_matches(speisen_df, weine_df, regeln_df, speise_name)
        except Exception as exc:
            st.error(f"⚠️ Matching fehlgeschlagen: {exc}")
        else:
            if not top_matches:
                st.info("Für diese Speise wurden keine passenden Weine gefunden.")
            else:
                st.subheader(f"Top {len(top_matches)} Empfehlungen für: {speise_name}")
                for match in top_matches:
                    punkte = match["punkte"]
                    zeile = match.get("zeile", "?")
                    st.markdown(f"**{match['weinname']}** — {punkte} Punkte (Zeile {zeile} im Sheet)")
                    if match["gründe"]:
                        st.markdown("Gründe:")
                        for eintrag in match["gründe"]:
                            st.markdown(
                                f"- {eintrag['Kategorie']}: {eintrag['Erklärung']} ({eintrag['Punkte']})"
                            )
                    with st.expander(f"Debug: Bewertung für {match['weinname']}"):
                        st.markdown("**Wein-Attribute aus Sheet:**")
                        st.json(match.get("wein_daten", {}))
                        st.markdown("**Angewandte Regeln:**")
                        st.dataframe(pd.DataFrame(match["gründe"]))

                # Debug: Score-Verteilung anzeigen
                with st.expander("Debug: Score-Verteilung aller Weine"):
                    st.markdown("**Wie viele Weine haben welchen Score?**")
                    sorted_scores = sorted(score_counts.items(), key=lambda x: x[0], reverse=True)
                    for score, count in sorted_scores[:10]:  # Top 10 Score-Gruppen
                        st.write(f"Score {score}: **{count}** Weine")

    with st.expander("Debug: Speisendetails"):
        st.json(
            speisen_df[speisen_df[SPEISEN_SPALTE] == speise_name].iloc[0].to_dict()
        )

# Debug: Vergleich Wein aus Zeile 10 vs Zeile 500
with st.expander("🔬 Debug: Vergleich Wein Zeile 10 vs Zeile 500"):
    col1, col2 = st.columns(2)
    attr_cols = ["Weinname", "Farbe", "Körper", "Säure", "Tannin", "Süße", "Alkoholgehalt"]

    with col1:
        st.markdown("**Wein aus Zeile 10:**")
        if len(weine_df) > 9:
            wein_10 = weine_df.iloc[9]
            for col in attr_cols:
                val = wein_10.get(col, "FEHLT")
                st.write(f"{col}: `{val}`")

    with col2:
        st.markdown("**Wein aus Zeile 500:**")
        if len(weine_df) > 499:
            wein_500 = weine_df.iloc[499]
            for col in attr_cols:
                val = wein_500.get(col, "FEHLT")
                st.write(f"{col}: `{val}`")
        else:
            st.write("Weniger als 500 Weine vorhanden")

    st.markdown("---")
    st.markdown("**Alle Spalten im Wein-DataFrame:**")
    st.write(list(weine_df.columns))
