import json
import os
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Optional, Tuple, Dict, Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

# =========================================================
# STREAMLIT PAGE CONFIG  (TEM QUE SER O PRIMEIRO st.*)
# =========================================================
st.set_page_config(
    page_title="Brewery Planner | Planejamento Cervejaria",
    layout="wide",
    initial_sidebar_state="expanded",
    page_icon="🍺",
)
pio.templates.default = "plotly_white"

# =========================================================
# HARD-GUARD: se rodar com "python breweryplanner.py", roda via Streamlit
# (evita "missing ScriptRunContext" e comportamento estranho no VSCode)
# =========================================================
def _running_inside_streamlit() -> bool:
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        return get_script_run_ctx() is not None
    except Exception:
        return False

if __name__ == "__main__" and not _running_inside_streamlit():
    import sys
    from streamlit.web import cli as stcli
    sys.argv = ["streamlit", "run", str(Path(__file__).resolve())]
    raise SystemExit(stcli.main())

# =========================================================
# CONFIG FILE: tema claro + texto escuro + headless
# =========================================================
def ensure_streamlit_config():
    """
    Cria .streamlit/config.toml se não existir.
    - Tema claro + texto escuro
    - headless=true evita abrir abas automaticamente
    - runOnSave=false reduz restarts no VSCode
    """
    try:
        project_root = Path(__file__).resolve().parent
        cfg_dir = project_root / ".streamlit"
        cfg_file = cfg_dir / "config.toml"

        desired = """[theme]
base="light"
primaryColor="#4c8df6"
backgroundColor="#f7f9fc"
secondaryBackgroundColor="#ffffff"
textColor="#0f172a"
font="sans serif"

[server]
headless=true
runOnSave=false

[browser]
gatherUsageStats=false
"""
        if not cfg_file.exists():
            cfg_dir.mkdir(parents=True, exist_ok=True)
            cfg_file.write_text(desired, encoding="utf-8")

            # aviso (agora ok, porque page_config já rodou)
            if not st.session_state.get("_cfg_notice_shown", False):
                st.session_state["_cfg_notice_shown"] = True
                st.warning(
                    "Criei **.streamlit/config.toml** (tema claro + texto escuro + headless). "
                    "Pare e rode novamente para aplicar:\n\n"
                    "`streamlit run breweryplanner.py`"
                )
    except Exception as e:
        if not st.session_state.get("_cfg_err_shown", False):
            st.session_state["_cfg_err_shown"] = True
            st.warning(
                "Não consegui criar automaticamente `.streamlit/config.toml`.\n\n"
                f"Detalhe: {e}"
            )

ensure_streamlit_config()

# =========================================================
# CONSTANTS
# =========================================================
DEFAULT_SCENARIO_NAME = "Base"

DB_DIR = Path.home() / ".breweryplanner"
DB_FILE = DB_DIR / "breweryplanner_db.json"

STATUS_OPTIONS = ["Comprado", "Orçado", "Pendente", "Estimado"]
SKUS_REQUIRED = [
    ("Copo Taproom", "Taproom"),
    ("Chope (R$/L)", "Varejo"),
    ("Lata 473ml", "Varejo"),
    ("Garrafa 600ml", "Varejo"),
    ("Long Neck", "Varejo"),
    ("PET Growler 1,5L", "Varejo"),
]
EMB_EXCLUDE_DIST = ("Barril 30L", "Barril 50L", "Copo Taproom")
VAR_TEXT = "#0f172a"

# =========================================================
# CSS (layout e cards) — sem tentar forçar texto da grid via CSS
# =========================================================
st.markdown(
    """
<style>
:root {
  --bg: #f7f9fc;
  --card: #ffffff;
  --text: #0f172a;
  --muted: #6c7280;
  --line: rgba(15, 23, 42, .08);
  --shadow: 0 14px 40px rgba(15, 23, 42, .08);
  --shadow2: 0 4px 18px rgba(15, 23, 42, .06);
  --accent: #4c8df6;
  --accent2: #2f73e0;
}

.stApp { background: var(--bg); }
.main .block-container { padding-top: 1.2rem; padding-bottom: 2.4rem; }
h1,h2,h3 { color: var(--text); letter-spacing: -0.02em; }
p, label, .stMarkdown { color: var(--text); }
* { color-scheme: light; }
div[data-testid="stMarkdownContainer"] * { color: var(--text)!important; }

section[data-testid="stSidebar"]{ background: #ffffff; border-right: 1px solid var(--line); }
section[data-testid="stSidebar"] .block-container { padding-top: 1.4rem; }

.brand-box{ display:flex;align-items:center;gap:12px; padding:10px 12px 10px 6px; }
.brand-logo{width:38px;height:38px;display:flex;align-items:center;justify-content:center;border-radius:12px;background:rgba(76,141,246,.12);color:var(--accent);font-weight:800;font-size:18px;}
.brand-title{font-size:20px;font-weight:800;letter-spacing:-0.02em;margin:0;color:var(--text);}

.stButton button{ border-radius: 14px; border: 1px solid var(--line); background: white; color: var(--text);
  box-shadow: var(--shadow2); padding: 0.52rem 0.8rem; font-weight: 650; }
.stButton button:hover{ border-color: rgba(76,141,246,.35); box-shadow: var(--shadow); }
div[data-testid="stDownloadButton"] button{ background: var(--accent); color: white; border-color: rgba(76,141,246,.0); box-shadow: var(--shadow2); }
div[data-testid="stDownloadButton"] button:hover{ background: var(--accent2); }

.stTabs [data-baseweb="tab-list"]{ gap: 10px; padding: 6px 6px; background: rgba(255,255,255,.65);
  border: 1px solid var(--line); border-radius: 999px; box-shadow: var(--shadow2); }
.stTabs [data-baseweb="tab"]{ padding: 10px 16px; border-radius: 999px; background: rgba(255,255,255,.95);
  border: 1px solid rgba(15,23,42,.08); color: var(--text); font-weight: 650; }

div[data-testid="stMetric"]{ background: var(--card); border: 1px solid var(--line); border-radius: 18px;
  padding: 16px 16px; box-shadow: var(--shadow2); }

div[data-testid="stDataFrame"], div[data-testid="stDataEditor"]{
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 16px;
  box-shadow: var(--shadow2);
  padding: 8px;
}

.helper-card{ background: var(--card); border: 1px solid var(--line); border-radius: 16px; padding: 14px; box-shadow: var(--shadow2); }
.helper-title{ font-weight: 750; color: var(--text); margin: 0 0 4px 0; }
.helper-sub{ color: var(--muted); margin: 0; }
hr { border: none; border-top: 1px solid var(--line); margin: 1rem 0; }
</style>
""",
    unsafe_allow_html=True,
)


# =========================================================
# UTIL
# =========================================================
def brl(x: float) -> str:
    try:
        return f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0,00"


def safe_toast(msg: str, icon: str = "✅"):
    try:
        st.toast(msg, icon=icon)
    except Exception:
        st.success(msg)


def ensure_cols(df: pd.DataFrame, cols_defaults: dict) -> pd.DataFrame:
    if df is None or not isinstance(df, pd.DataFrame):
        df = pd.DataFrame()
    for c, d in cols_defaults.items():
        if c not in df.columns:
            df[c] = d
    return df


def _df(records, cols_defaults=None):
    df = pd.DataFrame(records or [])
    if cols_defaults:
        df = ensure_cols(df, cols_defaults)
    return df


def _clean_numeric(df: pd.DataFrame, cols: list) -> pd.DataFrame:
    for c in cols:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    return df


def _merge_filtered(full_df: pd.DataFrame, filtered_df: pd.DataFrame, key_cols: list) -> pd.DataFrame:
    if full_df.empty:
        return filtered_df.copy()
    if filtered_df.empty:
        return full_df.copy()
    base = full_df.copy()
    base["_merge_key"] = base[key_cols].astype(str).agg("||".join, axis=1)
    new = filtered_df.copy()
    new["_merge_key"] = new[key_cols].astype(str).agg("||".join, axis=1)
    base = base[~base["_merge_key"].isin(new["_merge_key"])]
    merged = pd.concat([base.drop(columns=["_merge_key"]), new.drop(columns=["_merge_key"])]).reset_index(drop=True)
    return merged


