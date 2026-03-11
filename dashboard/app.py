"""
dashboard/app.py
────────────────
CPR Strategy Dashboard — 4 tabs, major.minor version system.

Run from project root:
    streamlit run dashboard/app.py
"""

import sys, warnings, io, itertools
warnings.filterwarnings("ignore")
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

from core.journal import load_journal, list_versions, load_metadata
from strategy import (
    load_strategy, all_versions,
    major_versions, minor_versions_of, load_major_base,
)

# ─────────────────────────────────────────────────────────────────────────────
#  Design tokens
# ─────────────────────────────────────────────────────────────────────────────
C = dict(
    bg="#080c14", surface="#0f1624", card="#141d2e",
    border="#1e2d45", grid="#1a2535", text="#c8d4e8",
    muted="#5a7091", green="#00d68f", red="#ff4d6d",
    blue="#3d9bff", yellow="#ffc145", purple="#b57aff",
    orange="#ff8c42", teal="#00b4d8", cyan="#22d3ee",
)

MINOR_PALETTE = [
    C["blue"], C["green"], C["yellow"],
    C["purple"], C["orange"], C["teal"], C["cyan"], C["red"],
]

def version_color(vid: str) -> str:
    try:
        return MINOR_PALETTE[(int(vid.split(".")[1]) - 1) % len(MINOR_PALETTE)]
    except Exception:
        return C["blue"]

PLOTLY_BASE = dict(
    paper_bgcolor=C["bg"], plot_bgcolor=C["surface"],
    font=dict(color=C["text"],
              family="'JetBrains Mono','Fira Code',monospace", size=12),
    xaxis=dict(gridcolor=C["grid"], zerolinecolor=C["grid"],
               linecolor=C["border"], tickcolor=C["muted"]),
    yaxis=dict(gridcolor=C["grid"], zerolinecolor=C["grid"],
               linecolor=C["border"], tickcolor=C["muted"]),
    margin=dict(l=48, r=24, t=44, b=40),
    legend=dict(bgcolor="rgba(0,0,0,0)", bordercolor=C["border"]),
)

