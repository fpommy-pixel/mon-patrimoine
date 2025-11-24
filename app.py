import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px

# --- CONFIGURATION ---
st.set_page_config(page_title="Mon Patrimoine", page_icon="💰", layout="wide")

# --- FONCTIONS UTILES ---
def clean_currency(x):
    """Nettoie les textes '1 000 €' en nombres"""
    if pd.isna(x) or str(x).strip() == "": return 0.0
    # On garde seulement les chiffres et le point/virgule
    s = str(x).replace('€', '').replace(' ', '').replace(' ', '').replace(',', '.')
    try:
        return float(s)
    except:
        return 0.0

def get_ticker_yahoo(raw_symbol):
    """Traduit vos codes (ex: EPA:AI) en codes Yahoo (ex: AI.PA)"""
    if pd.isna(raw_symbol): return None
    sym = str(raw_symbol).strip()
    
    mapping = {
        "EPA:CW8-ETFP": "CW8.PA", "EPA:WPEA": "WPEA.PA", 
        "EPA:PAEEM": "PAEEM.PA", "EPA:ETZ": "ETZ.PA", 
        "BIT:1BAYN": "BAYN.DE", "BIT:RACE": "RACE.MI",
        "BTCEUR": "BTC-EUR", "ETHEUR": "ETH-EUR", 
        "NQSOL": "SOL-EUR", "BNB": "BNB-EUR"
    }
    
    if sym in mapping: return mapping[sym]
    if "EPA:" in sym: return sym.replace("EPA:", "") + ".PA"
    return sym

# --- CHARGEMENT DU FICHIER EXCEL UNIQUE ---
@st.cache_data
def load_data():
    file_path = "patrimoine.xlsx"
    
    # Fonction utilitaire pour trouver le nom de feuille sans casse/espace
    def find_sheet(excel_file, target_name):
        """Trouve la feuille de calcul en ignorant la casse et les espaces aux extrémités."""
        for name in excel_file.sheet_names:
            if name.strip().lower() == target_name.lower():
                return name
        return None
    
    # Tente d'ouvrir le fichier Excel
    try:
        xlsx = pd.ExcelFile(file_path)
    except Exception as e:
        st.error(f"FATAL: Erreur lors de l'ouverture de 'patrimoine.xlsx': {e}")
        return pd.DataFrame(), pd.DataFrame(), {}
    
    # --- DIAGNOSTIC CLÉ (affiche la liste exacte des onglets trouvés) ---
    st.info(f"Onglets trouvés : {xlsx.sheet_names}")
    # --------------------------------------------------------------------

    # --- 1. Chargement PEA ---
    try:
        sheet_name_pea = find_sheet(xlsx, "Portefeuille PEA")
        if sheet_name_pea is None:
            st.error(f"ERREUR PEA: L'onglet 'Portefeuille PEA' est introuvable. Vérifiez la casse/les espaces dans le nom.")
            df_pea = pd.DataFrame()
        else:
            # On utilise le nom de feuille trouvé, même s'il a des majuscules différentes
            df_raw = pd.read_excel(xlsx, sheet_name=sheet_name_pea, header=None)
            start_row = df_raw[df_raw.apply(lambda row: row.astype(str).str.contains("CODE GOOGLE").any(), axis=1)].index[0]
            df_pea = pd.read_excel(xlsx, sheet_name=sheet_name_pea, skiprows=start_row+1)
            # ... (le reste du nettoyage PEA reste inchangé) ...
            cols = list(df_pea.columns)
            cols[0] = 'CODE'
            cols[1] = 'NOM'
            cols[2] = 'EN_PORTEFEUILLE'
            cols[4] = 'NB_PARTS'
            cols[5] = 'PRU'
            df_pea.columns = cols
            df_pea = df_pea[df_pea['EN_PORTEFEUILLE'] == True].copy()
            df_pea['NB_PARTS'] = df_pea['NB_PARTS'].apply(clean_currency)
            df_pea['PRU'] = df_pea['PRU'].apply(clean_currency)
    except Exception as e:
        st.error(f"Erreur lecture PEA (Ligne de données après l'en-tête: {e}")
        df_pea = pd.DataFrame()

    # --- 2. Chargement Crypto ---
    try:
        sheet_name_crypto = find_sheet(xlsx, "Crypto")
        if sheet_name_crypto is None:
            st.error(f"ERREUR CRYPTO: L'onglet 'Crypto' est introuvable.")
            df_crypto = pd.DataFrame()
        else:
            df_crypto = pd.read_excel(xlsx, sheet_name=sheet_name_crypto)
            df_crypto['Nombre possédés'] = df_crypto['Nombre possédés'].apply(clean_currency)
    except Exception as e:
        st.error(f"Erreur onglet Crypto (colonnes): {e}")
        df_crypto = pd.DataFrame()

    # --- 3. Chargement Patrimoine Global (Statique) ---
    try:
        sheet_name_patrimoine = find_sheet(xlsx, "Mon Patrimoine")
        if sheet_name_patrimoine is None:
            st.error(f"ERREUR PATRIMOINE: L'onglet 'Mon Patrimoine' est introuvable.")
            statique = {}
        else:
            df_pat = pd.read_excel(xlsx, sheet_name=sheet_name_patrimoine, header=None)
            
            def get_val(label):
                mask = df_pat.apply(lambda row: row.astype(str).str.contains(label, regex=False).any(), axis=1)
                if mask.any():
                    idx = mask.idxmax()
                    val = df_pat.iloc[idx, 2] 
                    return clean_currency(val)
                return 0.0
                
            statique = {
                "Immobilier": get_val("Résidence principale") + get_val("Immobilier Locatif"),
                "Liquidités": get_val("Comptes courant") + get_val("Epargne"),
                "Crowd": get_val("Crowfunding") + get_val("Crowlending"),
                "Or": get_val("OR"),
                "Assurance Vie": get_val("Assurance Vie"),
                "Dettes": get_val("Passif (dettes)")
            }
    except Exception as e:
        st.error(f"Erreur onglet Patrimoine (libellés): {e}")
        statique = {}

    return df_pea, df_crypto, statique