# =========================================================
# DEFAULT DATA
# =========================================================
def default_scenario():
    capex = [
        {"Categoria": "Produção Quente", "Item": "Tribloco 500L Industrial", "Valor": 68000.00, "Status": "Orçado"},
        {"Categoria": "Produção Quente", "Item": "Moinho de Rolos Alta Capacidade", "Valor": 4500.00, "Status": "Pendente"},
        {"Categoria": "Fermentação", "Item": "Fermentador Cônico 500L (Unid 1)", "Valor": 14500.00, "Status": "Orçado"},
        {"Categoria": "Fermentação", "Item": "Fermentador Cônico 500L (Unid 2)", "Valor": 14500.00, "Status": "Orçado"},
        {"Categoria": "Fermentação", "Item": "Fermentador Cônico 500L (Unid 3)", "Valor": 14500.00, "Status": "Orçado"},
        {"Categoria": "Fermentação", "Item": "Fermentador Cônico 500L (Unid 4)", "Valor": 14500.00, "Status": "Orçado"},
        {"Categoria": "Frio", "Item": "Chiller 15.000 kcal + Bomba Glicol", "Valor": 18500.00, "Status": "Pendente"},
        {"Categoria": "Frio", "Item": "Câmara Fria Modular (3x3m)", "Valor": 12000.00, "Status": "Pendente"},
        {"Categoria": "Envase", "Item": "Envasadora Counter Pressure Semi-auto", "Valor": 3500.00, "Status": "Comprado"},
        {"Categoria": "Logística", "Item": "Parque Barris Inox (Lote A)", "Valor": 16500.00, "Status": "Pendente"},
        {"Categoria": "Infraestrutura", "Item": "Adequação Civil e Piso", "Valor": 35000.00, "Status": "Estimado"},
        {"Categoria": "Infraestrutura", "Item": "Licenciamento e Projetos", "Valor": 5000.00, "Status": "Estimado"},
    ]

    opex_outros = [
        {"Descrição": "Aluguel Galpão", "Valor": 5000.00},
        {"Descrição": "Energia (Fixo)", "Valor": 1500.00},
        {"Descrição": "Marketing", "Valor": 2000.00},
        {"Descrição": "Internet/Telefonia", "Valor": 250.00},
        {"Descrição": "Contabilidade", "Valor": 300.00},
    ]

    funcionarios = [
        {"Nome": "Cervejeiro(a)", "Modalidade": "CLT", "Salário Bruto": 4500.00, "Encargos CLT (%)": 70.0, "Considerar 13º": True, "Considerar Férias": True},
        {"Nome": "Auxiliar Produção", "Modalidade": "CLT", "Salário Bruto": 2500.00, "Encargos CLT (%)": 70.0, "Considerar 13º": True, "Considerar Férias": True},
        {"Nome": "Vendas (PJ)", "Modalidade": "PJ", "Salário Bruto": 2200.00, "Encargos CLT (%)": 0.0, "Considerar 13º": False, "Considerar Férias": False},
    ]

    insumos = [
        {"Tipo": "Malte", "Nome": "Malte Pilsen Agrária", "Unidade": "kg", "Custo": 6.90},
        {"Tipo": "Malte", "Nome": "Malte Pale Ale", "Unidade": "kg", "Custo": 7.50},
        {"Tipo": "Malte", "Nome": "Malte Caramelo", "Unidade": "kg", "Custo": 11.00},
        {"Tipo": "Malte", "Nome": "Malte Trigo (Weiss)", "Unidade": "kg", "Custo": 8.00},
        {"Tipo": "Malte", "Nome": "Malte Torrado/Chocolate", "Unidade": "kg", "Custo": 14.00},
        {"Tipo": "Lúpulo", "Nome": "Lúpulo Citra", "Unidade": "kg", "Custo": 320.00},
        {"Tipo": "Lúpulo", "Nome": "Lúpulo Magnum (Amargor)", "Unidade": "kg", "Custo": 180.00},
        {"Tipo": "Lúpulo", "Nome": "Lúpulo Cascade", "Unidade": "kg", "Custo": 250.00},
        {"Tipo": "Lúpulo", "Nome": "Lúpulo Saaz (Lager)", "Unidade": "kg", "Custo": 280.00},
        {"Tipo": "Lúpulo", "Nome": "Lúpulo Hallertau", "Unidade": "kg", "Custo": 290.00},
        {"Tipo": "Levedura", "Nome": "US-05 (Ale Americana)", "Unidade": "pct", "Custo": 28.00},
        {"Tipo": "Levedura", "Nome": "S-04 (Ale Inglesa/Stout)", "Unidade": "pct", "Custo": 26.00},
        {"Tipo": "Levedura", "Nome": "W-34/70 (Lager)", "Unidade": "pct", "Custo": 35.00},
        {"Tipo": "Levedura", "Nome": "WB-06 (Weiss)", "Unidade": "pct", "Custo": 30.00},
    ]

    receitas_header = [
        {"ID": 1, "Nome": "American IPA", "Volume Batelada (L)": 500},
        {"ID": 2, "Nome": "Classic APA", "Volume Batelada (L)": 500},
        {"ID": 3, "Nome": "Pilsen Padrão", "Volume Batelada (L)": 500},
        {"ID": 4, "Nome": "Dry Stout", "Volume Batelada (L)": 500},
        {"ID": 5, "Nome": "Weissbier", "Volume Batelada (L)": 500},
    ]

    receitas_detalhe = [
        {"Receita_ID": 1, "Insumo": "Malte Pale Ale", "Qtd": 110, "Custo_Unit": 7.50, "Custo_Total": 825.0},
        {"Receita_ID": 1, "Insumo": "Malte Caramelo", "Qtd": 8, "Custo_Unit": 11.00, "Custo_Total": 88.0},
        {"Receita_ID": 1, "Insumo": "Lúpulo Magnum (Amargor)", "Qtd": 0.5, "Custo_Unit": 180.00, "Custo_Total": 90.0},
        {"Receita_ID": 1, "Insumo": "Lúpulo Citra", "Qtd": 4.0, "Custo_Unit": 320.00, "Custo_Total": 1280.0},
        {"Receita_ID": 1, "Insumo": "US-05 (Ale Americana)", "Qtd": 30, "Custo_Unit": 28.00, "Custo_Total": 840.0},

        {"Receita_ID": 2, "Insumo": "Malte Pale Ale", "Qtd": 100, "Custo_Unit": 7.50, "Custo_Total": 750.0},
        {"Receita_ID": 2, "Insumo": "Malte Caramelo", "Qtd": 5, "Custo_Unit": 11.00, "Custo_Total": 55.0},
        {"Receita_ID": 2, "Insumo": "Lúpulo Cascade", "Qtd": 2.5, "Custo_Unit": 250.00, "Custo_Total": 625.0},
        {"Receita_ID": 2, "Insumo": "US-05 (Ale Americana)", "Qtd": 25, "Custo_Unit": 28.00, "Custo_Total": 700.0},

        {"Receita_ID": 3, "Insumo": "Malte Pilsen Agrária", "Qtd": 95, "Custo_Unit": 6.90, "Custo_Total": 655.5},
        {"Receita_ID": 3, "Insumo": "Malte Caramelo", "Qtd": 3, "Custo_Unit": 11.00, "Custo_Total": 33.0},
        {"Receita_ID": 3, "Insumo": "Lúpulo Magnum (Amargor)", "Qtd": 0.3, "Custo_Unit": 180.00, "Custo_Total": 54.0},
        {"Receita_ID": 3, "Insumo": "Lúpulo Saaz (Lager)", "Qtd": 1.0, "Custo_Unit": 280.00, "Custo_Total": 280.0},
        {"Receita_ID": 3, "Insumo": "W-34/70 (Lager)", "Qtd": 40, "Custo_Unit": 35.00, "Custo_Total": 1400.0},

        {"Receita_ID": 4, "Insumo": "Malte Pale Ale", "Qtd": 85, "Custo_Unit": 7.50, "Custo_Total": 637.5},
        {"Receita_ID": 4, "Insumo": "Malte Torrado/Chocolate", "Qtd": 10, "Custo_Unit": 14.00, "Custo_Total": 140.0},
        {"Receita_ID": 4, "Insumo": "Malte Caramelo", "Qtd": 5, "Custo_Unit": 11.00, "Custo_Total": 55.0},
        {"Receita_ID": 4, "Insumo": "Lúpulo Magnum (Amargor)", "Qtd": 0.8, "Custo_Unit": 180.00, "Custo_Total": 144.0},
        {"Receita_ID": 4, "Insumo": "S-04 (Ale Inglesa/Stout)", "Qtd": 25, "Custo_Unit": 26.00, "Custo_Total": 650.0},

        {"Receita_ID": 5, "Insumo": "Malte Trigo (Weiss)", "Qtd": 50, "Custo_Unit": 8.00, "Custo_Total": 400.0},
        {"Receita_ID": 5, "Insumo": "Malte Pilsen Agrária", "Qtd": 50, "Custo_Unit": 6.90, "Custo_Total": 345.0},
        {"Receita_ID": 5, "Insumo": "Lúpulo Hallertau", "Qtd": 0.6, "Custo_Unit": 290.00, "Custo_Total": 174.0},
        {"Receita_ID": 5, "Insumo": "WB-06 (Weiss)", "Qtd": 25, "Custo_Unit": 30.00, "Custo_Total": 750.0},
    ]

    embalagens = [
        {"Embalagem": "Lata 473ml", "Volume (L)": 0.473, "Custo Unit (R$)": 1.60},
        {"Embalagem": "Garrafa 600ml", "Volume (L)": 0.600, "Custo Unit (R$)": 1.40},
        {"Embalagem": "Long Neck", "Volume (L)": 0.330, "Custo Unit (R$)": 1.10},
        {"Embalagem": "Barril 30L", "Volume (L)": 30.0, "Custo Unit (R$)": 0.00},
        {"Embalagem": "Barril 50L", "Volume (L)": 50.0, "Custo Unit (R$)": 0.00},
        {"Embalagem": "PET Growler 1,5L", "Volume (L)": 1.50, "Custo Unit (R$)": 2.20},
        {"Embalagem": "Copo Taproom", "Volume (L)": 0.473, "Custo Unit (R$)": 0.25},
    ]

    precos_sku = [
        {"SKU": "Lata 473ml", "Canal": "Varejo", "Preço Unit (R$)": 22.00},
        {"SKU": "Garrafa 600ml", "Canal": "Varejo", "Preço Unit (R$)": 26.00},
        {"SKU": "Long Neck", "Canal": "Varejo", "Preço Unit (R$)": 14.00},
        {"SKU": "PET Growler 1,5L", "Canal": "Varejo", "Preço Unit (R$)": 38.00},
        {"SKU": "Chope (R$/L)", "Canal": "Varejo", "Preço Unit (R$)": 13.00},
        {"SKU": "Copo Taproom", "Canal": "Taproom", "Preço Unit (R$)": 20.00},
    ]

    mix = {
        "Volume Vendido (L/mês)": 2000,
        "Mix Taproom (%)": 30,
        "Mix Varejo Chope (%)": 25,
        "Mix Varejo Embalado (%)": 45,
        "Distribuição Embalado (%)": {
            "Lata 473ml": 45,
            "Garrafa 600ml": 15,
            "Long Neck": 25,
            "PET Growler 1,5L": 15,
        },
        "Receita Base (para custo)": "Pilsen Padrão",
    }

    premissas = {
        "GIP Químicos (R$/L)": 0.25,
        "GIP Energia (R$/L)": 0.35,
        "GIP Água (R$/L)": 0.15,
        "GIP CO2 (R$/L)": 0.15,
        "Impostos s/ venda (%)": 10.0,
        "Capital de giro (meses)": 6,
    }

    financiamento = {
        "Ativo": False,
        "Percentual financiado (%)": 60.0,
        "Taxa juros a.a. (%)": 18.0,
        "Prazo (meses)": 48,
        "Carência (meses)": 0,
    }

    return {
        "capex_db": capex,
        "opex_outros_db": opex_outros,
        "funcionarios_db": funcionarios,
        "insumos_db": insumos,
        "receitas_header": receitas_header,
        "receitas_detalhe": receitas_detalhe,
        "embalagens_db": embalagens,
        "precos_sku": precos_sku,
        "mix": mix,
        "premissas": premissas,
        "financiamento": financiamento,
    }