st.set_page_config(
    page_title="CPR Strategy",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;600;700&family=Space+Grotesk:wght@400;600;700&display=swap');
html,body,[class*="css"]{{background:{C["bg"]};color:{C["text"]};font-family:'Space Grotesk',sans-serif}}
.stApp{{background:{C["bg"]}}}
section[data-testid="stSidebar"]{{background:{C["surface"]} !important;border-right:1px solid {C["border"]}}}
.stTabs [data-baseweb="tab-list"]{{background:{C["surface"]};border-bottom:1px solid {C["border"]};gap:0}}
.stTabs [data-baseweb="tab"]{{background:transparent;color:{C["muted"]};font-family:'JetBrains Mono',monospace;font-size:12px;letter-spacing:.06em;padding:10px 20px;border-bottom:2px solid transparent}}
.stTabs [aria-selected="true"]{{color:{C["blue"]} !important;border-bottom:2px solid {C["blue"]} !important;background:transparent !important}}
.kpi{{background:{C["card"]};border:1px solid {C["border"]};border-radius:8px;padding:14px 16px}}
.kpi-label{{font-family:'JetBrains Mono',monospace;font-size:10px;font-weight:600;letter-spacing:.12em;text-transform:uppercase;color:{C["muted"]};margin-bottom:6px}}
.kpi-value{{font-family:'JetBrains Mono',monospace;font-size:22px;font-weight:700;color:{C["text"]};line-height:1}}
.kpi-pos{{color:{C["green"]} !important}}
.kpi-neg{{color:{C["red"]} !important}}
.kpi-sub{{font-size:11px;color:{C["muted"]};margin-top:4px}}
.section-hdr{{font-family:'JetBrains Mono',monospace;font-size:10px;font-weight:700;letter-spacing:.16em;text-transform:uppercase;color:{C["muted"]};margin:20px 0 10px;padding-bottom:6px;border-bottom:1px solid {C["border"]}}}
.change-item{{padding:4px 0 4px 12px;border-left:3px solid {C["yellow"]};margin:4px 0;font-size:13px;color:{C["text"]}}}
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_trades(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty: return df
    return df[df["entry_type"].isin(["ORIGINAL","RE-ENTRY"])].copy()

def to_num(s): return pd.to_numeric(s, errors="coerce")

def hex_to_rgba(hex_color: str, alpha: float = 0.1) -> str:
    """Convert hex color to rgba string with transparency."""
    hex_color = hex_color.lstrip("#")
    r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"

def compute_metrics(trades) -> dict:
    if trades is None or trades.empty: return {}
    pnl   = to_num(trades["total_pnl_pts"]).dropna()
    wins  = trades[trades["trade_outcome"].str.startswith("WIN", na=False)]
    loss  = trades[trades["trade_outcome"] == "LOSS"]
    full  = trades[trades["trade_outcome"] == "WIN-FULL"]
    part  = trades[trades["trade_outcome"] == "WIN-PARTIAL"]
    n     = len(trades)
    wr    = len(wins)/n*100 if n else 0
    aw    = float(pnl[pnl>0].mean()) if (pnl>0).any() else 0
    al    = float(pnl[pnl<0].mean()) if (pnl<0).any() else 0
    exp   = (wr/100*aw) + ((1-wr/100)*al)
    gp    = float(pnl[pnl>0].sum())
    gl    = float(abs(pnl[pnl<0].sum()))
    pf    = round(gp/gl, 2) if gl > 0 else "∞"
    cum   = pnl.cumsum()
    mdd   = float((cum.cummax()-cum).max())
    oc    = trades["trade_outcome"].apply(lambda x: 1 if str(x).startswith("WIN") else -1)
    mxw   = max((sum(1 for _ in g) for k,g in itertools.groupby(oc) if k==1), default=0)
    mxl   = max((sum(1 for _ in g) for k,g in itertools.groupby(oc) if k==-1), default=0)
    return dict(
        n=n, total_pnl=round(float(pnl.sum()),1),
        win_rate=round(wr,1), win_full=round(len(full)/n*100,1),
        win_part=round(len(part)/n*100,1), loss_rate=round(len(loss)/n*100,1),
        avg_win=round(aw,1), avg_loss=round(al,1),
        expectancy=round(exp,1), pf=pf, max_dd=round(mdd,1),
        best=round(float(pnl.max()),1) if not pnl.empty else 0,
        worst=round(float(pnl.min()),1) if not pnl.empty else 0,
        max_win_streak=mxw, max_loss_streak=mxl,
    )

def _ly(**kw):
    b = dict(PLOTLY_BASE); b.update(kw); return b

def kpi_card(label, value, suffix="", cls="", sub=""):
    return (f'<div class="kpi">'
            f'<div class="kpi-label">{label}</div>'
            f'<div class="kpi-value {cls}">{value}{suffix}</div>'
            f'{"<div class=kpi-sub>"+sub+"</div>" if sub else ""}'
            f'</div>')

def kpi_row(items):
    cols = st.columns(len(items))
    for col, item in zip(cols, items):
        col.markdown(kpi_card(**item), unsafe_allow_html=True)

@st.cache_data(show_spinner=False)
def cached_journal(vid):
    df = load_journal(vid)
    if not df.empty and "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
    return df


# ─────────────────────────────────────────────────────────────────────────────
#  Chart functions
# ─────────────────────────────────────────────────────────────────────────────

def chart_equity(trades, color, name):
    pnl   = to_num(trades["total_pnl_pts"]).fillna(0)
    cum   = pnl.cumsum().reset_index(drop=True)
    dd    = (cum.cummax() - cum)
    dates = trades["date"].reset_index(drop=True)
    fig   = make_subplots(rows=2, cols=1, shared_xaxes=True,
                          row_heights=[0.72, 0.28], vertical_spacing=0.04)
    fig.add_trace(go.Scatter(x=dates, y=cum, name=name,
        line=dict(color=color, width=2),
        fill="tozeroy", fillcolor=hex_to_rgba(color)), row=1, col=1)
    fig.add_trace(go.Bar(x=dates, y=-dd, name="Drawdown",
        marker_color=C["red"], opacity=0.45), row=2, col=1)
    fig.update_layout(**_ly(title=f"Equity Curve — {name}",
                            showlegend=False, height=440))
    fig.update_yaxes(title_text="P&L (pts)", row=1)
    fig.update_yaxes(title_text="Drawdown",  row=2)
    return fig

def chart_monthly(trades):
    t = trades.copy()
    t["year"]  = t["date"].dt.year
    t["month"] = t["date"].dt.month
    t["pnl"]   = to_num(t["total_pnl_pts"])
    piv = t.groupby(["year","month"])["pnl"].sum().reset_index()
    piv = piv.pivot(index="year", columns="month", values="pnl")
    mn  = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    piv.columns = [mn[int(c)-1] for c in piv.columns]
    fig = px.imshow(piv,
        color_continuous_scale=[[0,C["red"]],[0.5,C["surface"]],[1,C["green"]]],
        color_continuous_midpoint=0, text_auto=".0f", aspect="auto")
    fig.update_layout(**_ly(title="Monthly P&L Heatmap",
                            coloraxis_showscale=False, height=300))
    fig.update_traces(textfont_size=10)
    return fig

def chart_yearly(trades):
    t = trades.copy()
    t["year"] = t["date"].dt.year
    t["pnl"]  = to_num(t["total_pnl_pts"])
    y = t.groupby("year")["pnl"].sum().reset_index()
    fig = go.Figure(go.Bar(
        x=y["year"].astype(str), y=y["pnl"],
        marker_color=[C["green"] if v>=0 else C["red"] for v in y["pnl"]],
        text=y["pnl"].round(0).astype(int), textposition="outside"))
    fig.update_layout(**_ly(title="Yearly P&L", height=300))
    return fig

def chart_donut(trades):
    oc  = trades["trade_outcome"].value_counts()
    cm  = {"WIN-FULL":C["green"],"WIN-PARTIAL":C["yellow"],
           "LOSS":C["red"],"BREAKEVEN":C["purple"]}
    fig = go.Figure(go.Pie(
        labels=oc.index, values=oc.values, hole=0.6,
        marker_colors=[cm.get(k, C["blue"]) for k in oc.index],
        textinfo="label+percent", textfont_size=12))
    fig.update_layout(**_ly(title="Trade Outcomes", showlegend=False, height=300))
    return fig

def chart_hist(trades):
    pnl = to_num(trades["total_pnl_pts"]).dropna()
    fig = px.histogram(pnl, nbins=60, color_discrete_sequence=[C["blue"]])
    fig.add_vline(x=0, line_color=C["red"], line_dash="dash", line_width=1.5)
    if not pnl.empty:
        fig.add_vline(x=pnl.mean(), line_color=C["green"], line_dash="dot",
            annotation_text=f"μ={pnl.mean():.1f}",
            annotation_font_color=C["green"])
    fig.update_layout(**_ly(title="P&L Distribution", height=300))
    return fig

def chart_dow(trades):
    t = trades.copy()
    t["pnl"]    = to_num(t["total_pnl_pts"])
    t["is_win"] = t["trade_outcome"].str.startswith("WIN", na=False)
    order = ["Mon","Tue","Wed","Thu","Fri"]
    g = t.groupby("day_of_week").agg(
        avg_pnl=("pnl","mean"), win_rate=("is_win","mean")
    ).reindex(order).reset_index()
    fig = make_subplots(specs=[[{"secondary_y":True}]])
    fig.add_trace(go.Bar(x=g["day_of_week"], y=g["avg_pnl"],
        marker_color=[C["green"] if v>=0 else C["red"]
                      for v in g["avg_pnl"].fillna(0)],
        name="Avg P&L"), secondary_y=False)
    fig.add_trace(go.Scatter(x=g["day_of_week"],
        y=(g["win_rate"]*100).round(1),
        mode="lines+markers",
        line=dict(color=C["blue"], width=2),
        name="Win %"), secondary_y=True)
    fig.update_layout(**_ly(title="Day of Week", height=300))
    return fig

def chart_scatter(trades):
    t  = trades.dropna(subset=["mfe_pts","mae_pts"]).copy()
    cm = {"WIN-FULL":C["green"],"WIN-PARTIAL":C["yellow"],
          "LOSS":C["red"],"BREAKEVEN":C["purple"]}
    fig = px.scatter(t, x="mae_pts", y="mfe_pts", color="trade_outcome",
        color_discrete_map=cm, opacity=0.65,
        hover_data=["date","entry_price","total_pnl_pts"])
    fig.update_layout(**_ly(title="MFE vs MAE", height=360,
        xaxis_title="MAE (Adverse)", yaxis_title="MFE (Favourable)"))
    return fig

def chart_overlay_equity(version_ids):
    fig = go.Figure()
    for v in version_ids:
        t = get_trades(cached_journal(v))
        if t.empty: continue
        pnl = to_num(t["total_pnl_pts"]).fillna(0)
        cum = pnl.cumsum().reset_index(drop=True)
        fig.add_trace(go.Scatter(
            x=t["date"].reset_index(drop=True), y=cum,
            name=f"v{v}", line=dict(color=version_color(v), width=2)))
    fig.update_layout(**_ly(
        title="Equity Curves — All Minor Versions",
        yaxis_title="Cumulative P&L (pts)", height=420))
    return fig

def chart_bar_metric(version_ids, metric, title):
    vals = [compute_metrics(get_trades(cached_journal(v))).get(metric,0) or 0
            for v in version_ids]
    fig = go.Figure(go.Bar(
        x=[f"v{v}" for v in version_ids], y=vals,
        marker_color=[version_color(v) for v in version_ids],
        text=[f"{vv:+.1f}" if isinstance(vv, float) else str(vv) for vv in vals],
        textposition="outside"))
    fig.update_layout(**_ly(title=title, height=280))
    return fig


# ─────────────────────────────────────────────────────────────────────────────
#  Strategy info panel (shown at top of Performance tab)
# ─────────────────────────────────────────────────────────────────────────────

def render_strategy_info(vid, meta, params, bt_meta, metrics):
    vc    = version_color(vid)
    saved = vid in list_versions()

    # Header
    st.markdown(f"""
    <div style="display:flex;align-items:center;gap:14px;margin-bottom:16px">
      <div style="background:{vc}22;border:1px solid {vc}55;border-radius:8px;
                  padding:10px 18px;font-family:'JetBrains Mono',monospace;
                  font-size:20px;font-weight:700;color:{vc}">v{vid}</div>
      <div>
        <div style="font-size:18px;font-weight:700">{meta.get("name","")}</div>
        <div style="font-family:'JetBrains Mono',monospace;font-size:11px;
                    color:{C["muted"]};margin-top:2px">
          Rulebook: {meta.get("rulebook_date","")} &nbsp;·&nbsp;
          Nifty 50 NSE Spot &nbsp;·&nbsp; Long Only &nbsp;·&nbsp; 3-Min
        </div>
      </div>
      <div style="margin-left:auto;font-family:'JetBrains Mono',monospace;
                  font-size:11px;color:{C["muted"]}">
        {"✅ Backtested" if saved else "⬜ Not yet run"}
        {" &nbsp;·&nbsp; " + bt_meta.get("backtest_start","")[:10]
         + " → " + bt_meta.get("backtest_end","")[:10]
         if saved and bt_meta else ""}
      </div>
    </div>
    """, unsafe_allow_html=True)

    # Three info columns
    ca, cb, cc = st.columns([1.2, 1.2, 1.6])

    with ca:
        st.markdown('<div class="section-hdr">CPR Width Filter</div>',
                    unsafe_allow_html=True)
        st.markdown(f"""
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
          <div style="background:{C["surface"]};border:1px solid {vc}44;
                      border-radius:6px;padding:10px 12px">
            <div style="font-family:'JetBrains Mono',monospace;font-size:10px;
                        color:{C["muted"]}">VN-CPR</div>
            <div style="font-family:'JetBrains Mono',monospace;font-size:16px;
                        font-weight:700;color:{vc}">
              &lt; {params["cpr"]["vn_threshold"]}%</div>
          </div>
          <div style="background:{C["surface"]};border:1px solid {vc}44;
                      border-radius:6px;padding:10px 12px">
            <div style="font-family:'JetBrains Mono',monospace;font-size:10px;
                        color:{C["muted"]}">Total Band</div>
            <div style="font-family:'JetBrains Mono',monospace;font-size:16px;
                        font-weight:700;color:{vc}">{meta.get("cpr_band","")}</div>
          </div>
        </div>
        <div style="margin-top:8px;font-family:'JetBrains Mono',monospace;
                    font-size:11px;color:{C["muted"]}">
          Intent: <span style="color:{C["text"]}">{meta.get("intent","")}</span>
        </div>
        """, unsafe_allow_html=True)

    with cb:
        st.markdown('<div class="section-hdr">Trade Rules</div>',
                    unsafe_allow_html=True)
        sl=params["sl"]; tgt=params["targets"]
        tsl=params["tsl"]; ema=params["ema"]
        st.markdown(f"""
        <div style="font-family:'JetBrains Mono',monospace;font-size:12px;line-height:2.1">
          <span style="color:{C["muted"]}">Fixed SL:    </span><span>{sl["max_sl_pts"]} pts</span><br>
          <span style="color:{C["muted"]}">Struct SL:   </span><span>Prior {sl["lookback"]} candle lows</span><br>
          <span style="color:{C["muted"]}">TP-1:        </span><span style="color:{C["green"]}">Entry + R × {tgt["tp1_r_multiple"]}</span><br>
          <span style="color:{C["muted"]}">TSL Buffer:  </span><span>{ema["fast"]}-EMA − {tsl["buffer_pts"]} pts</span><br>
          <span style="color:{C["muted"]}">TSL Update:  </span><span>Every {tsl["update_mins"]} min</span><br>
          <span style="color:{C["muted"]}">EMAs:        </span><span>{ema["fast"]}-EMA &gt; {ema["slow"]}-EMA</span>
        </div>
        """, unsafe_allow_html=True)

    with cc:
        st.markdown('<div class="section-hdr">Session Rules</div>',
                    unsafe_allow_html=True)
        ses = params["session"]
        st.markdown(f"""
        <div style="font-family:'JetBrains Mono',monospace;font-size:12px;line-height:2.1">
          <span style="color:{C["muted"]}">Entry from:   </span><span>{ses["entry_start"]}</span><br>
          <span style="color:{C["muted"]}">Entry cutoff: </span><span style="color:{C["red"]}">{ses["entry_cutoff"]} (hard)</span><br>
          <span style="color:{C["muted"]}">Hard exit:    </span><span style="color:{C["red"]}">{ses["hard_exit"]}</span><br>
          <span style="color:{C["muted"]}">Obs window:   </span><span>9:18–9:30 ({ses["min_obs_above"]} of 4 closes &gt; TC)</span><br>
          <span style="color:{C["muted"]}">Position:     </span><span>2 lots (Qty-1 + Qty-2)</span>
        </div>
        """, unsafe_allow_html=True)

    # Changes from previous
    changes = [c for c in meta.get("changes_from_previous",[])
               if "Initial" not in c]
    if changes:
        st.markdown('<div class="section-hdr">Changes from Previous Minor Version</div>',
                    unsafe_allow_html=True)
        st.markdown("".join(
            f'<div class="change-item">▸ {c}</div>' for c in changes
        ), unsafe_allow_html=True)

    # Live summary if backtested
    if saved and metrics:
        st.markdown('<div class="section-hdr">Backtest Summary</div>',
                    unsafe_allow_html=True)
        kpi_row([
            dict(label="Trades",       value=metrics["n"]),
            dict(label="Total P&L",    value=f"{metrics['total_pnl']:+.0f}",
                 suffix=" pts",
                 cls="kpi-pos" if metrics["total_pnl"]>=0 else "kpi-neg"),
            dict(label="Win Rate",     value=f"{metrics['win_rate']:.1f}",
                 suffix="%",
                 cls="kpi-pos" if metrics["win_rate"]>=50 else "kpi-neg"),
            dict(label="Expectancy",   value=f"{metrics['expectancy']:+.1f}",
                 suffix=" pts",
                 cls="kpi-pos" if metrics["expectancy"]>0 else "kpi-neg"),
            dict(label="Profit Factor",value=str(metrics["pf"])),
            dict(label="Max Drawdown", value=f"{metrics['max_dd']:.0f}",
                 suffix=" pts", cls="kpi-neg"),
        ])


# ─────────────────────────────────────────────────────────────────────────────
#  Sidebar
# ─────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown(f"""
    <div style="padding:8px 0 16px">
      <div style="font-family:'JetBrains Mono',monospace;font-size:18px;
                  font-weight:700;color:{C["blue"]}">◈ CPR STRATEGY</div>
      <div style="font-family:'JetBrains Mono',monospace;font-size:10px;
                  color:{C["muted"]};letter-spacing:.12em;margin-top:4px">
        LONG ONLY · NIFTY 50 · INTRADAY</div>
    </div>
    """, unsafe_allow_html=True)
    st.divider()

    saved  = list_versions()
    majors = major_versions()

    if not saved:
        st.warning(
            "No results yet.\n\n"
            "Run a backtest first:\n"
            "```\npython run_backtest.py "
            "--major 1 --source yfinance\n```"
        )

    st.markdown(
        f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:10px;'
        f'font-weight:700;letter-spacing:.12em;text-transform:uppercase;'
        f'color:{C["muted"]}">Select Strategy</div>',
        unsafe_allow_html=True
    )

    # Initialize session state for version tracking
    if "sel_minor" not in st.session_state:
        st.session_state.sel_minor = minor_versions_of(majors[0])[0] if majors else None
    if "sel_major" not in st.session_state:
        st.session_state.sel_major = majors[0] if majors else None
    
    def on_major_change():
        """Reset minor version when major version changes"""
        st.session_state.sel_minor = minor_versions_of(st.session_state.sel_major)[0]
    
    sel_major = st.selectbox(
        "Major Version (Rulebook)",
        majors,
        key="sel_major",
        on_change=on_major_change,
        format_func=lambda m: f"V{m} — {len(minor_versions_of(m))} variants"
    )

    minor_opts = minor_versions_of(sel_major)
    sel_minor  = st.selectbox(
        "Minor Version",
        minor_opts,
        key="sel_minor",
        format_func=lambda v: f"v{v}  {'✅' if v in saved else '⬜'}"
    )

    st.divider()
    st.markdown(
        f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:10px;'
        f'font-weight:700;letter-spacing:.12em;text-transform:uppercase;'
        f'color:{C["muted"]}">Filters</div>',
        unsafe_allow_html=True
    )
    cpr_f  = st.selectbox("CPR Type", ["All","VN-CPR","N-CPR"], key="cpr_filter")
    year_f = st.text_input("Year", placeholder="e.g. 2023 (blank = all)", key="year_filter")
    st.divider()
    st.caption("📁 Results saved in:\n`data/results/{version}/`")


# ─────────────────────────────────────────────────────────────────────────────
#  Load active version
# ─────────────────────────────────────────────────────────────────────────────

version_id = st.session_state.sel_minor
vc         = version_color(version_id)

try:
    strategy     = load_strategy(version_id)
    strat_meta   = strategy.get_metadata()
    strat_params = strategy.get_params()
except Exception as e:
    st.error(f"Could not load strategy {version_id}: {e}")
    st.stop()

bt_meta = load_metadata(version_id)
df_raw  = cached_journal(version_id) if version_id in saved else pd.DataFrame()

# Apply sidebar filters
df = df_raw.copy()
if not df.empty:
    if st.session_state.get("cpr_filter", "All") != "All" and "cpr_type" in df.columns:
        df = df[df["cpr_type"] == st.session_state.get("cpr_filter", "All")]
    year_val = st.session_state.get("year_filter", "").strip()
    if year_val:
        try: df = df[df["date"].dt.year == int(year_val)]
        except ValueError: pass

trades  = get_trades(df)
metrics = compute_metrics(trades)


# ─────────────────────────────────────────────────────────────────────────────
#  Page header
# ─────────────────────────────────────────────────────────────────────────────

st.markdown(f"""
<div style="font-size:26px;font-weight:700;margin-bottom:4px">
  CPR Strategy Dashboard</div>
<div style="font-family:'JetBrains Mono',monospace;font-size:11px;
            color:{C["muted"]};margin-bottom:20px">
  Active: <span style="color:{vc}">v{version_id}</span> &nbsp;·&nbsp;
  Major V{sel_major} ({len(minor_opts)} variants) &nbsp;·&nbsp;
  Nifty 50 · NSE Spot · Zerodha Kite Connect
</div>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
#  Tabs
# ─────────────────────────────────────────────────────────────────────────────

tab_perf, tab_cmp, tab_info, tab_journal = st.tabs([
    "📊  Performance",
    "⚖️  Version Comparison",
    "📋  Strategy Info & Rulebook",
    "🗒️  Trade Journal",
])


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 1 — PERFORMANCE
# ══════════════════════════════════════════════════════════════════════════════

with tab_perf:
    render_strategy_info(version_id, strat_meta, strat_params, bt_meta, metrics)
    st.divider()

    if df_raw.empty:
        st.info(
            f"No backtest data for v{version_id} yet.\n\n"
            f"Run:\n```\npython run_backtest.py "
            f"--version {version_id} --source yfinance\n```"
        )
    elif trades.empty:
        st.warning("No trades match current filters.")
    else:
        kpi_row([
            dict(label="Total Trades",  value=metrics["n"]),
            dict(label="Total P&L",     value=f"{metrics['total_pnl']:+.0f}",
                 suffix=" pts",
                 cls="kpi-pos" if metrics["total_pnl"]>=0 else "kpi-neg"),
            dict(label="Win Rate",      value=f"{metrics['win_rate']:.1f}",
                 suffix="%",
                 cls="kpi-pos" if metrics["win_rate"]>=50 else "kpi-neg"),
            dict(label="Expectancy",    value=f"{metrics['expectancy']:+.1f}",
                 suffix=" pts",
                 cls="kpi-pos" if metrics["expectancy"]>0 else "kpi-neg"),
            dict(label="Profit Factor", value=str(metrics["pf"])),
            dict(label="Max Drawdown",  value=f"{metrics['max_dd']:.0f}",
                 suffix=" pts", cls="kpi-neg"),
        ])
        kpi_row([
            dict(label="WIN-FULL %",    value=f"{metrics['win_full']:.1f}",
                 suffix="%", cls="kpi-pos"),
            dict(label="WIN-PARTIAL %", value=f"{metrics['win_part']:.1f}",
                 suffix="%"),
            dict(label="Loss %",        value=f"{metrics['loss_rate']:.1f}",
                 suffix="%", cls="kpi-neg"),
            dict(label="Avg Win",       value=f"{metrics['avg_win']:+.1f}",
                 suffix=" pts", cls="kpi-pos"),
            dict(label="Avg Loss",      value=f"{metrics['avg_loss']:+.1f}",
                 suffix=" pts", cls="kpi-neg"),
            dict(label="Max Win Streak",value=metrics["max_win_streak"],
                 cls="kpi-pos"),
        ])

        st.markdown('<div class="section-hdr">Equity & Drawdown</div>',
                    unsafe_allow_html=True)
        st.plotly_chart(chart_equity(trades, vc, f"v{version_id}"),
                        width='stretch')

        c1, c2 = st.columns([3, 2])
        with c1:
            st.markdown('<div class="section-hdr">Monthly P&L Heatmap</div>',
                        unsafe_allow_html=True)
            st.plotly_chart(chart_monthly(trades), width='stretch')
        with c2:
            st.markdown('<div class="section-hdr">Yearly P&L</div>',
                        unsafe_allow_html=True)
            st.plotly_chart(chart_yearly(trades), width='stretch')

        c3, c4 = st.columns(2)
        with c3:
            st.markdown('<div class="section-hdr">Trade Outcomes</div>',
                        unsafe_allow_html=True)
            st.plotly_chart(chart_donut(trades), width='stretch')
        with c4:
            st.markdown('<div class="section-hdr">P&L Distribution</div>',
                        unsafe_allow_html=True)
            st.plotly_chart(chart_hist(trades), width='stretch')

        c5, c6 = st.columns(2)
        with c5:
            st.markdown('<div class="section-hdr">Day of Week</div>',
                        unsafe_allow_html=True)
            st.plotly_chart(chart_dow(trades), width='stretch')
        with c6:
            st.markdown('<div class="section-hdr">MFE vs MAE</div>',
                        unsafe_allow_html=True)
            st.plotly_chart(chart_scatter(trades), width='stretch')


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 2 — VERSION COMPARISON
# ══════════════════════════════════════════════════════════════════════════════

with tab_cmp:
    st.markdown(
        f'<div class="section-hdr">Compare Minor Versions — Major V{sel_major}</div>',
        unsafe_allow_html=True)

    saved_minors = [v for v in minor_opts if v in saved]

    if len(saved_minors) < 2:
        st.info(
            f"Need ≥ 2 backtested versions to compare. "
            f"Saved so far: {saved_minors or 'none'}.\n\n"
            f"Run all at once:\n"
            f"```\npython run_backtest.py --major {sel_major} --source yfinance\n```"
        )
    else:
        cmp_sel = st.multiselect(
            "Versions to compare", saved_minors, default=saved_minors,
            format_func=lambda v: f"v{v}"
        )

        if len(cmp_sel) >= 2:
            all_m = {v: compute_metrics(get_trades(cached_journal(v)))
                     for v in cmp_sel}

            st.markdown('<div class="section-hdr">Equity Curves Overlay</div>',
                        unsafe_allow_html=True)
            st.plotly_chart(chart_overlay_equity(cmp_sel),
                            width='stretch')

            # Head-to-head table
            st.markdown('<div class="section-hdr">Head-to-Head Metrics</div>',
                        unsafe_allow_html=True)
            metric_map = {
                "n":          "Total Trades",
                "total_pnl":  "Total P&L (pts)",
                "win_rate":   "Win Rate %",
                "win_full":   "WIN-FULL %",
                "loss_rate":  "Loss Rate %",
                "avg_win":    "Avg Win (pts)",
                "avg_loss":   "Avg Loss (pts)",
                "expectancy": "Expectancy (pts)",
                "pf":         "Profit Factor",
                "max_dd":     "Max Drawdown (pts)",
                "best":       "Best Trade (pts)",
                "worst":      "Worst Trade (pts)",
            }
            lower_better = {"max_dd","loss_rate","avg_loss","worst"}

            rows = []
            for mk, ml in metric_map.items():
                row = {"Metric": ml}
                for v in cmp_sel:
                    row[f"v{v}"] = all_m[v].get(mk, "—")
                rows.append(row)
            cdf = pd.DataFrame(rows)

            def hl_best(row):
                styles = [""] * (len(cmp_sel) + 1)
                try:
                    nums = {j+1: row[f"v{v}"]
                            for j,v in enumerate(cmp_sel)
                            if isinstance(row.get(f"v{v}"), (int, float))}
                    if not nums: return styles
                    lb = row["Metric"] in {metric_map[k] for k in lower_better
                                           if k in metric_map}
                    bi = (min(nums, key=nums.__getitem__) if lb
                          else max(nums, key=nums.__getitem__))
                    styles[bi] = (f"background-color:{C['green']}22;"
                                  f"color:{C['green']};font-weight:700")
                except Exception:
                    pass
                return styles

            st.dataframe(cdf.style.apply(hl_best, axis=1),
                         width='stretch', height=420)

            # Delta vs first version
            ref    = cmp_sel[0]
            others = cmp_sel[1:]
            if others:
                st.markdown(f'<div class="section-hdr">Delta vs v{ref}</div>',
                            unsafe_allow_html=True)
                dcols = st.columns(len(others))
                for ci, v in enumerate(others):
                    vc2 = version_color(v)
                    with dcols[ci]:
                        html = (f'<div style="background:{C["card"]};'
                                f'border:1px solid {vc2}44;border-radius:8px;'
                                f'padding:14px">')
                        html += (f'<div style="font-family:\'JetBrains Mono\','
                                 f'monospace;font-size:13px;font-weight:700;'
                                 f'color:{vc2};margin-bottom:10px">v{v}</div>')
                        for mk in ["total_pnl","win_rate","expectancy","max_dd"]:
                            bv = all_m[ref].get(mk)
                            cv = all_m[v].get(mk)
                            if not all(isinstance(x,(int,float))
                                       for x in [bv,cv] if x is not None):
                                continue
                            delta = cv - bv
                            good  = (delta < 0) if mk in lower_better else (delta > 0)
                            dc    = C["green"] if good else C["red"]
                            html += (f'<div style="display:flex;justify-content:'
                                     f'space-between;padding:4px 0;border-bottom:'
                                     f'1px solid {C["border"]}">'
                                     f'<span style="font-size:11px;color:{C["muted"]}">'
                                     f'{metric_map[mk]}</span>'
                                     f'<span style="font-family:\'JetBrains Mono\','
                                     f'monospace;font-size:12px;color:{dc}">'
                                     f'{delta:+.1f}</span></div>')
                        html += '</div>'
                        st.markdown(html, unsafe_allow_html=True)

            # Bar charts
            st.markdown('<div class="section-hdr">Metric Bars</div>',
                        unsafe_allow_html=True)
            b1, b2, b3 = st.columns(3)
            with b1:
                st.plotly_chart(chart_bar_metric(cmp_sel,"win_rate","Win Rate %"),
                                width='stretch')
            with b2:
                st.plotly_chart(chart_bar_metric(cmp_sel,"expectancy","Expectancy"),
                                width='stretch')
            with b3:
                st.plotly_chart(chart_bar_metric(cmp_sel,"total_pnl","Total P&L"),
                                width='stretch')


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 3 — STRATEGY INFO & RULEBOOK
# ══════════════════════════════════════════════════════════════════════════════

with tab_info:
    # Major version description block
    base_mod = load_major_base(sel_major)
    if base_mod:
        st.markdown(f"""
        <div style="background:{C["card"]};border:1px solid {C["border"]};
                    border-left:4px solid {vc};border-radius:8px;
                    padding:18px 22px;margin-bottom:20px">
          <div style="font-family:'JetBrains Mono',monospace;font-size:13px;
                      font-weight:700;color:{vc};margin-bottom:8px">
            Major Version {sel_major} — {getattr(base_mod,"RULEBOOK_NAME","")}
          </div>
          <div style="font-size:13px;color:{C["text"]};line-height:1.7">
            {getattr(base_mod,"DESCRIPTION","").strip()}
          </div>
          <div style="margin-top:12px;font-family:'JetBrains Mono',monospace;
                      font-size:11px;color:{C["muted"]}">
            Rulebook: {getattr(base_mod,"RULEBOOK_DATE","")} &nbsp;·&nbsp;
            {getattr(base_mod,"INSTRUMENT","")} &nbsp;·&nbsp;
            Execution: {getattr(base_mod,"TIMEFRAME_EXEC","")}
          </div>
        </div>
        """, unsafe_allow_html=True)

    # All minor versions
    st.markdown(f'<div class="section-hdr">All V{sel_major}.x Minor Versions</div>',
                unsafe_allow_html=True)

    for v in minor_opts:
        try:
            s  = load_strategy(v)
            sm = s.get_metadata()
            sp = s.get_params()
        except Exception:
            continue

        vc2      = version_color(v)
        is_saved = v in saved
        m2       = compute_metrics(get_trades(cached_journal(v))) if is_saved else {}

        changes_html = "".join(
            f'<div style="margin:3px 0;padding-left:10px;border-left:2px solid '
            f'{vc2}44;font-size:12px;color:{C["muted"]}">▸ {c}</div>'
            for c in sm.get("changes_from_previous", [])
            if "Initial" not in c
        )

        metrics_html = ""
        if is_saved and m2:
            pc = C["green"] if m2.get("total_pnl",0)>=0 else C["red"]
            ec = C["green"] if m2.get("expectancy",0)>=0 else C["red"]
            metrics_html = (
                f'<div style="display:flex;gap:20px;margin-top:10px;'
                f'padding-top:10px;border-top:1px solid {C["border"]};'
                f'font-family:\'JetBrains Mono\',monospace;font-size:12px">'
                f'<span style="color:{C["muted"]}">Trades: '
                f'<b style="color:{C["text"]}">{m2.get("n","—")}</b></span>'
                f'<span style="color:{C["muted"]}">P&L: '
                f'<b style="color:{pc}">{m2.get("total_pnl","—")} pts</b></span>'
                f'<span style="color:{C["muted"]}">Win: '
                f'<b style="color:{C["green"]}">{m2.get("win_rate","—")}%</b></span>'
                f'<span style="color:{C["muted"]}">Exp: '
                f'<b style="color:{ec}">{m2.get("expectancy","—")}</b></span>'
                f'<span style="color:{C["muted"]}">PF: '
                f'<b style="color:{C["yellow"]}">{m2.get("pf","—")}</b></span>'
                f'<span style="color:{C["muted"]}">MDD: '
                f'<b style="color:{C["red"]}">{m2.get("max_dd","—")} pts</b></span>'
                f'</div>'
            )

        st.markdown(f"""
        <div style="background:{C["card"]};border:1px solid {C["border"]};
                    border-left:4px solid {vc2};border-radius:8px;
                    padding:16px 20px;margin-bottom:10px">
          <div style="display:flex;align-items:center;
                      justify-content:space-between;margin-bottom:10px">
            <div>
              <span style="font-family:'JetBrains Mono',monospace;font-size:14px;
                           font-weight:700;color:{vc2}">v{v}</span>
              <span style="margin-left:10px;font-size:13px">
                {sm.get("name","")}</span>
            </div>
            <span style="font-family:'JetBrains Mono',monospace;font-size:11px;
                         padding:3px 10px;border-radius:4px;
                         background:{""+C["green"]+"22" if is_saved else C["surface"]};
                         color:{""+C["green"] if is_saved else C["muted"]}">
              {"✅ Backtested" if is_saved else "⬜ Not run"}
            </span>
          </div>
          <div style="display:grid;grid-template-columns:repeat(5,1fr);gap:8px;
                      font-family:'JetBrains Mono',monospace;font-size:12px">
            <div><span style="color:{C["muted"]}">VN-CPR: </span>
              <span style="color:{vc2}">&lt; {sp["cpr"]["vn_threshold"]}%</span></div>
            <div><span style="color:{C["muted"]}">N-CPR:  </span>
              <span style="color:{vc2}">&lt; {sp["cpr"]["n_threshold"]}%</span></div>
            <div><span style="color:{C["muted"]}">Band:   </span>
              <span>{sm.get("cpr_band","")}</span></div>
            <div><span style="color:{C["muted"]}">TP-1:   </span>
              <span>R × {sp["targets"]["tp1_r_multiple"]}</span></div>
            <div><span style="color:{C["muted"]}">SL:     </span>
              <span>−{sp["sl"]["max_sl_pts"]} pts</span></div>
          </div>
          {changes_html}
          {metrics_html}
        </div>
        """, unsafe_allow_html=True)

    # Parameter comparison table
    st.markdown(f'<div class="section-hdr">Parameter Table — V{sel_major}.x</div>',
                unsafe_allow_html=True)
    prows = []
    for v in minor_opts:
        try:
            p  = load_strategy(v).get_params()
            pm = load_strategy(v).get_metadata()
            prows.append({
                "Version":       f"v{v}",
                "VN-CPR <":      f"{p['cpr']['vn_threshold']}%",
                "N-CPR <":       f"{p['cpr']['n_threshold']}%",
                "CPR Band":      pm.get("cpr_band",""),
                "Intent":        pm.get("intent",""),
                "Fixed SL":      f"{p['sl']['max_sl_pts']} pts",
                "TP-1 Multiple": f"R × {p['targets']['tp1_r_multiple']}",
                "TSL Buffer":    f"{p['tsl']['buffer_pts']} pts",
                "TSL Interval":  f"{p['tsl']['update_mins']} min",
                "EMA Fast/Slow": f"{p['ema']['fast']}/{p['ema']['slow']}",
                "Entry Cutoff":  p["session"]["entry_cutoff"],
                "Hard Exit":     p["session"]["hard_exit"],
                "Backtested":    "✅" if v in saved else "⬜",
            })
        except Exception:
            pass
    if prows:
        st.dataframe(pd.DataFrame(prows),
                     width='stretch', hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 4 — TRADE JOURNAL
# ══════════════════════════════════════════════════════════════════════════════

with tab_journal:
    if df_raw.empty:
        st.info(
            f"No data for v{version_id}.\n\n"
            f"```\npython run_backtest.py "
            f"--version {version_id} --source yfinance\n```"
        )
    else:
        show_cols = [c for c in [
            "date","day_of_week","cpr_type","cpr_width_pct",
            "ab_cpr","po_above_tc","setup_valid",
            "entry_type","entry_time","entry_price",
            "sl_method","sl_price","r_value","tp1_price",
            "tp1_hit","tp1_pnl_pts",
            "qty2_exit_type","qty2_exit_price","qty2_pnl_pts",
            "total_pnl_pts","trade_outcome",
            "mfe_pts","mae_pts","trade_duration",
        ] if c in df.columns]

        disp = (df[show_cols]
                .sort_values("date", ascending=False)
                .reset_index(drop=True))

        def co(v):
            if str(v).startswith("WIN"): return f"color:{C['green']}"
            if v == "LOSS":              return f"color:{C['red']}"
            return ""

        def cp(v):
            try:
                f = float(v)
                return (f"color:{C['green']}" if f > 0
                        else (f"color:{C['red']}" if f < 0 else ""))
            except Exception:
                return ""

        fmt = {k: "{:+.2f}"
               for k in ["total_pnl_pts","tp1_pnl_pts","qty2_pnl_pts"]
               if k in disp.columns}
        if "cpr_width_pct" in disp.columns:
            fmt["cpr_width_pct"] = "{:.4f}%"

        styled = (disp.style
                  .applymap(co,  subset=["trade_outcome"])
                  .applymap(cp,  subset=["total_pnl_pts"])
                  .format(fmt,   na_rep="—"))

        st.dataframe(styled, width='stretch', height=540)

        d1, d2, _ = st.columns([1, 1, 5])
        with d1:
            st.download_button(
                "⬇ CSV",
                df[show_cols].to_csv(index=False),
                f"cpr_v{version_id}_journal.csv",
                "text/csv",
            )
        with d2:
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as w:
                df[show_cols].to_excel(w, index=False, sheet_name="Journal")
            st.download_button(
                "⬇ XLSX",
                buf.getvalue(),
                f"cpr_v{version_id}_journal.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