# --- RECUPERATION PRIX LIVE ---
list_tickers = []
if not df_pea.empty:
    list_tickers += df_pea['CODE'].apply(get_ticker_yahoo).dropna().tolist()
if not df_crypto.empty:
    list_tickers += df_crypto['Symbol crypto'].dropna().apply(get_ticker_yahoo).tolist()

live_prices = {}
if list_tickers:
    with st.spinner('Actualisation des prix...'):
        try:
            data = yf.download(list_tickers, period="1d", progress=False)['Close']
            if not data.empty:
                live_prices = data.iloc[-1]
        except:
            st.warning("Erreur de connexion Yahoo Finance")

def get_price(ticker):
    try:
        return float(live_prices[ticker])
    except:
        return 0.0

# --- CALCULS ---
total_bourse = 0
if not df_pea.empty:
    df_pea['Ticker_YF'] = df_pea['CODE'].apply(get_ticker_yahoo)
    df_pea['Prix_Live'] = df_pea['Ticker_YF'].apply(get_price)
    # Si prix live trouvé, on l'utilise, sinon on garde le PRU
    df_pea['Val_Finale'] = df_pea.apply(lambda x: x['Prix_Live'] if x['Prix_Live'] > 0 else x['PRU'], axis=1)
    df_pea['Total'] = df_pea['NB_PARTS'] * df_pea['Val_Finale']
    total_bourse = df_pea['Total'].sum()

total_crypto = 0
if not df_crypto.empty:
    df_crypto['Ticker_YF'] = df_crypto['Symbol crypto'].apply(get_ticker_yahoo)
    df_crypto['Prix_Live'] = df_crypto['Ticker_YF'].apply(get_price)
    df_crypto['Total'] = df_crypto['Nombre possédés'] * df_crypto['Prix_Live']
    # Ajout des montants manuels (sans symbole)
    manual_crypto = df_crypto[df_crypto['Symbol crypto'].isna()]['Montant'].apply(clean_currency).sum()
    total_crypto = df_crypto['Total'].sum() + manual_crypto

net_worth = (statique.get('Immobilier', 0) + statique.get('Liquidités', 0) + 
             statique.get('Crowd', 0) + statique.get('Or', 0) + 
             statique.get('Assurance Vie', 0) + total_bourse + total_crypto - statique.get('Dettes', 0))

# --- AFFICHAGE ---
st.metric("Patrimoine Net", f"{net_worth:,.0f} €".replace(',', ' '))

col1, col2 = st.columns(2)
col1.metric("Bourse Live", f"{total_bourse:,.0f} €".replace(',', ' '))
col2.metric("Crypto Live", f"{total_crypto:,.0f} €".replace(',', ' '))

# Graphique
data_pie = {
    "Immo": statique.get('Immobilier', 0),
    "Bourse": total_bourse,
    "Assurance Vie": statique.get('Assurance Vie', 0),
    "Crypto": total_crypto,
    "Liquidités": statique.get('Liquidités', 0),
    "Crowd": statique.get('Crowd', 0)
}
fig = px.pie(values=list(data_pie.values()), names=list(data_pie.keys()), hole=0.5)
st.plotly_chart(fig)

# Tableau Bourse simplifié
if not df_pea.empty:
    st.subheader("Top Actions")

    st.dataframe(df_pea[['NOM', 'Total']].sort_values('Total', ascending=False).head(5))

# Dernière MAJ