# =========================================================
# DB LOAD/SAVE (com migração)
# =========================================================
def _empty_db():
    return {"scenarios": {DEFAULT_SCENARIO_NAME: default_scenario()}, "selected": DEFAULT_SCENARIO_NAME}


def load_db() -> dict:
    if not DB_FILE.exists():
        return _empty_db()

    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return _empty_db()

    # MIGRAÇÃO 1: formato antigo single scenario (sem "scenarios")
    if "scenarios" not in raw:
        sc = {}
        for k in [
            "capex_db",
            "opex_db",
            "insumos_db",
            "receitas_header",
            "receitas_detalhe",
            "precos_venda",
            "opex_outros_db",
            "funcionarios_db",
            "embalagens_db",
            "precos_sku",
            "mix",
            "premissas",
            "financiamento",
        ]:
            if k in raw:
                sc[k] = raw.get(k)
        if "opex_db" in sc and "opex_outros_db" not in sc:
            sc["opex_outros_db"] = sc.pop("opex_db")
        if "precos_venda" in sc and "precos_sku" not in sc:
            sc["precos_sku"] = sc.pop("precos_venda")
        base = default_scenario()
        base.update({k: v for k, v in sc.items() if v is not None})
        return {"scenarios": {DEFAULT_SCENARIO_NAME: base}, "selected": DEFAULT_SCENARIO_NAME}

    # MIGRAÇÃO 2: db["scenarios"] vindo como LISTA
    if isinstance(raw.get("scenarios"), list):
        sc_dict = {}
        for i, item in enumerate(raw["scenarios"]):
            if isinstance(item, dict):
                name = item.get("name") or item.get("Nome") or f"Cenário {i+1}"
                data = item.get("data") or item
                sc_dict[str(name)] = data
        raw["scenarios"] = sc_dict

    if not isinstance(raw.get("scenarios"), dict) or len(raw["scenarios"]) == 0:
        raw = _empty_db()

    sel = raw.get("selected")
    if sel not in raw["scenarios"]:
        raw["selected"] = list(raw["scenarios"].keys())[0]

    return raw


def save_db(db: dict):
    try:
        DB_DIR.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile("w", delete=False, encoding="utf-8", dir=DB_DIR) as tmp:
            json.dump(db, tmp, indent=2, ensure_ascii=False)
            tmp_path = Path(tmp.name)
        os.replace(tmp_path, DB_FILE)
        safe_toast("Dados salvos com sucesso!", "💾")
    except Exception as e:
        st.error(f"Erro ao salvar banco: {e}")


# =========================================================
# SESSION INIT
# =========================================================
if "db" not in st.session_state:
    st.session_state.db = load_db()


def get_scenario_name() -> str:
    return st.session_state.db.get("selected", DEFAULT_SCENARIO_NAME)


def set_selected(name: str):
    if name in st.session_state.db.get("scenarios", {}):
        st.session_state.db["selected"] = name


def get_scenario() -> dict:
    name = get_scenario_name()
    return st.session_state.db["scenarios"].get(name, default_scenario())


def put_scenario(name: str, data: dict):
    st.session_state.db["scenarios"][name] = data


# =========================================================
# DATAFRAME GETTERS (por cenário)
# =========================================================
def scenario_dfs(sc: dict):
    capex_df = _df(sc.get("capex_db"), {"Categoria": "", "Item": "", "Valor": 0.0, "Status": "Pendente"})
    capex_df = _clean_numeric(capex_df, ["Valor"])
    capex_df["Status"] = capex_df["Status"].fillna("Pendente")

    opex_outros_df = _df(sc.get("opex_outros_db"), {"Descrição": "", "Valor": 0.0})
    opex_outros_df = _clean_numeric(opex_outros_df, ["Valor"])

    funcionarios_df = _df(
        sc.get("funcionarios_db"),
        {
            "Nome": "",
            "Modalidade": "CLT",
            "Salário Bruto": 0.0,
            "Encargos CLT (%)": 70.0,
            "Considerar 13º": True,
            "Considerar Férias": True,
        },
    )
    funcionarios_df = _clean_numeric(funcionarios_df, ["Salário Bruto", "Encargos CLT (%)"])
    funcionarios_df["Modalidade"] = (
        funcionarios_df["Modalidade"].fillna("CLT").replace({"Clt": "CLT", "pj": "PJ", "Pj": "PJ"})
    )
    funcionarios_df["Considerar 13º"] = funcionarios_df["Considerar 13º"].fillna(True).astype(bool)
    funcionarios_df["Considerar Férias"] = funcionarios_df["Considerar Férias"].fillna(True).astype(bool)

    insumos_df = _df(sc.get("insumos_db"), {"Tipo": "", "Nome": "", "Unidade": "kg", "Custo": 0.0})
    insumos_df = _clean_numeric(insumos_df, ["Custo"])

    receitas_header_df = _df(sc.get("receitas_header"), {"ID": 1, "Nome": "", "Volume Batelada (L)": 500})
    receitas_header_df = _clean_numeric(receitas_header_df, ["ID", "Volume Batelada (L)"])
    receitas_header_df["ID"] = receitas_header_df["ID"].astype(int)

    receitas_det_df = _df(
        sc.get("receitas_detalhe"),
        {"Receita_ID": 1, "Insumo": "", "Qtd": 0.0, "Custo_Unit": 0.0, "Custo_Total": 0.0},
    )
    receitas_det_df = _clean_numeric(receitas_det_df, ["Receita_ID", "Qtd", "Custo_Unit"])
    receitas_det_df["Receita_ID"] = receitas_det_df["Receita_ID"].astype(int)
    receitas_det_df["Custo_Total"] = (receitas_det_df["Qtd"] * receitas_det_df["Custo_Unit"]).astype(float)

    emb_df = _df(sc.get("embalagens_db"), {"Embalagem": "", "Volume (L)": 0.0, "Custo Unit (R$)": 0.0})
    emb_df = _clean_numeric(emb_df, ["Volume (L)", "Custo Unit (R$)"])

    precos_df = _df(sc.get("precos_sku"), {"SKU": "", "Canal": "Varejo", "Preço Unit (R$)": 0.0})
    precos_df["Canal"] = precos_df["Canal"].fillna("Varejo")
    precos_df = _clean_numeric(precos_df, ["Preço Unit (R$)"])

    mix = sc.get("mix") or default_scenario()["mix"]
    prem = sc.get("premissas") or default_scenario()["premissas"]
    fin = sc.get("financiamento") or default_scenario()["financiamento"]

    return capex_df, opex_outros_df, funcionarios_df, insumos_df, receitas_header_df, receitas_det_df, emb_df, precos_df, mix, prem, fin


def persist_dfs(
    sc_name: str,
    sc: dict,
    capex_df,
    opex_outros_df,
    funcionarios_df,
    insumos_df,
    receitas_header_df,
    receitas_det_df,
    emb_df,
    precos_df,
    mix,
    prem,
    fin,
):
    sc["capex_db"] = capex_df.reset_index(drop=True).to_dict("records")
    sc["opex_outros_db"] = opex_outros_df.reset_index(drop=True).to_dict("records")
    sc["funcionarios_db"] = funcionarios_df.reset_index(drop=True).to_dict("records")
    sc["insumos_db"] = insumos_df.reset_index(drop=True).to_dict("records")
    sc["receitas_header"] = receitas_header_df.reset_index(drop=True).to_dict("records")
    sc["receitas_detalhe"] = receitas_det_df.reset_index(drop=True).to_dict("records")
    sc["embalagens_db"] = emb_df.reset_index(drop=True).to_dict("records")
    sc["precos_sku"] = precos_df.reset_index(drop=True).to_dict("records")
    sc["mix"] = mix
    sc["premissas"] = prem
    sc["financiamento"] = fin
    put_scenario(sc_name, sc)


# =========================================================
# FINANCE CALCS
# =========================================================
def calc_gip_total(prem: dict) -> float:
    return (
        float(prem.get("GIP Químicos (R$/L)", 0.0))
        + float(prem.get("GIP Energia (R$/L)", 0.0))
        + float(prem.get("GIP Água (R$/L)", 0.0))
        + float(prem.get("GIP CO2 (R$/L)", 0.0))
    )


def calc_folha_mensal(func_df: pd.DataFrame) -> pd.DataFrame:
    df = func_df.copy()
    df["Custo Mensal (R$)"] = 0.0

    for i, r in df.iterrows():
        mod = str(r.get("Modalidade", "CLT")).upper().strip()
        sal = float(r.get("Salário Bruto", 0.0) or 0.0)
        if mod == "PJ":
            custo = sal
        else:
            encargos = float(r.get("Encargos CLT (%)", 0.0) or 0.0) / 100.0
            custo_base = sal * (1.0 + encargos)

            prov_13 = sal / 12.0 if bool(r.get("Considerar 13º", True)) else 0.0
            prov_ferias = (sal * (4.0 / 3.0)) / 12.0 if bool(r.get("Considerar Férias", True)) else 0.0

            custo = custo_base + prov_13 + prov_ferias
        df.at[i, "Custo Mensal (R$)"] = float(custo)

    return df


def recipe_cost_per_liter(
    receitas_header_df: pd.DataFrame,
    receitas_det_df: pd.DataFrame,
    prem: dict,
    recipe_name: Optional[str],
) -> float:
    gip = calc_gip_total(prem)
    if receitas_header_df.empty:
        return gip

    names = set(receitas_header_df["Nome"].tolist())
    if not recipe_name or recipe_name not in names:
        recipe_name = receitas_header_df["Nome"].iloc[0]

    row = receitas_header_df[receitas_header_df["Nome"] == recipe_name].iloc[0]
    rid = int(row["ID"])
    vol = float(row["Volume Batelada (L)"] or 0.0)

    det = receitas_det_df[receitas_det_df["Receita_ID"] == rid].copy()
    if det.empty or vol <= 0:
        return gip

    if "Custo_Total" not in det.columns:
        det["Custo_Total"] = det["Qtd"] * det["Custo_Unit"]
    custo_total = float(det["Custo_Total"].sum())
    return (custo_total / vol) + gip


def get_price(precos_df: pd.DataFrame, sku: str, canal: str) -> float:
    m = precos_df[(precos_df["SKU"] == sku) & (precos_df["Canal"] == canal)]
    if m.empty:
        return 0.0
    return float(m["Preço Unit (R$)"].iloc[0])


def get_pack_cost(emb_df: pd.DataFrame, embalagem: str) -> Tuple[float, float]:
    m = emb_df[emb_df["Embalagem"] == embalagem]
    if m.empty:
        return 0.0, 0.0
    return float(m["Volume (L)"].iloc[0]), float(m["Custo Unit (R$)"].iloc[0])


def normalize_dist(dist: dict) -> dict:
    clean = {k: max(0.0, float(v or 0.0)) for k, v in (dist or {}).items()}
    s = sum(clean.values())
    if s <= 0:
        return clean
    return {k: (v / s) * 100.0 for k, v in clean.items()}


def compute_monthly_dre(
    volume_mes_l: float,
    mix_taproom: float,
    mix_varejo_chope: float,
    mix_varejo_emb: float,
    dist_emb_percent: dict,
    receita_base_nome: str,
    receitas_header_df: pd.DataFrame,
    receitas_det_df: pd.DataFrame,
    emb_df: pd.DataFrame,
    precos_df: pd.DataFrame,
    prem: dict,
) -> dict:
    volume_mes_l = max(0.0, float(volume_mes_l))
    impostos_pct = float(prem.get("Impostos s/ venda (%)", 0.0) or 0.0) / 100.0
    custo_liquido_l = recipe_cost_per_liter(receitas_header_df, receitas_det_df, prem, receita_base_nome)

    vol_tap = volume_mes_l * (mix_taproom / 100.0)
    vol_vch = volume_mes_l * (mix_varejo_chope / 100.0)
    vol_vemb = volume_mes_l * (mix_varejo_emb / 100.0)

    preco_chope_l = get_price(precos_df, "Chope (R$/L)", "Varejo")
    preco_copo = get_price(precos_df, "Copo Taproom", "Taproom")

    copo_vol_l, copo_custo = get_pack_cost(emb_df, "Copo Taproom")
    copo_vol_l = copo_vol_l or 0.473
    cups = vol_tap / copo_vol_l if copo_vol_l > 0 else 0.0
    receita_tap = cups * preco_copo
    custo_copo_total = cups * copo_custo

    receita_vch = vol_vch * preco_chope_l

    dist_emb = normalize_dist(dist_emb_percent)
    receita_emb = 0.0
    custo_embalagem_total = 0.0

    for emb_name, pct in dist_emb.items():
        vol_ = vol_vemb * (pct / 100.0)
        v_l, c_u = get_pack_cost(emb_df, emb_name)
        if v_l <= 0:
            continue
        unidades = vol_ / v_l
        preco_u = get_price(precos_df, emb_name, "Varejo")
        receita_emb += unidades * preco_u
        custo_embalagem_total += unidades * c_u

    receita_bruta = receita_tap + receita_vch + receita_emb
    impostos = receita_bruta * impostos_pct

    cmv_liquido = volume_mes_l * custo_liquido_l
    cmv = cmv_liquido + custo_embalagem_total + custo_copo_total

    margem = receita_bruta - impostos - cmv

    return {
        "Receita bruta": receita_bruta,
        "Impostos": impostos,
        "CMV líquido": cmv_liquido,
        "Custo embalagens": custo_embalagem_total,
        "Custo copos": custo_copo_total,
        "CMV total": cmv,
        "Margem de contribuição": margem,
        "Taproom (copos/mês)": cups,
        "Varejo chope (L/mês)": vol_vch,
        "Varejo embalado (L/mês)": vol_vemb,
    }


def pmt_price(pv: float, rate_month: float, nper: int) -> float:
    if nper <= 0:
        return 0.0
    if rate_month <= 0:
        return pv / nper
    return (pv * rate_month) / (1 - (1 + rate_month) ** (-nper))


def build_payback_series(invest: float, monthly_cash: float, months: int = 84) -> Tuple[pd.DataFrame, Optional[int]]:
    saldo = [-invest]
    pay_m = None
    acc = -invest
    for m in range(1, months + 1):
        acc += monthly_cash
        saldo.append(acc)
        if acc >= 0 and pay_m is None:
            pay_m = m
    df = pd.DataFrame({"Mês": list(range(0, months + 1)), "Saldo": saldo})
    return df, pay_m


def ensure_white_fig(fig: go.Figure) -> go.Figure:
    title_text = getattr(getattr(fig.layout, "title", None), "text", None)
    if title_text is None or str(title_text).strip().lower() == "undefined":
        fig.update_layout(title_text="")

    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="white",
        plot_bgcolor="white",
        font=dict(color=VAR_TEXT),
        title_font=dict(color=VAR_TEXT),
        xaxis=dict(color=VAR_TEXT, title_font=dict(color=VAR_TEXT)),
        yaxis=dict(color=VAR_TEXT, title_font=dict(color=VAR_TEXT)),
    )
    return fig


# =========================================================
# EXCEL IMPORT/EXPORT
# =========================================================
def scenario_to_excel_bytes(sc_name: str, sc: dict) -> bytes:
    capex_df, opex_outros_df, func_df, ins_df, rh_df, rd_df, emb_df, precos_df, mix, prem, fin = scenario_dfs(sc)

    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        capex_df.to_excel(writer, index=False, sheet_name="CAPEX")
        opex_outros_df.to_excel(writer, index=False, sheet_name="OPEX_Outros")
        func_df.to_excel(writer, index=False, sheet_name="Funcionarios")
        ins_df.to_excel(writer, index=False, sheet_name="Insumos")
        rh_df.to_excel(writer, index=False, sheet_name="Receitas_Header")
        rd_df.to_excel(writer, index=False, sheet_name="Receitas_Detalhe")
        emb_df.to_excel(writer, index=False, sheet_name="Embalagens")
        precos_df.to_excel(writer, index=False, sheet_name="Precos_SKU")

        mix_rows = []
        for k, v in (mix or {}).items():
            if isinstance(v, dict):
                for kk, vv in v.items():
                    mix_rows.append({"Chave": f"{k}::{kk}", "Valor": vv})
            else:
                mix_rows.append({"Chave": k, "Valor": v})
        pd.DataFrame(mix_rows).to_excel(writer, index=False, sheet_name="Mix_Demanda")

        prem_rows = [{"Chave": k, "Valor": v} for k, v in (prem or {}).items()]
        pd.DataFrame(prem_rows).to_excel(writer, index=False, sheet_name="Premissas")

        fin_rows = [{"Chave": k, "Valor": v} for k, v in (fin or {}).items()]
        pd.DataFrame(fin_rows).to_excel(writer, index=False, sheet_name="Financiamento")

    return bio.getvalue()


def read_sheet(xls: pd.ExcelFile, name: str) -> pd.DataFrame:
    try:
        df = pd.read_excel(xls, sheet_name=name)
        if df is None:
            return pd.DataFrame()
        return df
    except Exception:
        return pd.DataFrame()


def kv_sheet_to_dict(df: pd.DataFrame) -> dict:
    if df.empty or "Chave" not in df.columns or "Valor" not in df.columns:
        return {}
    out: Dict[str, Any] = {}
    for _, r in df.iterrows():
        k = str(r["Chave"])
        v = r["Valor"]
        if "::" in k:
            base, sub = k.split("::", 1)
            out.setdefault(base, {})
            out[base][sub] = v
        else:
            out[k] = v
    return out


def import_excel_apply(uploaded, sc_name: str):
    try:
        xls = pd.ExcelFile(uploaded)
    except Exception as e:
        st.error(f"Não consegui ler o XLSX. Erro: {e}")
        return

    sc = get_scenario()

    capex_df = read_sheet(xls, "CAPEX")
    opex_outros_df = read_sheet(xls, "OPEX_Outros")
    func_df = read_sheet(xls, "Funcionarios")
    ins_df = read_sheet(xls, "Insumos")
    rh_df = read_sheet(xls, "Receitas_Header")
    rd_df = read_sheet(xls, "Receitas_Detalhe")
    emb_df = read_sheet(xls, "Embalagens")
    precos_df = read_sheet(xls, "Precos_SKU")

    mix_df = read_sheet(xls, "Mix_Demanda")
    prem_df = read_sheet(xls, "Premissas")
    fin_df = read_sheet(xls, "Financiamento")

    mix = kv_sheet_to_dict(mix_df) or sc.get("mix") or default_scenario()["mix"]
    prem = kv_sheet_to_dict(prem_df) or sc.get("premissas") or default_scenario()["premissas"]
    fin = kv_sheet_to_dict(fin_df) or sc.get("financiamento") or default_scenario()["financiamento"]

    if "Distribuição Embalado (%)" in mix and isinstance(mix["Distribuição Embalado (%)"], dict):
        mix["Distribuição Embalado (%)"] = {k: float(v) for k, v in mix["Distribuição Embalado (%)"].items()}

    capex_df = ensure_cols(
        capex_df if not capex_df.empty else _df(sc.get("capex_db")),
        {"Categoria": "", "Item": "", "Valor": 0.0, "Status": "Pendente"},
    )
    opex_outros_df = ensure_cols(
        opex_outros_df if not opex_outros_df.empty else _df(sc.get("opex_outros_db")),
        {"Descrição": "", "Valor": 0.0},
    )
    func_df = ensure_cols(
        func_df if not func_df.empty else _df(sc.get("funcionarios_db")),
        {"Nome": "", "Modalidade": "CLT", "Salário Bruto": 0.0, "Encargos CLT (%)": 70.0, "Considerar 13º": True, "Considerar Férias": True},
    )
    ins_df = ensure_cols(
        ins_df if not ins_df.empty else _df(sc.get("insumos_db")),
        {"Tipo": "", "Nome": "", "Unidade": "kg", "Custo": 0.0},
    )
    rh_df = ensure_cols(
        rh_df if not rh_df.empty else _df(sc.get("receitas_header")),
        {"ID": 1, "Nome": "", "Volume Batelada (L)": 500},
    )
    rd_df = ensure_cols(
        rd_df if not rd_df.empty else _df(sc.get("receitas_detalhe")),
        {"Receita_ID": 1, "Insumo": "", "Qtd": 0.0, "Custo_Unit": 0.0, "Custo_Total": 0.0},
    )
    emb_df = ensure_cols(
        emb_df if not emb_df.empty else _df(sc.get("embalagens_db")),
        {"Embalagem": "", "Volume (L)": 0.0, "Custo Unit (R$)": 0.0},
    )
    precos_df = ensure_cols(
        precos_df if not precos_df.empty else _df(sc.get("precos_sku")),
        {"SKU": "", "Canal": "Varejo", "Preço Unit (R$)": 0.0},
    )

    rd_df = _clean_numeric(rd_df, ["Qtd", "Custo_Unit"])
    rd_df["Custo_Total"] = (rd_df["Qtd"] * rd_df["Custo_Unit"]).astype(float)

    persist_dfs(sc_name, sc, capex_df, opex_outros_df, func_df, ins_df, rh_df, rd_df, emb_df, precos_df, mix, prem, fin)
    save_db(st.session_state.db)
    st.session_state["_import_done"] = True


# =========================================================
# SIDEBAR
# =========================================================
with st.sidebar:
    st.markdown(
        """
        <div class='brand-box'>
          <div class='brand-logo'>🍺</div>
          <div>
            <p class='brand-title'>BreweryPlanner</p>
            <small style='color:var(--muted);'>Planejamento cervejeiro</small>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.write("")

    scenarios = list(st.session_state.db["scenarios"].keys())
    selected = get_scenario_name()

    new_sel = st.selectbox(
        "Cenário", scenarios, index=scenarios.index(selected) if selected in scenarios else 0, key="scenario_select_clean"
    )
    if new_sel != selected:
        set_selected(new_sel)

    st.write("")
    new_name = st.text_input("Nome do novo cenário", value=st.session_state.get("new_scenario_name", ""), placeholder="Ex: Cenário otimista")
    st.session_state["new_scenario_name"] = new_name

    st.markdown("<div class='smallbtn'>", unsafe_allow_html=True)
    cA, cB, cC = st.columns(3, gap="small")

    with cA:
        if st.button("＋", help="Novo", use_container_width=True, key="btn_new"):
            base_name = new_name.strip() if new_name and new_name.strip() else "Novo cenário"
            name = base_name
            i = 1
            while name in st.session_state.db["scenarios"]:
                i += 1
                name = f"{base_name} {i}"
            st.session_state.db["scenarios"][name] = default_scenario()
            set_selected(name)
            save_db(st.session_state.db)
            st.session_state["new_scenario_name"] = ""
            st.rerun()

    with cB:
        if st.button("⎘", help="Duplicar", use_container_width=True, key="btn_dup"):
            cur = get_scenario_name()
            base_name = f"{cur} (cópia)"
            name = base_name
            i = 1
            while name in st.session_state.db["scenarios"]:
                i += 1
                name = f"{base_name} {i}"
            st.session_state.db["scenarios"][name] = deepcopy(st.session_state.db["scenarios"][cur])
            set_selected(name)
            save_db(st.session_state.db)
            st.rerun()

    with cC:
        if st.button("🗑", help="Excluir", use_container_width=True, key="btn_del"):
            cur = get_scenario_name()
            if len(st.session_state.db["scenarios"]) <= 1:
                st.warning("Você precisa manter pelo menos 1 cenário.")
            else:
                st.session_state.db["scenarios"].pop(cur, None)
                set_selected(list(st.session_state.db["scenarios"].keys())[0])
                save_db(st.session_state.db)
                st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)

    st.write("")
    if st.button("💾 Salvar alterações", type="primary", use_container_width=True, key="btn_save_sidebar"):
        save_db(st.session_state.db)

    st.write("")
    st.markdown("<hr/>", unsafe_allow_html=True)

    st.markdown(
        "<div class='helper-card'><p class='helper-title'>Premissas</p><p class='helper-sub'>Custos indiretos e impostos</p></div>",
        unsafe_allow_html=True,
    )

    sc_name = get_scenario_name()
    sc = get_scenario()
    capex_df, opex_outros_df, func_df, ins_df, rh_df, rd_df, emb_df, precos_df, mix, prem, fin = scenario_dfs(sc)

    gip_q = st.number_input("Químicos (R$/L)", 0.0, 10.0, float(prem.get("GIP Químicos (R$/L)", 0.25)), step=0.05, key="prem_gip_q")
    gip_e = st.number_input("Energia (R$/L)", 0.0, 10.0, float(prem.get("GIP Energia (R$/L)", 0.35)), step=0.05, key="prem_gip_e")
    gip_a = st.number_input("Água (R$/L)", 0.0, 10.0, float(prem.get("GIP Água (R$/L)", 0.15)), step=0.05, key="prem_gip_a")
    gip_c = st.number_input("CO2 (R$/L)", 0.0, 10.0, float(prem.get("GIP CO2 (R$/L)", 0.15)), step=0.05, key="prem_gip_c")
    gip_total = gip_q + gip_e + gip_a + gip_c
    st.caption(f"Indiretos total: **{brl(gip_total)} / L**")

    imp = st.slider("Impostos s/ venda (%)", 0.0, 30.0, float(prem.get("Impostos s/ venda (%)", 10.0)), step=0.5, key="prem_imp")
    giro = st.number_input("Capital de giro (meses)", 1, 24, int(prem.get("Capital de giro (meses)", 6)), key="prem_giro")

    prem["GIP Químicos (R$/L)"] = float(gip_q)
    prem["GIP Energia (R$/L)"] = float(gip_e)
    prem["GIP Água (R$/L)"] = float(gip_a)
    prem["GIP CO2 (R$/L)"] = float(gip_c)
    prem["Impostos s/ venda (%)"] = float(imp)
    prem["Capital de giro (meses)"] = int(giro)

    st.write("")
    st.markdown("<hr/>", unsafe_allow_html=True)
    st.markdown(
        "<div class='helper-card'><p class='helper-title'>Import / Export (Excel)</p><p class='helper-sub'>Exporta o template, edita no Excel e reimporta</p></div>",
        unsafe_allow_html=True,
    )

    excel_bytes = scenario_to_excel_bytes(sc_name, sc)
    st.download_button(
        "⬇️ Exportar planilha (padrão)",
        data=excel_bytes,
        file_name=f"BreweryPlanner_{sc_name}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
        key="dl_excel",
    )

    st.write("")
    st.caption("Importação substitui os dados do cenário selecionado.")
    uploader_key = st.session_state.get("_uploader_key", 1)
    up = st.file_uploader("Importar planilha (.xlsx)", type=["xlsx"], key=f"uploader_{uploader_key}")

    apply_col1, apply_col2 = st.columns([1, 1], gap="small")
    with apply_col1:
        can_apply = up is not None
        if st.button("Importar", type="primary", disabled=not can_apply, use_container_width=True, key="btn_apply_import"):
            import_excel_apply(up, sc_name)
            st.session_state["_uploader_key"] = uploader_key + 1
            st.rerun()

    with apply_col2:
        if st.button("Cancelar", disabled=not can_apply, use_container_width=True, key="btn_cancel_import"):
            st.session_state["_uploader_key"] = uploader_key + 1
            st.rerun()

    if st.session_state.get("_import_done"):
        safe_toast("Arquivo importado com sucesso!", "✅")
        st.session_state["_import_done"] = False


# =========================================================
# MAIN TABS
# =========================================================
tabs = st.tabs(
    [
        "Visão Geral",
        "CAPEX",
        "OPEX & Pessoas",
        "Insumos",
        "Receitas",
        "Embalagens",
        "Preços (SKU)",
        "Mix & Demanda",
        "Financeiro (Payback)",
    ]
)

# Recarrega dfs após sidebar premissas
sc_name = get_scenario_name()
sc = get_scenario()
capex_df, opex_outros_df, func_df, ins_df, rh_df, rd_df, emb_df, precos_df, mix, prem, fin = scenario_dfs(sc)


# =========================================================
# TAB 0 - VISÃO GERAL
# =========================================================
with tabs[0]:
    st.title("Dashboard Executivo")

    folha_calc = calc_folha_mensal(func_df)
    folha_total = float(folha_calc["Custo Mensal (R$)"].sum()) if not folha_calc.empty else 0.0
    opex_outros_total = float(opex_outros_df["Valor"].sum()) if not opex_outros_df.empty else 0.0
    opex_total = folha_total + opex_outros_total

    capex_total = float(capex_df["Valor"].sum()) if not capex_df.empty else 0.0
    giro_meses = int(prem.get("Capital de giro (meses)", 6))
    investimento_total = capex_total + (opex_total * giro_meses)

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("CAPEX (investimento)", brl(capex_total))
    k2.metric("OPEX mensal (total)", brl(opex_total))
    k3.metric("Capital de giro", f"{giro_meses} meses")
    k4.metric("Capital total necessário", brl(investimento_total))

    st.markdown("<hr/>", unsafe_allow_html=True)

    c1, c2 = st.columns([1.2, 1.0], gap="large")

    with c1:
        st.subheader("Composição do CAPEX por categoria")
        if capex_df.empty:
            st.info("Cadastre itens no CAPEX para visualizar gráficos.")
        else:
            df_cap_cat = capex_df.groupby("Categoria", as_index=False)["Valor"].sum()
            fig = px.bar(df_cap_cat, x="Categoria", y="Valor", text_auto=True)
            fig.update_layout(height=360, xaxis_title=None, yaxis_title=None, showlegend=False)
            st.plotly_chart(ensure_white_fig(fig), use_container_width=True)

    with c2:
        st.subheader("Status do CAPEX (percentual)")
        if capex_df.empty:
            st.info("Sem dados de CAPEX.")
        else:
            df_st = capex_df.copy()
            df_st["Status"] = df_st["Status"].fillna("Pendente")
            order = STATUS_OPTIONS
            df_st["Status"] = pd.Categorical(df_st["Status"], categories=order, ordered=True)
            s = df_st.groupby("Status", as_index=False)["Valor"].sum().dropna()
            if s.empty:
                st.info("Sem status definidos.")
            else:
                fig2 = px.pie(s, names="Status", values="Valor", hole=0.55)
                fig2.update_layout(height=360, legend_title_text="")
                st.plotly_chart(ensure_white_fig(fig2), use_container_width=True)

    st.subheader("Custos fixos - OPEX")
    if opex_total <= 0:
        st.info("Cadastre OPEX e/ou funcionários para ver o Pareto.")
    else:
        pareto = pd.concat(
            [
                opex_outros_df.rename(columns={"Descrição": "Item"})[["Item", "Valor"]],
                folha_calc.rename(columns={"Nome": "Item", "Custo Mensal (R$)": "Valor"})[["Item", "Valor"]],
            ],
            ignore_index=True,
        )
        pareto = pareto.sort_values("Valor", ascending=False)
        figp = px.bar(pareto, x="Valor", y="Item", orientation="h", text_auto=True)
        figp.update_layout(height=420, xaxis_title=None, yaxis_title=None)
        st.plotly_chart(ensure_white_fig(figp), use_container_width=True)


# =========================================================
# TAB 1 - CAPEX
# =========================================================
with tabs[1]:
    st.title("CAPEX (Equipamentos e Implantação)")

    colf1, colf2 = st.columns([1.1, 1.0], gap="large")
    with colf1:
        cats = ["Todas"] + sorted([c for c in capex_df["Categoria"].dropna().unique().tolist() if str(c).strip() != ""])
        cat = st.radio("Filtrar categoria", cats, horizontal=True)
    with colf2:
        status_list = ["Todos"] + STATUS_OPTIONS
        st_sel = st.radio("Filtrar status", status_list, horizontal=True)

    df_show = capex_df.copy()
    if cat != "Todas":
        df_show = df_show[df_show["Categoria"] == cat]
    if st_sel != "Todos":
        df_show = df_show[df_show["Status"] == st_sel]

    edited = st.data_editor(
        df_show,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "Valor": st.column_config.NumberColumn("Valor (R$)", format="R$ %.2f"),
            "Status": st.column_config.SelectboxColumn("Status", options=STATUS_OPTIONS),
        },
        key="capex_editor",
    )

    if cat == "Todas" and st_sel == "Todos":
        capex_df = edited.copy()
    else:
        capex_df = _merge_filtered(capex_df, edited, ["Categoria", "Item"])

    st.caption(f"Total CAPEX (visível): **{brl(float(edited['Valor'].sum()) if not edited.empty else 0.0)}**")


# =========================================================
# TAB 2 - OPEX & PESSOAS
# =========================================================
with tabs[2]:
    st.title("OPEX (Custos fixos mensais) & Pessoas")

    st.subheader("Funcionários (CLT / PJ)")
    st.caption("CLT: custo mensal = salário*(1+encargos) + provisão 13º + provisão férias (1 + 1/3). PJ: custo = valor bruto.")

    func_calc = calc_folha_mensal(func_df)
    func_calc_display = func_calc.copy()

    edited_func = st.data_editor(
        func_calc_display,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "Modalidade": st.column_config.SelectboxColumn("Modalidade", options=["CLT", "PJ"]),
            "Salário Bruto": st.column_config.NumberColumn("Salário/Valor (R$)", format="R$ %.2f"),
            "Encargos CLT (%)": st.column_config.NumberColumn("Encargos CLT (%)", format="%.1f"),
            "Considerar 13º": st.column_config.CheckboxColumn("13º"),
            "Considerar Férias": st.column_config.CheckboxColumn("Férias"),
            "Custo Mensal (R$)": st.column_config.NumberColumn("Custo Mensal (R$)", format="R$ %.2f", disabled=True),
        },
        key="func_editor",
    )

    func_df = edited_func.drop(columns=["Custo Mensal (R$)"], errors="ignore").copy()
    func_calc = calc_folha_mensal(func_df)
    folha_total = float(func_calc["Custo Mensal (R$)"].sum()) if not func_calc.empty else 0.0

    st.markdown("")
    m1, m2 = st.columns(2)
    m1.metric("Custo mensal da folha", brl(folha_total))
    m2.metric("Qtd. colaboradores", int(len(func_df)))

    st.markdown("<hr/>", unsafe_allow_html=True)

    st.subheader("Outros custos fixos (mensais)")
    edited_opex = st.data_editor(
        opex_outros_df,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={"Valor": st.column_config.NumberColumn("Valor (R$)", format="R$ %.2f")},
        key="opex_outros_editor",
    )
    opex_outros_df = edited_opex.copy()

    opex_total = float(opex_outros_df["Valor"].sum()) + folha_total
    st.metric("OPEX mensal total", brl(opex_total), delta="Folha + Outros")


# =========================================================
# TAB 3 - INSUMOS
# =========================================================
with tabs[3]:
    st.title("Catálogo de Insumos")
    st.caption("Cadastre maltes, lúpulos, leveduras, adjuntos e outros itens com custo unitário.")

    edited_ins = st.data_editor(
        ins_df,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "Custo": st.column_config.NumberColumn("Custo (R$)", format="R$ %.2f"),
            "Unidade": st.column_config.SelectboxColumn("Unidade", options=["kg", "g", "pct", "un", "L"]),
        },
        key="ins_editor",
    )
    ins_df = edited_ins.copy()


# =========================================================
# TAB 4 - RECEITAS
# =========================================================
with tabs[4]:
    st.title("Receitas (Cadastro + Custo por litro)")

    col_left, col_right = st.columns([1.05, 1.95], gap="large")

    with col_left:
        st.subheader("Receitas")
        with st.expander("➕ Criar nova receita", expanded=False):
            with st.form("form_new_recipe"):
                n = st.text_input("Nome da receita")
                v = st.number_input("Volume da batelada (L)", min_value=50, max_value=100000, value=500, step=50)
                submit = st.form_submit_button("Criar")
                if submit:
                    if str(n).strip() == "":
                        st.warning("Informe um nome.")
                    else:
                        new_id = int(rh_df["ID"].max() + 1) if not rh_df.empty else 1
                        rh_df = pd.concat(
                            [rh_df, pd.DataFrame([[new_id, n, float(v)]], columns=["ID", "Nome", "Volume Batelada (L)"])],
                            ignore_index=True,
                        )
                        safe_toast("Receita criada!", "✅")
                        st.rerun()

        if rh_df.empty:
            st.info("Nenhuma receita cadastrada.")
            selected_recipe = None
        else:
            selected_recipe = st.selectbox("Selecionar", rh_df["Nome"].tolist(), key="sel_recipe")
            row = rh_df[rh_df["Nome"] == selected_recipe].iloc[0]
            rid = int(row["ID"])
            rvol = float(row["Volume Batelada (L)"])

            st.caption(f"ID: {rid} • Volume base: {rvol:.0f} L")

            if st.button("🗑️ Excluir receita", key="btn_del_recipe"):
                rh_df = rh_df[rh_df["ID"] != rid].copy()
                rd_df = rd_df[rd_df["Receita_ID"] != rid].copy()
                if mix.get("Receita Base (para custo)") == selected_recipe:
                    mix["Receita Base (para custo)"] = rh_df["Nome"].iloc[0] if not rh_df.empty else ""
                safe_toast("Receita excluída!", "🗑️")
                st.rerun()

    with col_right:
        st.subheader("Composição de insumos")
        if selected_recipe is None:
            st.info("Crie ou selecione uma receita para editar a composição.")
        else:
            row = rh_df[rh_df["Nome"] == selected_recipe].iloc[0]
            rid = int(row["ID"])
            rvol = float(row["Volume Batelada (L)"])

            top1, top2, top3 = st.columns([2.0, 1.0, 1.0], gap="small")
            with top1:
                if ins_df.empty:
                    st.warning("Cadastre insumos primeiro.")
                    ins_sel = None
                else:
                    ins_sel = st.selectbox("Insumo", ins_df["Nome"].tolist(), key="ins_sel_recipe")
            with top2:
                qtd = st.number_input("Quantidade", min_value=0.0, value=0.0, step=0.1, key="qtd_recipe")
            with top3:
                custo_unit = 0.0
                if ins_sel is not None and not ins_df.empty:
                    custo_unit = float(ins_df[ins_df["Nome"] == ins_sel]["Custo"].iloc[0])
                st.caption(f"Custo unit: **{brl(custo_unit)}**")
                if st.button("Adicionar", type="primary", key="btn_add_ing"):
                    if ins_sel:
                        rd_df = pd.concat(
                            [
                                rd_df,
                                pd.DataFrame(
                                    [
                                        {
                                            "Receita_ID": rid,
                                            "Insumo": ins_sel,
                                            "Qtd": float(qtd),
                                            "Custo_Unit": float(custo_unit),
                                            "Custo_Total": float(qtd) * float(custo_unit),
                                        }
                                    ]
                                ),
                            ],
                            ignore_index=True,
                        )
                        safe_toast("Item adicionado!", "✅")
                        st.rerun()

            st.markdown("")
            itens = rd_df[rd_df["Receita_ID"] == rid].copy().reset_index(drop=True)
            if itens.empty:
                st.info("Sem ingredientes ainda.")
            else:
                edited_itens = st.data_editor(
                    itens[["Insumo", "Qtd", "Custo_Unit"]],
                    num_rows="dynamic",
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Insumo": st.column_config.TextColumn(disabled=True),
                        "Qtd": st.column_config.NumberColumn("Qtd", min_value=0.0),
                        "Custo_Unit": st.column_config.NumberColumn("Custo Unit (R$)", format="R$ %.2f", disabled=True),
                    },
                    key="recipe_items_editor",
                )
                edited_itens["Receita_ID"] = rid
                edited_itens["Custo_Total"] = edited_itens["Qtd"] * edited_itens["Custo_Unit"]

                rd_df = pd.concat([rd_df[rd_df["Receita_ID"] != rid], edited_itens], ignore_index=True)

                custo_batelada = float(edited_itens["Custo_Total"].sum())
                custo_l = (custo_batelada / rvol) if rvol > 0 else 0.0
                custo_final_l = custo_l + calc_gip_total(prem)

                a, b, c = st.columns(3)
                a.metric("Custo batelada", brl(custo_batelada))
                b.metric("Matéria-prima / L", brl(custo_l))
                c.metric("Custo final / L", brl(custo_final_l), delta="MP + indiretos")


# =========================================================
# TAB 5 - EMBALAGENS
# =========================================================
with tabs[5]:
    st.title("Embalagens")
    st.caption("Cadastre volumes e custos unitários. Barris podem ter custo unitário 0 se forem ativos (CAPEX).")

    edited_emb = st.data_editor(
        emb_df,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "Volume (L)": st.column_config.NumberColumn("Volume (L)", format="%.3f"),
            "Custo Unit (R$)": st.column_config.NumberColumn("Custo Unit (R$)", format="R$ %.2f"),
        },
        key="emb_editor",
    )
    emb_df = edited_emb.copy()

    st.markdown("<hr/>", unsafe_allow_html=True)
    st.subheader("Taproom (copo)")
    st.caption("Defina o tamanho do copo e o custo do copo. O preço do copo fica na aba Preços (SKU).")

    copo_vol_l, copo_custo_ref = get_pack_cost(emb_df, "Copo Taproom")
    copo_vol_ml = st.slider("Volume do copo (ml)", 200, 800, int(copo_vol_l * 1000) if copo_vol_l > 0 else 473, step=10)
    copo_custo = st.number_input("Custo do copo (R$)", 0.0, 10.0, float(copo_custo_ref if copo_custo_ref > 0 else 0.25), step=0.05)

    if "Copo Taproom" in emb_df["Embalagem"].tolist():
        emb_df.loc[emb_df["Embalagem"] == "Copo Taproom", "Volume (L)"] = copo_vol_ml / 1000.0
        emb_df.loc[emb_df["Embalagem"] == "Copo Taproom", "Custo Unit (R$)"] = float(copo_custo)
    else:
        emb_df = pd.concat(
            [emb_df, pd.DataFrame([{"Embalagem": "Copo Taproom", "Volume (L)": copo_vol_ml / 1000.0, "Custo Unit (R$)": float(copo_custo)}])],
            ignore_index=True,
        )


# =========================================================
# TAB 6 - PREÇOS
# =========================================================
with tabs[6]:
    st.title("Preços (SKU)")
    st.caption("Taproom: preço do copo. Varejo: preço por unidade (embalagens) e chope por litro.")

    for sku, canal in SKUS_REQUIRED:
        if precos_df[(precos_df["SKU"] == sku) & (precos_df["Canal"] == canal)].empty:
            precos_df = pd.concat(
                [precos_df, pd.DataFrame([[sku, canal, 0.0]], columns=["SKU", "Canal", "Preço Unit (R$)"])]
            ).reset_index(drop=True)

    edited_precos = st.data_editor(
        precos_df,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "Canal": st.column_config.SelectboxColumn("Canal", options=["Taproom", "Varejo"]),
            "Preço Unit (R$)": st.column_config.NumberColumn("Preço (R$)", format="R$ %.2f"),
        },
        key="precos_editor",
    )
    precos_df = edited_precos.copy()


# =========================================================
# TAB 7 - MIX & DEMANDA
# =========================================================
with tabs[7]:
    st.title("Mix & Demanda (mês típico)")
    st.caption("Defina volume mensal e divisão entre Taproom, Varejo chope e Varejo embalado.")

    c1, c2, c3 = st.columns(3, gap="large")
    with c1:
        vol_mes = st.slider("Volume vendido (L/mês)", 100, 20000, int(mix.get("Volume Vendido (L/mês)", 2000)), step=50)
    with c2:
        mix_tap = st.slider("Taproom (%)", 0, 100, int(mix.get("Mix Taproom (%)", 30)), step=1)
    with c3:
        mix_varejo_chope = st.slider("Varejo chope (%)", 0, 100, int(mix.get("Mix Varejo Chope (%)", 25)), step=1)

    rest = max(0, 100 - mix_tap - mix_varejo_chope)
    mix_varejo_emb = st.slider("Varejo embalado (%)", 0, 100, int(mix.get("Mix Varejo Embalado (%)", rest)), step=1)

    ssum = mix_tap + mix_varejo_chope + mix_varejo_emb
    if ssum != 100:
        mix_varejo_emb = max(0, 100 - mix_tap - mix_varejo_chope)

    if not rh_df.empty:
        receita_base = st.selectbox(
            "Receita base (para custo por litro)",
            rh_df["Nome"].tolist(),
            index=rh_df["Nome"].tolist().index(mix.get("Receita Base (para custo)")) if mix.get("Receita Base (para custo)") in rh_df["Nome"].tolist() else 0,
        )
    else:
        receita_base = ""

    st.markdown("<hr/>", unsafe_allow_html=True)
    st.subheader("Distribuição do Varejo Embalado (%)")
    st.caption("A soma ideal é 100%. Se não fechar 100%, o app normaliza automaticamente no cálculo.")

    eligible = [e for e in emb_df["Embalagem"].tolist() if e not in EMB_EXCLUDE_DIST]
    current_dist = mix.get("Distribuição Embalado (%)", {}) or {}
    for e in eligible:
        current_dist.setdefault(e, 0.0)

    dist_df = pd.DataFrame([[k, float(v)] for k, v in current_dist.items() if k in eligible], columns=["Embalagem", "Percentual (%)"])
    dist_df = dist_df.sort_values("Embalagem")

    edited_dist = st.data_editor(
        dist_df,
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        column_config={"Percentual (%)": st.column_config.NumberColumn("Percentual (%)", min_value=0.0, max_value=100.0, step=1.0)},
        key="dist_editor",
    )

    dist_out = {r["Embalagem"]: float(r["Percentual (%)"]) for _, r in edited_dist.iterrows()}

    mix["Volume Vendido (L/mês)"] = float(vol_mes)
    mix["Mix Taproom (%)"] = float(mix_tap)
    mix["Mix Varejo Chope (%)"] = float(mix_varejo_chope)
    mix["Mix Varejo Embalado (%)"] = float(mix_varejo_emb)
    mix["Distribuição Embalado (%)"] = dist_out
    mix["Receita Base (para custo)"] = receita_base

    dre_preview = compute_monthly_dre(
        volume_mes_l=float(vol_mes),
        mix_taproom=float(mix_tap),
        mix_varejo_chope=float(mix_varejo_chope),
        mix_varejo_emb=float(mix_varejo_emb),
        dist_emb_percent=dist_out,
        receita_base_nome=receita_base,
        receitas_header_df=rh_df,
        receitas_det_df=rd_df,
        emb_df=emb_df,
        precos_df=precos_df,
        prem=prem,
    )
    st.markdown("<hr/>", unsafe_allow_html=True)
    a, b, c, d = st.columns(4)
    a.metric("Receita bruta", brl(dre_preview["Receita bruta"]))
    b.metric("Impostos", brl(dre_preview["Impostos"]))
    c.metric("CMV total", brl(dre_preview["CMV total"]))
    d.metric("Margem contrib.", brl(dre_preview["Margem de contribuição"]))


# =========================================================
# TAB 8 - FINANCEIRO (PAYBACK)
# =========================================================
with tabs[8]:
    st.title("Financeiro (Payback & Retorno)")
    st.caption("Payback simples e com dívida. Na opção com dívida, a parcela mensal reduz o caixa disponível.")

    folha_calc = calc_folha_mensal(func_df)
    folha_total = float(folha_calc["Custo Mensal (R$)"].sum()) if not folha_calc.empty else 0.0
    opex_outros_total = float(opex_outros_df["Valor"].sum()) if not opex_outros_df.empty else 0.0
    opex_total = folha_total + opex_outros_total

    capex_total = float(capex_df["Valor"].sum()) if not capex_df.empty else 0.0
    giro_meses = int(prem.get("Capital de giro (meses)", 6))
    invest_inicial = capex_total + (opex_total * giro_meses)

    st.subheader("Simulação (mês típico) — dinâmica")
    colS1, colS2, colS3 = st.columns(3, gap="large")

    with colS1:
        vol_mes = st.slider("Volume vendido (L/mês)", 100, 20000, int(mix.get("Volume Vendido (L/mês)", 2000)), step=50, key="fin_vol")
    with colS2:
        mix_tap = st.slider("Taproom (%)", 0, 100, int(mix.get("Mix Taproom (%)", 30)), step=1, key="fin_mix_tap")
    with colS3:
        mix_vch = st.slider("Varejo chope (%)", 0, 100, int(mix.get("Mix Varejo Chope (%)", 25)), step=1, key="fin_mix_vch")

    mix_vemb = max(0, 100 - mix_tap - mix_vch)
    st.caption(f"Varejo embalado calculado automaticamente: **{mix_vemb}%**")

    eligible = [e for e in emb_df["Embalagem"].tolist() if e not in EMB_EXCLUDE_DIST]
    current_dist = mix.get("Distribuição Embalado (%)", {}) or {}
    for e in eligible:
        current_dist.setdefault(e, 0.0)
    dist_df = pd.DataFrame([[k, float(v)] for k, v in current_dist.items() if k in eligible], columns=["Embalagem", "Percentual (%)"])

    st.markdown("")
    st.markdown("**Distribuição do embalado (%)** (dinâmica)")
    edited_dist = st.data_editor(
        dist_df.sort_values("Embalagem"),
        use_container_width=True,
        hide_index=True,
        column_config={"Percentual (%)": st.column_config.NumberColumn("Percentual (%)", min_value=0.0, max_value=100.0, step=1.0)},
        key="fin_dist",
    )
    dist_out = {r["Embalagem"]: float(r["Percentual (%)"]) for _, r in edited_dist.iterrows()}

    if not rh_df.empty:
        receita_base = st.selectbox(
            "Receita base (para custo por litro)",
            rh_df["Nome"].tolist(),
            index=rh_df["Nome"].tolist().index(mix.get("Receita Base (para custo)")) if mix.get("Receita Base (para custo)") in rh_df["Nome"].tolist() else 0,
            key="fin_receita_base",
        )
    else:
        receita_base = ""

    dre = compute_monthly_dre(
        volume_mes_l=float(vol_mes),
        mix_taproom=float(mix_tap),
        mix_varejo_chope=float(mix_vch),
        mix_varejo_emb=float(mix_vemb),
        dist_emb_percent=dist_out,
        receita_base_nome=receita_base,
        receitas_header_df=rh_df,
        receitas_det_df=rd_df,
        emb_df=emb_df,
        precos_df=precos_df,
        prem=prem,
    )

    lucro_operacional = float(dre["Margem de contribuição"] - opex_total)

    st.markdown("<hr/>", unsafe_allow_html=True)

    vis = st.radio("Visualização", ["Payback simples", "Payback com dívida"], horizontal=True, key="pay_vis")

    if vis == "Payback com dívida":
        st.subheader("Financiamento (robusto e interativo)")

        colF1, colF2, colF3, colF4 = st.columns(4, gap="large")
        with colF1:
            pct_fin = st.slider("Percentual financiado (%)", 0.0, 100.0, float(fin.get("Percentual financiado (%)", 60.0)), step=1.0, key="fin_pct")
        with colF2:
            juros_aa = st.slider("Taxa de juros a.a. (%)", 0.0, 60.0, float(fin.get("Taxa juros a.a. (%)", 18.0)), step=0.5, key="fin_juros")
        with colF3:
            prazo = st.slider("Prazo (meses)", 1, 180, int(fin.get("Prazo (meses)", 48)), step=1, key="fin_prazo")
        with colF4:
            carencia = st.slider("Carência (meses)", 0, 24, int(fin.get("Carência (meses)", 0)), step=1, key="fin_carencia")

        valor_fin = invest_inicial * (pct_fin / 100.0)
        i_m = (juros_aa / 100.0) / 12.0
        parcela = pmt_price(valor_fin, i_m, max(1, prazo - carencia))
        juros_only = valor_fin * i_m

        st.caption(f"Valor financiado: **{brl(valor_fin)}** • Taxa mês: **{i_m * 100:.2f}%**")
        st.info("Carência (neste modelo): durante a carência paga apenas juros; depois entra parcela Price.")

        st.metric("Parcela estimada (após carência)", brl(parcela))
    else:
        pct_fin = 0.0
        juros_aa = 0.0
        prazo = 0
        carencia = 0
        valor_fin = 0.0
        parcela = 0.0
        juros_only = 0.0

    st.markdown("<hr/>", unsafe_allow_html=True)
    st.subheader("Payback visual (até 7 anos)")

    if vis == "Payback simples":
        monthly_cash = lucro_operacional
        df_pb, m_pay = build_payback_series(invest_inicial, monthly_cash, months=84)
        titulo = "Payback (Simples)"
    else:
        saldo = [-invest_inicial]
        m_pay = None
        acc = -invest_inicial
        for m in range(1, 85):
            pay = juros_only if m <= carencia else parcela
            acc += (lucro_operacional - pay)
            saldo.append(acc)
            if acc >= 0 and m_pay is None:
                m_pay = m
        df_pb = pd.DataFrame({"Mês": list(range(0, 85)), "Saldo": saldo})
        titulo = "Payback (Com dívida)"

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df_pb["Mês"],
            y=df_pb["Saldo"],
            mode="lines",
            fill="tozeroy",
            name="Saldo acumulado",
            line=dict(width=3),
        )
    )
    fig.add_hline(y=0, line_width=1, line_color="rgba(17,24,39,.45)")

    if m_pay is not None:
        fig.add_vline(x=m_pay, line_dash="dash", line_width=2, line_color="rgba(10,132,255,.75)")
        fig.add_annotation(
            x=m_pay,
            y=0,
            text=f"Payback: {m_pay} meses ({m_pay/12:.1f} anos)",
            showarrow=True,
            arrowhead=2,
            yshift=14,
        )
        st.success(f"Payback: **{m_pay} meses** (~{m_pay/12:.1f} anos).")
    else:
        st.warning("Neste cenário, o investimento não se paga em 7 anos.")

    fig.update_layout(
        title=titulo,
        height=480,
        xaxis_title="Meses",
        yaxis_title="Saldo acumulado (R$)",
        margin=dict(l=10, r=10, t=60, b=10),
    )
    st.plotly_chart(ensure_white_fig(fig), use_container_width=True)

    st.markdown("<hr/>", unsafe_allow_html=True)
    st.subheader("Resumo do resultado operacional (mês típico)")

    r1, r2, r3, r4 = st.columns(4, gap="large")
    r1.metric("Receita bruta", brl(dre["Receita bruta"]))
    r2.metric("Receita líquida", brl(dre["Receita bruta"] - dre["Impostos"]))
    r3.metric("Margem de contribuição", brl(dre["Margem de contribuição"]))
    r4.metric("Lucro operacional", brl(lucro_operacional), delta="Margem - OPEX")

    st.caption(
        f"Taproom: {dre['Taproom (copos/mês)']:.0f} copos/mês • "
        f"Varejo chope: {dre['Varejo chope (L/mês)']:.0f} L/mês • "
        f"Varejo embalado: {dre['Varejo embalado (L/mês)']:.0f} L/mês"
    )


# =========================================================
# PERSIST SCENARIO (sempre que navegar)
# =========================================================
persist_dfs(sc_name, sc, capex_df, opex_outros_df, func_df, ins_df, rh_df, rd_df, emb_df, precos_df, mix, prem, fin)
