import streamlit as st
import numpy as np
import pandas as pd
import yfinance as yf
from bcb import sgs
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests
import io
import math

# --- Configuração da Página ---
st.set_page_config(
    page_title="EBITDA at Risk - Análise de Sensibilidade",
    layout="wide",
    initial_sidebar_state="expanded"
)



st.title("EBITDA at Risk")
st.subheader("Simulação de Risco de Mercado na Projeção Operacional")
st.markdown("---")


# --- Funções de Formatação (Padrão BRL) ---

def format_currency_brl(value):
    """Formata valor como moeda brasileira (R$ 1.000.000,00)"""
    if isinstance(value, (int, float, np.float64)):
        return f"R$ {value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return value


def format_percent_brl(value):
    """Formata valor como porcentagem (25,00 %)"""
    if isinstance(value, (int, float, np.float64)):
        return f"{value:,.2f} %".replace(",", "_").replace(".", ",").replace("_", ".")
    return value


# Alias para compatibilidade com o novo código
formatar_brl = format_currency_brl
formatar_pct = format_percent_brl


# --- Estilos CSS Condicionais para Destaque de Linhas Sintéticas ---

def apply_row_styles(row, synthetic_list):
    """Aplica estilo condicional a todas as células da linha, incluindo o índice (header)"""
    is_synthetic = row.name in synthetic_list

    # Fundo sutil que funciona bem em dark/light mode
    bg_color = 'background-color: rgba(100, 100, 100, 0.1);' if is_synthetic else ''

    # Aplica negrito a todas as células da linha (incluindo o header visualmente)
    font_weight = 'font-weight: bold;' if is_synthetic else ''

    # Garante que o índice (Conta) também tenha o estilo aplicado
    styles = [style for _ in row.index.tolist() for style in [f'{bg_color}{font_weight}']]

    return [f'{bg_color}{font_weight}'] * len(row)


# --- 1. Input de Períodos e Premissas ---

st.markdown("### Configuração da Análise Temporal")

num_periodos = st.number_input(
    "Número de Períodos (Colunas para Projeção)",
    min_value=1, max_value=12, value=3, step=1,
    help="Define quantos meses/trimestres serão projetados."
)

st.markdown("---")

# Estrutura das Premissas (Inputs)
period_cols = [f"Período {i + 1}" for i in range(num_periodos)]
colunas = period_cols  # Alias para compatibilidade com o novo código
num_meses = num_periodos  # Alias para compatibilidade com o novo código

data = {
    "Premissa": [
        "Preço de Venda (USD)",
        "Quantidade Vendida (Unid)",
        "Cotação USD/BRL",
        "Receita Mercado Interno (R$)",
        "Deduções sobre Vendas (R$)",
        "Custos (R$)",
        "Despesas Operacionais (R$)",
        "Caixa no Exterior (R$ - Exp. em US$)",
        "Empréstimos e Financiamentos (R$ - Exp. em US$)",
        "Hedge Contratado - Comprado (R$)",
        "Hedge Contratado - Vendido (R$)"
    ],
    "Unidade": [
        "USD", "Unid.", "R$/USD", "R$", "R$", "R$", "R$", "R$", "R$", "R$", "R$"
    ]
}

base_values = {
    "Preço de Venda (USD)": 25.0, "Quantidade Vendida (Unid)": 10000, "Cotação USD/BRL": 5.00,
    "Receita Mercado Interno (R$)": 500000.0, "Deduções sobre Vendas (R$)": 50000.0, "Custos (R$)": 800000.0,
    "Despesas Operacionais (R$)": 150000.0, "Caixa no Exterior (R$ - Exp. em US$)": 100000.0,
    "Empréstimos e Financiamentos (R$ - Exp. em US$)": 200000.0, "Hedge Contratado - Comprado (R$)": 0.0,
    "Hedge Contratado - Vendido (R$)": 0.0
}

df_data = pd.DataFrame(data)
for col in period_cols:
    df_data[col] = df_data["Premissa"].map(base_values)

# --- Configuração de Coluna CORRIGIDA para o st.data_editor ---
column_config = {
    "Premissa": st.column_config.Column("Premissa", disabled=True),
    "Unidade": st.column_config.Column("Unidade", disabled=True)
}

for col in period_cols:
    column_config[col] = st.column_config.NumberColumn(
        col, format="%.2f", min_value=0.0
    )

with st.expander("Premissas Operacionais e de Tesouraria (Edição Multi-Período)", expanded=True):
    st.markdown(
        "Defina os valores das premissas. Os valores em R$ e outras moedas devem ser entendidos pelo rótulo 'Unidade'.")
    df_premissas_editado = st.data_editor(
        df_data, column_config=column_config, hide_index=True, key="df_premissas"
    )

st.markdown("---")

# --- 2. CÁLCULO E PREENCHIMENTO DA DRE E EXPOSIÇÃO ---

# Contas Sintéticas
SYNTHETIC_ACCOUNTS = [
    "Receitas Operacionais (R$)", "Receita Líquida (R$)", "EBITDA (R$)",
    "Exposição Financeira (R$)", "Exposição Cambial Líquida (R$)", "Exposição Cambial Final (R$)"
]

# Estrutura da DRE/Exposição
dre_df_data = {
    "Conta": [
        "Receitas Operacionais (R$)",
        "  Receita em Moeda Estrangeira (R$)",  # RENOMEADO
        "  Receita Mercado Interno (R$)",
        "Deduções sobre Vendas (R$)",
        "Receita Líquida (R$)",
        "Custos (R$)",
        "Despesas Operacionais (R$)",
        "EBITDA (R$)",
        "Margem EBITDA (%)",

        # Linhas de Exposição (integradas na DRE)
        "Exposição Financeira (R$)",
        "  Caixa no Exterior (R$ - Exp. em US$)",
        "  Empréstimos e Financiamentos (R$ - Exp. em US$)",

        "Exposição Cambial Líquida (R$)",

        "  Hedge Contratado - Comprado (R$)",
        "  Hedge Contratado - Vendido (R$)",

        "Exposição Cambial Final (R$)"
    ]
}
dre_df = pd.DataFrame(dre_df_data).set_index("Conta")

# Processar e Calcular
for periodo in period_cols:
    premissas = df_premissas_editado.set_index("Premissa")[periodo]

    # --- DRE Cálculos ---
    preco_usd = premissas["Preço de Venda (USD)"]
    qtd = premissas["Quantidade Vendida (Unid)"]
    ptax = premissas["Cotação USD/BRL"]

    receita_exportacao_brl = preco_usd * qtd * ptax
    receita_liquida = (receita_exportacao_brl + premissas["Receita Mercado Interno (R$)"]) - premissas[
        "Deduções sobre Vendas (R$)"]
    ebitda = receita_liquida - premissas["Custos (R$)"] - premissas["Despesas Operacionais (R$)"]
    margem_ebitda = (ebitda / receita_liquida) * 100 if receita_liquida != 0 else 0.0

    # --- Exposição Cálculos ---
    caixa_ext = premissas["Caixa no Exterior (R$ - Exp. em US$)"]
    emprestimos = premissas["Empréstimos e Financiamentos (R$ - Exp. em US$)"]
    hedge_comprado = premissas["Hedge Contratado - Comprado (R$)"]
    hedge_vendido = premissas["Hedge Contratado - Vendido (R$)"]

    # Exposição Cambial Líquida (Operacional: Receita Exportação + Financeira: Caixa - Empréstimos)
    exposicao_cambial_liquida = receita_exportacao_brl + caixa_ext - emprestimos

    # Exposição Cambial Final (Líquida + Hedge Net)
    exposicao_cambial_final = exposicao_cambial_liquida + (hedge_comprado - hedge_vendido)

    # --- Preenchimento do DataFrame ---
    dre_df.loc["Receitas Operacionais (R$)", periodo] = receita_exportacao_brl + premissas[
        "Receita Mercado Interno (R$)"]
    dre_df.loc["  Receita em Moeda Estrangeira (R$)", periodo] = receita_exportacao_brl  # RENOMEADO
    dre_df.loc["  Receita Mercado Interno (R$)", periodo] = premissas["Receita Mercado Interno (R$)"]
    dre_df.loc["Deduções sobre Vendas (R$)", periodo] = premissas["Deduções sobre Vendas (R$)"]
    dre_df.loc["Receita Líquida (R$)", periodo] = receita_liquida
    dre_df.loc["Custos (R$)", periodo] = premissas["Custos (R$)"]
    dre_df.loc["Despesas Operacionais (R$)", periodo] = premissas["Despesas Operacionais (R$)"]
    dre_df.loc["EBITDA (R$)", periodo] = ebitda
    dre_df.loc["Margem EBITDA (%)", periodo] = margem_ebitda

    # Preenchimento das linhas de Exposição
    dre_df.loc["Exposição Financeira (R$)", periodo] = caixa_ext + emprestimos
    dre_df.loc["  Caixa no Exterior (R$ - Exp. em US$)", periodo] = caixa_ext
    dre_df.loc["  Empréstimos e Financiamentos (R$ - Exp. em US$)", periodo] = emprestimos

    dre_df.loc["Exposição Cambial Líquida (R$)", periodo] = exposicao_cambial_liquida

    dre_df.loc["  Hedge Contratado - Comprado (R$)", periodo] = hedge_comprado
    dre_df.loc["  Hedge Contratado - Vendido (R$)", periodo] = hedge_vendido

    dre_df.loc["Exposição Cambial Final (R$)", periodo] = exposicao_cambial_final

# --- Adição da Coluna de Totais e Margens ---

dre_df['Total'] = dre_df[period_cols].sum(axis=1)

# Recalcula a Margem EBITDA (%) para a coluna Total
total_receita_liquida = dre_df.loc['Receita Líquida (R$)', 'Total']
total_ebitda = dre_df.loc['EBITDA (R$)', 'Total']
dre_df.loc['Margem EBITDA (%)', 'Total'] = (
                                                   total_ebitda / total_receita_liquida) * 100 if total_receita_liquida != 0 else 0.0

# --- DEFINIÇÃO DE VARIÁVEIS PARA AS PRÓXIMAS SEÇÕES ---
exposicao_total = dre_df.loc['Exposição Cambial Final (R$)', period_cols].sum()
dados = df_premissas_editado.set_index("Premissa")  # DataFrame de Premissas (Input)
resultado = dre_df  # DataFrame de Resultados (DRE Base)
ebitda_total = total_ebitda
margem_ebitda = dre_df.loc['Margem EBITDA (%)', 'Total']
dre_rows = dre_df.index  # Linhas da DRE
base_pct_row = "Receita Líquida (R$)"  # Linha base para %

# --- FIM DA DEFINIÇÃO DE VARIÁVEIS ---

# --- 3. EXIBIÇÃO FINAL CORRIGIDA E FORMATADA ---

with st.expander("Visualização Detalhada da DRE e Exposição Cambial (Contas x Períodos)", expanded=True):
    st.markdown("### DRE Gerencial e Análise de Exposição (Cenário Base)")

    # Colunas para formatação
    all_cols = period_cols + ['Total']

    # Aplica formatação e negrito
    st.dataframe(
        dre_df.style
        # Aplica negrito e cor de fundo (row-style)
        .apply(apply_row_styles, axis=1, synthetic_list=SYNTHETIC_ACCOUNTS)

        # Formata moeda R$ (no padrão BRL)
        .format(
            {col: format_currency_brl for col in all_cols},
            # Seleciona todas as linhas que contêm 'R$' mas não 'Margem'
            subset=pd.IndexSlice[[i for i in dre_df.index if "R$" in i and "Margem" not in i], all_cols]
        )
        # Formata porcentagem
        .format(
            {col: format_percent_brl for col in all_cols},
            subset=pd.IndexSlice['Margem EBITDA (%)', all_cols]
        )
    )

    # --- INSERÇÃO DOS CARTÕES DE RESUMO ---
    st.markdown("### Resumo das Principais Métricas (Período Total)")

    rl_total = dre_df.loc['Receita Líquida (R$)', 'Total']
    ebitda_total_kpi = dre_df.loc['EBITDA (R$)', 'Total']
    margem_total_kpi = dre_df.loc['Margem EBITDA (%)', 'Total']
    exposicao_final_total_kpi = exposicao_total

    col_kpi_1, col_kpi_2, col_kpi_3, col_kpi_4 = st.columns(4)

    with col_kpi_1:
        st.metric(
            label="Receita Líquida Total (R$)",
            value=format_currency_brl(rl_total)
        )

    with col_kpi_2:
        st.metric(
            label="EBITDA Total (R$)",
            value=format_currency_brl(ebitda_total_kpi)
        )

    with col_kpi_3:
        st.metric(
            label="Margem EBITDA Total (%)",
            value=format_percent_brl(margem_total_kpi)
        )

    with col_kpi_4:
        #delta_label = f"{'Posição Long (Compra de Câmbio)' if exposicao_final_total_kpi >= 0 else 'Posição Short (Venda de Câmbio)'}"
        st.metric(
            label="Exposição Cambial Final (Net)",
            value=format_currency_brl(exposicao_final_total_kpi),
            #delta=delta_label
        )
    # --- FIM DA INSERÇÃO DOS CARTÕES DE RESUMO ---

st.markdown("---")

# ========================================
# SEÇÃO 2: Análise Histórica e Parâmetros
# ========================================

dias_uteis_por_mes = 22
retorno_mensal_auto = 0.0
volatilidade_mensal_auto = 0.01
cotacoes = None
fonte_dados = "N/A"

with st.expander("2. Análise Histórica de Câmbio", expanded=False):
    fonte_dados_selecionada = st.radio(
        "Selecione a fonte dos dados históricos:",
        ("Banco Central (SGS)", "Yahoo Finance"),
        index=0, horizontal=True, key="fonte_dados_radio"
    )
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        moeda = st.selectbox("Selecione a moeda de exposição:", ["USD", "EUR", "JPY", "CNY"])
    with col2:
        data_inicial_default = datetime.today() - pd.DateOffset(days=30)
        data_inicial = st.date_input("Data inicial:", value=data_inicial_default)
    with col3:
        data_final = st.date_input("Data final:", value=datetime.today())

    moedas_sgs = {"USD": 1, "EUR": 21619, "JPY": 21623, "CNY": 21627}
    yf_tickers = {"USD": "BRL=X", "EUR": "EURBRL=X", "JPY": "JPYBRL=X", "CNY": "CNYBRL=X"}

    erro_api = None
    progress_bar = st.progress(0, text="Aguardando busca de dados...")

    if data_inicial and data_final and data_inicial < data_final:
        try:
            cotacoes_temp = None
            if fonte_dados_selecionada == "Banco Central (SGS)":
                progress_bar.progress(20, text="Buscando dados no Banco Central (SGS)...")
                codigo_sgs = moedas_sgs.get(moeda)
                if not codigo_sgs: raise ValueError(f"Código SGS não encontrado para a moeda {moeda}")
                cotacoes_temp = sgs.get({'Cotação': codigo_sgs}, start=data_inicial, end=data_final)
                progress_bar.progress(70, text="Processando dados do BCB...")
                if cotacoes_temp is None or cotacoes_temp.empty: raise ValueError(
                    "Não foram retornados dados do BCB para o período selecionado.")
                fonte_dados = "Banco Central (SGS)"

                if isinstance(cotacoes_temp.columns, pd.MultiIndex):
                    cotacoes_temp.columns = cotacoes_temp.columns.droplevel(1)

            elif fonte_dados_selecionada == "Yahoo Finance":
                progress_bar.progress(20, text="Buscando dados no Yahoo Finance...")
                ticker = yf_tickers.get(moeda)
                if not ticker: raise ValueError(f"Ticker do Yahoo Finance não encontrado para a moeda {moeda}")

                ticker_data = yf.Ticker(ticker)
                yf_data = ticker_data.history(start=data_inicial.strftime('%Y-%m-%d'),
                                              end=data_final.strftime('%Y-%m-%d'))

                progress_bar.progress(70, text="Processando dados do YF...")
                if yf_data.empty: raise ValueError(f"Não foram encontrados dados no YF para {ticker} no período.")

                price_col = 'Close' if 'Close' in yf_data.columns else 'Adj Close'
                if price_col not in yf_data.columns: raise ValueError(
                    "Colunas 'Close' ou 'Adj Close' não encontradas nos dados do YF.")

                cotacoes_temp = pd.DataFrame(yf_data[price_col]).rename(columns={price_col: 'Cotação'})

                if pd.api.types.is_datetime64_any_dtype(cotacoes_temp.index) and cotacoes_temp.index.tz is not None:
                    cotacoes_temp.index = cotacoes_temp.index.tz_localize(None)
                fonte_dados = "Yahoo Finance"

            if cotacoes_temp is None: raise ValueError("Nenhuma fonte de dados foi buscada.")

            if 'Cotação' not in cotacoes_temp.columns:
                raise KeyError("Não foi possível identificar a coluna 'Cotação' após a busca. Colunas: " + str(
                    cotacoes_temp.columns))

            cotacoes = cotacoes_temp.dropna()
            if cotacoes.empty: raise ValueError(f"Dados de {fonte_dados} vazios após primeiro dropna.")

            progress_bar.progress(90, text="Calculando retornos e estatísticas...")
            cotacoes["Retorno Diário"] = np.log(cotacoes["Cotação"] / cotacoes["Cotação"].shift(1))
            cotacoes = cotacoes.dropna()

            if cotacoes.empty: raise ValueError(f"Dados de {fonte_dados} vazios após cálculo de retornos.")

            st.success(f"Dados históricos carregados com sucesso de: **{fonte_dados}**")
            progress_bar.progress(100, text="Análise histórica concluída!")
            progress_bar.empty()

            st.markdown(f"### Gráficos de Cotações e Retornos ({fonte_dados})")
            media_cotacao = cotacoes["Cotação"].mean()
            fig_cotacao = px.line(cotacoes, y="Cotação", title=f"Cotação diária - {moeda}/BRL")
            fig_cotacao.add_hline(y=media_cotacao, line_dash="dash", line_color="red",
                                  annotation_text=f"Média: {media_cotacao:,.2f}")
            fig_cotacao.update_layout(template="plotly_white")
            fig_retorno = px.line(cotacoes, y="Retorno Diário",
                                  title="Retornos Logarítmicos Diários do Câmbio")
            fig_retorno.update_layout(template="plotly_white")
            col1, col2 = st.columns(2)
            col1.plotly_chart(fig_cotacao, use_container_width=True)
            col2.plotly_chart(fig_retorno, use_container_width=True)

            dias_uteis_por_mes = 22
            media_diaria = cotacoes["Retorno Diário"].mean()
            volatilidade_diaria = cotacoes["Retorno Diário"].std()
            if volatilidade_diaria == 0: volatilidade_diaria = 0.0001

            retorno_mensal_auto = np.exp(dias_uteis_por_mes * (media_diaria - 0.5 * volatilidade_diaria ** 2)) - 1

            # --- CORREÇÃO DE TYPO (volatility_diaria -> volatilidade_diaria) ---
            volatilidade_mensal_auto = volatilidade_diaria * np.sqrt(dias_uteis_por_mes)
            # --------------------------------------------------------------------

            cot_min = cotacoes["Cotação"].min()
            cot_med = cotacoes["Cotação"].mean()
            cot_max = cotacoes["Cotação"].max()

            st.markdown("### Estatísticas Descritivas (Histórico)")
            col1, col2, col3 = st.columns(3)
            col1.metric("Cotação Mínima", f"{cot_min:,.4f}")
            col2.metric("Cotação Média", f"{cot_med:,.4f}")
            col3.metric("Cotação Máxima", f"{cot_max:,.4f}")

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Retorno Médio Diário", f"{media_diaria * 100:.4f}%")
            col2.metric("Volatilidade Diária", f"{volatilidade_diaria * 100:.4f}%")
            col3.metric("Retorno Médio Mensal (Auto)", f"{retorno_mensal_auto * 100:.2f}%")
            col4.metric("Volatilidade Mensal (Auto)", f"{volatilidade_mensal_auto * 100:.2f}%")

            with st.expander("Clique para ver a Tabela de Cotações e Retornos Diários"):
                cotacoes_ordenadas = cotacoes.sort_index(ascending=False)
                st.dataframe(cotacoes_ordenadas.style.format({
                    "Cotação": "{:,.4f}", "Retorno Diário": "{:.4%}"
                }))


                def to_excel(df):
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        df.to_excel(writer, index=True, sheet_name='Cotações')
                    return output.getvalue()


                excel_data = to_excel(cotacoes_ordenadas)
                st.download_button(
                    label="📥 Exportar para Excel", data=excel_data,
                    file_name=f"Cotacoes_{moeda}_{data_inicial}_{data_final}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

        except (requests.exceptions.RequestException, Exception) as e:
            progress_bar.empty()
            st.error(f"Erro ao carregar ou processar dados históricos: {e}")


    else:
        progress_bar.empty()
        st.warning("Por favor, selecione uma data inicial e final válidas para executar as análises.")

# ========================================
# SEÇÃO 3: Análise Paramétrica (VaR)
# ========================================

with st.expander("3. Análise Paramétrica (VaR)", expanded=False):
    st.markdown("### Parâmetros de Entrada para o Cálculo")
    opcoes_radio = []
    if cotacoes is not None and not cotacoes.empty:
        opcoes_radio.append("Usar estatísticas automáticas (calculadas acima)")
    opcoes_radio.append("Inserir manualmente os parâmetros")
    indice_default = 0 if (cotacoes is not None and not cotacoes.empty) else 0

    usar_dados_auto = st.radio(
        "Selecione a fonte dos dados de retorno e volatilidade:",
        opcoes_radio, index=indice_default, key="radio_params_main"
    )
    if usar_dados_auto == "Usar estatísticas automáticas (calculadas acima)":
        retorno_mensal = retorno_mensal_auto
        # --- CORREÇÃO DO NAMERROR: volatility_mensal_auto -> volatilidade_mensal_auto ---
        volatilidade_mensal = volatilidade_mensal_auto
        # ---------------------------------------------------------------------------------
    else:
        if cotacoes is None or cotacoes.empty:
            st.info("Dados automáticos não disponíveis. Insira os parâmetros manualmente.")
        col1, col2 = st.columns(2)
        retorno_mensal = col1.number_input(
            "Informe o Retorno Médio Mensal (em %):",
            min_value=-100.0, max_value=100.0, value=float(retorno_mensal_auto * 100), step=0.01, format="%.2f",
            key="ret_manual_main"
        ) / 100
        volatilidade_mensal = col2.number_input(
            "Informe a Volatilidade Mensal (em %):",
            min_value=0.0, max_value=100.0, value=float(volatilidade_mensal_auto * 100), step=0.01, format="%.2f",
            key="vol_manual_main"
        ) / 100

    volatilidade_mensal = max(volatilidade_mensal, 0.0001)

    st.markdown("### Parâmetros do Cálculo do VaR e Indicadores")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        nivel_confianca = st.selectbox("Nível de confiança:", ["95%", "99%"], key="nc_main")
    with col2:
        dias_uteis_var = st.number_input("Dias úteis para VaR:", min_value=1, max_value=252, value=21,
                                         key="du_var_main")
    with col3:
        ebitda_mensal = st.number_input("EBITDA Médio Mensal (R$):", min_value=0.0,
                                        value=total_ebitda / num_periodos if num_periodos > 0 else 0.0, step=1000.0,
                                        format="%.2f", key="ebitda_mensal_main")
    with col4:
        pl = st.number_input("Patrimônio Líquido (PL) (R$):", min_value=0.0, step=1000.0, format="%.2f", key="pl_main")

    z_score = 1.65 if nivel_confianca == "95%" else 2.33

    if dias_uteis_por_mes == 0: dias_uteis_por_mes = 22
    volatilidade_diaria_equivalente = volatilidade_mensal / np.sqrt(dias_uteis_por_mes)

    # --- CÁLCULO CORRIGIDO DO VAR ---
    var_value = abs(exposicao_total) * volatilidade_diaria_equivalente * z_score * np.sqrt(dias_uteis_var)
    # --- FIM DA CORREÇÃO ---

    st.markdown("### Indicadores de Risco (VaR Paramétrico)")
    col1, col2, col3 = st.columns(3)

    col1.metric(f"Value at Risk (VaR) {nivel_confianca}", formatar_brl(var_value))

    relacao = (var_value / ebitda_mensal) if ebitda_mensal > 0 else 0.0
    col2.metric("VaR / EBITDA Médio Mensal", formatar_pct(relacao * 100))

    relacao_pl = (var_value / pl) if pl > 0 else 0.0
    col3.metric("VaR / Patrimônio Líquido (PL)", formatar_pct(relacao_pl * 100))

    with st.expander("Detalhamento dos Indicadores de Risco"):
        st.markdown(f"""
        <div class="insight-box">
        <strong>Value at Risk (VaR): {formatar_brl(var_value)}</strong><br>
        Com {nivel_confianca} de confiança, estima-se que a perda máxima na exposição cambial ({formatar_brl(exposicao_total)}) 
        seja de até {formatar_brl(var_value)} em {dias_uteis_var} dias úteis, 
        considerando a volatilidade mensal de {volatilidade_mensal * 100:.2f}%.
        </div>
        """, unsafe_allow_html=True)

        if ebitda_mensal > 0:
            st.markdown(f"""
            <div class="insight-box">
            <strong>VaR / EBITDA: {formatar_pct(relacao * 100)}</strong><br>
            A razão entre o VaR e o EBITDA indica qual percentual do EBITDA médio mensal 
            poderia ser comprometido em um cenário adverso.
            </div>
            """, unsafe_allow_html=True)
        if pl > 0:
            st.markdown(f"""
            <div class="insight-box">
            <strong>VaR / PL: {formatar_pct(relacao_pl * 100)}</strong><br>
            A razão entre o VaR e o PL mostra a proporção do capital próprio 
            que poderia ser impactada pela exposição cambial.
            </div>
            """, unsafe_allow_html=True)

    if cotacoes is not None and not cotacoes.empty:
        # --- CÓDIGO PARA VISUALIZAR VA R (TAIL RISK SHADING) ---
        st.markdown("### Distribuição dos Retornos e **Zona de Risco de Cauda (VaR)**")

        # VaR percentual (o ponto crítico na distribuição)
        var_percentual = -z_score * volatilidade_diaria_equivalente * np.sqrt(dias_uteis_var)

        # 1. Cria o histograma com Plotly Express
        fig_hist = px.histogram(
            cotacoes, x="Retorno Diário", nbins=50,
            title="Distribuição dos Retornos Logarítmicos Diários de Câmbio",
            opacity=0.8, histnorm='probability density'
        )

        # 2. Define o limite inferior e adiciona a Sombra (Tail Risk)
        min_retorno = cotacoes["Retorno Diário"].min() - 0.001

        fig_hist.add_shape(
            type="rect",
            xref="x", yref="paper",
            x0=min_retorno,
            y0=0, y1=1,
            x1=var_percentual,
            line=dict(width=0),
            fillcolor="red",
            opacity=0.2,
            layer="below"
        )

        # 3. Adiciona a Linha do VaR (Linha de Corte)
        fig_hist.add_vline(
            x=var_percentual,
            line_dash="dash",
            line_color="red",
            annotation_text=f"VaR {nivel_confianca}: {var_percentual * 100:.2f}% (Limite de Perda)",
            annotation_position="top right"
        )

        # 4. Ajustes Finais de Layout
        fig_hist.update_layout(
            template="plotly_white",
            xaxis_title="Retorno Diário Logarítmico",
            yaxis_title="Densidade de Probabilidade",
            bargap=0.01
        )
        st.plotly_chart(fig_hist, use_container_width=True)
        # --- FIM DO CÓDIGO CORRIGIDO ---
    else:
        st.markdown("_(Histograma de retornos não disponível)_")

st.markdown("---")

# ========================================
# SEÇÃO 4: Análise EBITDA @Risk (REESTRUTURADA)
# ========================================

if 'dados' in locals() and 'resultado' in locals() and 'ebitda_total' in locals():
    # REQUISITO 2: Mover Seção 4 para um expander
    with st.expander("4. Análise EBITDA @Risk (Stress Test)", expanded=True):

        # --- CORREÇÃO DE TIPAGEM (USANDO PD.TO_NUMERIC) ---
        # Opção 2 (VaR Analítico)
        cot_med_usuario = dados.loc["Cotação USD/BRL", colunas].apply(
            pd.to_numeric, errors='coerce'
        ).mean() if not dados.empty and "Cotação USD/BRL" in dados.index else 0.0
        # ----------------------------------------------------

        if cot_med_usuario == 0 and cotacoes is not None and not cotacoes.empty:
            cot_med_usuario = cotacoes["Cotação"].mean()
        elif cot_med_usuario == 0:
            cot_med_usuario = 1.0  # Fallback

        if 'retorno_mensal' in locals() and 'volatilidade_mensal' in locals() and 'z_score' in locals():
            retorno_minimo_var = -z_score * volatilidade_mensal + retorno_mensal
            cambio_minimo_var = max(0.01, cot_med_usuario * (1 + retorno_minimo_var)) if cot_med_usuario > 0 else 0.01
        else:
            retorno_minimo_var = 0.0
            cambio_minimo_var = cot_med_usuario * 0.95 if cot_med_usuario > 0 else 1.0  # Fallback

        # --- CORREÇÃO DE ESCOPO: Selecionar apenas as colunas de período ---
        # Opção 1 (Goal Seek)
        receita_total_usd = (dados.loc["Preço de Venda (USD)", colunas].astype(float) * dados.loc[
            "Quantidade Vendida (Unid)", colunas].astype(
            float)).sum() if not dados.empty else 0.0
        # ------------------------------------------------------------------

        # Custos Fixos Totais da DRE Base
        deducoes_total_rs = resultado.loc[
            "Deduções sobre Vendas (R$)", "Total"] if "Total" in resultado.columns else 0.0
        custos_rs = resultado.loc["Custos (R$)", "Total"] if "Total" in resultado.columns else 0.0
        despesas_rs = resultado.loc["Despesas Operacionais (R$)", "Total"] if "Total" in resultado.columns else 0.0
        receita_domestica_rs = resultado.loc[
            "  Receita Mercado Interno (R$)", "Total"] if "Total" in resultado.columns else 0.0

        # Custos que NÃO variam com o câmbio (para o cálculo Goal Seek)
        custos_fixos_operacionais_rs = custos_rs + despesas_rs
        # Custos Totais (para a fórmula do câmbio) = Deduções + Custos Fixos Operacionais
        custos_fixos_totais_rs = deducoes_total_rs + custos_fixos_operacionais_rs

        cambio_minimo_meta = 0.01
        ebitda_meta_valor_abs = 0.0
        ebitda_meta_pct = 0.0

        # Seletor principal
        metodo_ear = st.radio(
            "Selecione o método para definir o Cenário Adverso:",
            [
                "1. Definir Câmbio via Meta de EBITDA (Goal Seek)",
                f"2. Usar Câmbio Mínimo Analítico FX (Fonte: {fonte_dados})",
                "3. Inserir Câmbio Manualmente (por Período)"
            ],
            key="metodo_ear_radio"
        )

        cambio_aplicado = 0.0

        # Bloco 1: Meta de EBITDA
        if metodo_ear.startswith("1."):
            st.markdown("### 1. Cálculo Inverso: Câmbio Mínimo via Meta de EBITDA")
            ebitda_meta_tipo = st.radio("Definir meta de EBITDA por:",
                                        ["Valor Absoluto (R$)", "Percentual da Receita Líquida Adversa"],
                                        index=0, key="meta_tipo_main", horizontal=True)

            st.info("""
            **Como funciona o Cálculo Inverso (Goal Seek):**
            Esta ferramenta calcula o câmbio *exato* (break-even) necessário para atingir sua meta de EBITDA, 
            considerando seus custos fixos em BRL e sua receita em USD.
            """)

            if ebitda_meta_tipo == "Valor Absoluto (R$)":
                ebitda_meta_valor_abs = st.number_input("1. Meta de EBITDA Mínimo (R$):",
                                                        value=ebitda_total * 0.9 if ebitda_total is not None else 0.0,
                                                        format="%.2f", step=10000.0, key="meta_abs_main")

                # CÁLCULO DO GOAL SEEK - VALOR ABSOLUTO
                # ----------------------------------------------------
                receita_bruta_total_min = ebitda_meta_valor_abs + custos_fixos_totais_rs
                receita_me_necessaria_rs = receita_bruta_total_min - receita_domestica_rs

                if receita_total_usd > 0:
                    cambio_minimo_meta = max(0.01, receita_me_necessaria_rs / receita_total_usd)
                else:
                    cambio_minimo_meta = 0.01
                # ----------------------------------------------------


            else:
                ebitda_meta_pct = st.number_input("1. Meta de Margem EBITDA Mínima (%):",
                                                  value=max(0.0,
                                                            margem_ebitda - 5.0) if margem_ebitda is not None else 5.0,
                                                  format="%.2f", step=1.0, key="meta_pct_main") / 100.0

                # CÁLCULO DO GOAL SEEK - PERCENTUAL
                # ----------------------------------------------------
                # Formula: Rec Liq Nec = Custos Fixos Operacionais / (1 - Pct Meta)
                if (1 - ebitda_meta_pct) > 0 and receita_total_usd > 0:
                    rec_liq_necessaria = custos_fixos_operacionais_rs / (1 - ebitda_meta_pct)
                    receita_bruta_total_min = rec_liq_necessaria + deducoes_total_rs
                    receita_me_necessaria_rs = receita_bruta_total_min - receita_domestica_rs

                    cambio_minimo_meta = max(0.01, receita_me_necessaria_rs / receita_total_usd)
                    # Recalcula valor absoluto para confirmação
                    ebitda_meta_valor_abs = rec_liq_necessaria - custos_fixos_operacionais_rs
                else:
                    cambio_minimo_meta = 0.01
                    ebitda_meta_valor_abs = 0.0
                # ----------------------------------------------------

            st.metric(f"Câmbio Mínimo Necessário (via Meta)", f"R$ {cambio_minimo_meta:,.4f}",
                      help=f"Câmbio necessário para atingir um EBITDA total de {formatar_brl(ebitda_meta_valor_abs)}")

            # REQ 1: DataFrame de Detalhamento do Goal Seek
            with st.expander("Ver Composição do Cálculo (Goal Seek)"):

                # Variáveis de Custo / Rec
                custos_fixos_op_rs = custos_rs + despesas_rs
                receita_exportacao_usd_total = receita_total_usd

                if ebitda_meta_tipo == "Valor Absoluto (R$)":
                    # 1. Meta de EBITDA Mínimo (R$)
                    # 2. Custos Fixos Operacionais (Custos + Despesas) (R$)
                    # 3. Deduções sobre Vendas (R$)
                    # 4. Receita Bruta Total Mínima Necessária (R$) [1+2+3]
                    # 5. Receita Doméstica (R$) - NÃO EXPOSTA
                    # 6. Receita de Exportação Mínima Necessária (R$) [4-5]
                    # 7. Receita de Exportação (USD) [Exposição Bruta USD]
                    # 8. Câmbio Mínimo Calculado [6 / 7]

                    goal_seek_data = {
                        "Componente": [
                            "1. Meta de EBITDA Mínimo (R$)",
                            "2. Custos Fixos Operacionais (Custos + Despesas) (R$)",
                            "3. Deduções sobre Vendas (R$)",
                            "4. Receita Bruta Total Mínima Necessária (R$) [1+2+3]",
                            "5. Receita Doméstica (R$) - NÃO EXPOSTA",
                            "6. Receita de Exportação Mínima Necessária (R$) [4-5]",
                            "7. Receita de Exportação (USD) [Exposição Bruta USD]",
                            "8. Câmbio Mínimo Calculado [6 / 7]"
                        ],
                        "Valor": [
                            ebitda_meta_valor_abs,
                            custos_fixos_op_rs,
                            deducoes_total_rs,
                            receita_bruta_total_min,
                            receita_domestica_rs,
                            receita_me_necessaria_rs,
                            receita_exportacao_usd_total,
                            cambio_minimo_meta
                        ]
                    }
                else:  # Percentual
                    # 1. Meta de Margem EBITDA (%)
                    # 2. Custos Fixos Operacionais (Custos + Despesas) (R$)
                    # 3. Deduções sobre Vendas (R$)
                    # 4. Receita Doméstica (R$) - NÃO EXPOSTA
                    # 5. Receita de Exportação (USD) [Exposição Bruta USD]
                    # 6. Fator Custo Margem [1 / (1 - Pct Meta)]
                    # 7. Receita Líquida Necessária (R$) [2 * 6]
                    # 8. Receita Bruta Total Mínima Necessária (R$) [7+3]
                    # 9. Receita de Exportação Necessária (R$) [8-4]
                    # 10. Câmbio Mínimo Calculado [9 / 5]

                    fator_custo_margem = 1 / (1 - ebitda_meta_pct) if (1 - ebitda_meta_pct) > 0 else 0

                    goal_seek_data = {
                        "Componente": [
                            "1. Meta de Margem EBITDA (%)",
                            "2. Custos Fixos Operacionais (Custos + Despesas) (R$)",
                            "3. Deduções sobre Vendas (R$)",
                            "4. Receita Doméstica (R$) - NÃO EXPOSTA",
                            "5. Receita de Exportação (USD) [Exposição Bruta USD]",
                            "6. Fator Custo Margem [1 / (1 - Pct Meta)]",
                            "7. Receita Líquida Necessária (R$)",
                            "8. Receita Bruta Total Mínima Necessária (R$) [7+3]",
                            "9. Receita de Exportação Necessária (R$) [8-4]",
                            "10. Câmbio Mínimo Calculado [9 / 5]",
                            "EBITDA Meta (R$)"
                        ],
                        "Valor": [
                            ebitda_meta_pct * 100,
                            custos_fixos_op_rs,
                            deducoes_total_rs,
                            receita_domestica_rs,
                            receita_exportacao_usd_total,
                            fator_custo_margem,
                            rec_liq_necessaria,
                            receita_bruta_total_min,
                            receita_me_necessaria_rs,
                            cambio_minimo_meta,
                            ebitda_meta_valor_abs
                        ]
                    }
                df_goal_seek = pd.DataFrame(goal_seek_data)

                # Formata o DataFrame para exibição
                df_goal_seek_formatado = df_goal_seek.copy()
                for i in range(len(df_goal_seek_formatado)):
                    valor = df_goal_seek.iloc[i, 1]
                    componente = df_goal_seek.iloc[i, 0]

                    if "USD" in componente:
                        df_goal_seek_formatado.iloc[i, 1] = f"USD {valor:,.2f}".replace(",", "_").replace(".",
                                                                                                          ",").replace(
                            "_", ".")
                    elif "Câmbio" in componente:
                        df_goal_seek_formatado.iloc[i, 1] = f"R$ {valor:,.4f}".replace(",", "_").replace(".",
                                                                                                         ",").replace(
                            "_", ".")
                    elif "(%)" in componente:
                        df_goal_seek_formatado.iloc[i, 1] = formatar_pct(valor)
                    elif "Fator Custo Margem" in componente:
                        df_goal_seek_formatado.iloc[i, 1] = f"{valor:,.4f}".replace(",", "_").replace(".", ",").replace(
                            "_", ".")
                    else:
                        df_goal_seek_formatado.iloc[i, 1] = formatar_brl(valor)

                st.dataframe(df_goal_seek_formatado.set_index("Componente"), use_container_width=True)

            cambio_aplicado = cambio_minimo_meta

        # Bloco 2: VaR Analítico
        elif metodo_ear.startswith("2."):
            st.markdown(f"### 2. Câmbio Mínimo via VaR Analítico (Fonte: {fonte_dados})")

            st.info(f"""
            **Sobre este Cálculo (VaR Analítico):**
            Este método usa a volatilidade histórica ({volatilidade_mensal * 100:.2f}%) e o retorno médio ({retorno_mensal * 100:.2f}%) 
            para calcular o 5º percentil (ou 1º) do câmbio.

            **Atenção:** Se os dados históricos recentes tiverem uma forte tendência de alta (retorno/drift positivo),
            o cenário "adverso" (P5) pode ser um câmbio **mais alto (mais favorável)** do que o seu câmbio orçado.
            """)

            col1, col2, col3 = st.columns(3)
            col1.metric("Cotação Média (Orçada)", formatar_brl(cot_med_usuario))
            col2.metric(f"Retorno Mínimo ({nivel_confianca})", formatar_pct(retorno_minimo_var * 100))
            col3.metric(f"Câmbio Mínimo ({nivel_confianca})", f"R$ {cambio_minimo_var:,.4f}")
            cambio_aplicado = cambio_minimo_var

        # Bloco 3: Manual
        elif metodo_ear.startswith("3."):
            st.markdown("### 3. Câmbio Mínimo via Input Manual (por Período)")
            # Assegura que todas as variáveis são definidas
            cambio_base_series = dados.loc["Cotação USD/BRL", colunas].apply(pd.to_numeric, errors='coerce').fillna(0.0)

            df_cambio_manual = pd.DataFrame(data=[cambio_base_series * 0.95], index=["Câmbio Mínimo Manual"],
                                            columns=colunas)
            cambio_manual_input = st.data_editor(df_cambio_manual, use_container_width=True, height=80,
                                                 key="cambio_manual_main")
            cambio_aplicado = cambio_manual_input.loc["Câmbio Mínimo Manual"].astype(float)

        # --- Cálculo e Exibição do DRE Adverso (Baseado na seleção acima) ---
        st.markdown("---")
        st.markdown("### Demonstrativo de Resultados (Cenário Adverso Selecionado)")

        # --- CORREÇÃO AQUI: Adicionar 'Margem EBITDA (%)' ao required_rows_dre ---
        required_rows_dre = [
            "Receitas Operacionais (R$)", "  Receita em Moeda Estrangeira (R$)", "  Receita Mercado Interno (R$)",
            # RENOMEADO
            "Deduções sobre Vendas (R$)", "Receita Líquida (R$)", "Custos (R$)",
            "Despesas Operacionais (R$)", "EBITDA (R$)",
            "Margem EBITDA (%)",  # Linha adicionada
            "Exposição Financeira (R$)", "  Caixa no Exterior (R$ - Exp. em US$)",
            "  Empréstimos e Financiamentos (R$ - Exp. em US$)", "Exposição Cambial Líquida (R$)",
            "  Hedge Contratado - Comprado (R$)", "  Hedge Contratado - Vendido (R$)",
            "Exposição Cambial Final (R$)"
        ]
        # -----------------------------------------------------------------------

        map_input_to_output = {
            "Receita Mercado Interno (R$)": "  Receita Mercado Interno (R$)",
            "Deduções sobre Vendas (R$)": "Deduções sobre Vendas (R$)",
            "Custos (R$)": "Custos (R$)",
            "Despesas Operacionais (R$)": "Despesas Operacionais (R$)",
            "Caixa no Exterior (R$ - Exp. em US$)": "  Caixa no Exterior (R$ - Exp. em US$)",
            "Empréstimos e Financiamentos (R$ - Exp. em US$)": "  Empréstimos e Financiamentos (R$ - Exp. em US$)",
            "Hedge Contratado - Comprado (R$)": "  Hedge Contratado - Comprado (R$)",
            "Hedge Contratado - Vendido (R$)": "  Hedge Contratado - Vendido (R$)"
        }

        resultado_scenario = pd.DataFrame(0.0, index=required_rows_dre, columns=colunas)
        ebitda_min_total, receita_min_total, ear_loss = 0.0, 0.0, 0.0
        margem_ebitda_min = 0.0

        if not dados.empty and not resultado.isnull().values.any():
            try:
                # Copia linhas em R$ (Mercado Interno, Custos, Despesas, Financeiro)
                for input_row, output_row in map_input_to_output.items():
                    if input_row in dados.index and output_row in resultado_scenario.index:
                        # Puxa APENAS as colunas de período
                        resultado_scenario.loc[output_row, colunas] = dados.loc[input_row, colunas].astype(float)

                # Cálculo Receita Exportação (em R$)
                if isinstance(cambio_aplicado, float):
                    cambio_aplicado_series = pd.Series([cambio_aplicado] * num_meses, index=colunas)
                else:
                    cambio_aplicado_series = cambio_aplicado  # É uma Série (Manual)

                preco_usd_series = dados.loc["Preço de Venda (USD)", colunas].astype(float)
                qtd_series = dados.loc["Quantidade Vendida (Unid)", colunas].astype(float)

                receita_exportacao_adversa = preco_usd_series * qtd_series * cambio_aplicado_series
                resultado_scenario.loc[
                    "  Receita em Moeda Estrangeira (R$)", colunas] = receita_exportacao_adversa  # RENOMEADO

                # Cálculos sintéticos e financeiros
                resultado_scenario.loc["Receitas Operacionais (R$)", colunas] = (
                        resultado_scenario.loc["  Receita em Moeda Estrangeira (R$)", colunas] +
                        resultado_scenario.loc["  Receita Mercado Interno (R$)", colunas]
                )
                resultado_scenario.loc["Receita Líquida (R$)", colunas] = (
                        resultado_scenario.loc["Receitas Operacionais (R$)", colunas] -
                        resultado_scenario.loc["Deduções sobre Vendas (R$)", colunas]
                )
                ebitda_series = (
                        resultado_scenario.loc["Receita Líquida (R$)", colunas] -
                        resultado_scenario.loc["Custos (R$)", colunas] -
                        resultado_scenario.loc["Despesas Operacionais (R$)", colunas]
                )
                resultado_scenario.loc["EBITDA (R$)", colunas] = ebitda_series

                # --- CORREÇÃO AQUI: Cálculo e inserção da Margem percentual ---
                margem_ebitda_series = np.where(resultado_scenario.loc["Receita Líquida (R$)", colunas] != 0,
                                                (ebitda_series / resultado_scenario.loc[
                                                    "Receita Líquida (R$)", colunas]) * 100,
                                                0.0
                                                )
                resultado_scenario.loc["Margem EBITDA (%)", colunas] = margem_ebitda_series
                # ---------------------------------------------------------------

                # Exposição
                caixa_ext = resultado_scenario.loc["  Caixa no Exterior (R$ - Exp. em US$)", colunas]
                emprestimos = resultado_scenario.loc["  Empréstimos e Financiamentos (R$ - Exp. em US$)", colunas]
                hedge_comprado = resultado_scenario.loc["  Hedge Contratado - Comprado (R$)", colunas]
                hedge_vendido = resultado_scenario.loc["  Hedge Contratado - Vendido (R$)", colunas]

                exposicao_operacional = resultado_scenario.loc[
                    "  Receita em Moeda Estrangeira (R$)", colunas]  # RENOMEADO
                exposicao_cambial_liquida = exposicao_operacional + caixa_ext - emprestimos
                resultado_scenario.loc["Exposição Cambial Líquida (R$)", colunas] = exposicao_cambial_liquida

                resultado_scenario.loc["Exposição Cambial Final (R$)", colunas] = (
                        exposicao_cambial_liquida + (hedge_comprado - hedge_vendido)
                )

                # Totais
                resultado_scenario['Total'] = resultado_scenario[colunas].sum(axis=1)

                # Recalcula a Margem Total para a coluna Total
                total_receita_liq_adversa = resultado_scenario.loc["Receita Líquida (R$)", "Total"]
                ebitda_min_total = resultado_scenario.loc["EBITDA (R$)", "Total"]
                resultado_scenario.loc["Margem EBITDA (%)", "Total"] = (
                                                                                   ebitda_min_total / total_receita_liq_adversa) * 100 if total_receita_liq_adversa != 0 else 0.0

                receita_min_total = total_receita_liq_adversa
                ear_loss = ebitda_total - ebitda_min_total
                margem_ebitda_min = resultado_scenario.loc[
                    "Margem EBITDA (%)", "Total"]  # Garante que a variável seja a total


            except (TypeError, ValueError, KeyError, AttributeError) as e:
                st.error(f"Erro ao calcular DRE Adverso: {e}")
                resultado_scenario.iloc[:, :] = 0.0
        else:
            st.warning("Aguardando DRE Base ou premissas.")
            resultado_scenario.iloc[:, :] = 0.0

        st.markdown("### Totais do Cenário Adverso vs Base")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("EBITDA Total (Base)", formatar_brl(ebitda_total))

        # EBITDA Sem Hedge
        delta_ebitda_valor = ebitda_min_total - ebitda_total
        delta_ebitda_formatado_brl = formatar_brl(delta_ebitda_valor)
        col2.metric("EBITDA Total (Sem Hedge)", formatar_brl(ebitda_min_total),
                    delta=f"{delta_ebitda_valor:.2f}",
                    delta_color="normal",
                    help=f"Variação vs Base: {delta_ebitda_formatado_brl}")

        # EBITDA @Risk (Perda)
        delta_pct_valor = (delta_ebitda_valor / ebitda_total * 100) if ebitda_total != 0 else 0.0
        col3.metric("EBITDA @Risk (Perda)", formatar_brl(ear_loss),
                    delta=f"{delta_pct_valor:.1f}%",
                    delta_color="normal",
                    help="Variação percentual vs Base")

        # Margem Adversa
        delta_margem_valor = margem_ebitda_min - margem_ebitda
        col4.metric("Margem EBITDA (Adversa)", formatar_pct(margem_ebitda_min),
                    delta=f"{delta_margem_valor:.1f} p.p.",
                    delta_color="normal",
                    help="Variação em pontos percentuais vs Base")

        with st.expander("Ver Demonstrativo Detalhado (Cenário Adverso)"):
            resultado_scenario_formatado = resultado_scenario.copy()
            for col in colunas:
                resultado_scenario_formatado[col] = resultado_scenario_formatado[col].apply(formatar_brl)
            resultado_scenario_formatado["Total"] = resultado_scenario_formatado["Total"].apply(formatar_brl)

            # --- CORREÇÃO AQUI: Aplicar format_percent_brl (formatar_pct) APENAS na linha Margem EBITDA (%) ---
            all_cols_data = colunas + ['Total']
            resultado_scenario_formatado.loc['Margem EBITDA (%)', all_cols_data] = resultado_scenario_formatado.loc[
                'Margem EBITDA (%)', all_cols_data].apply(formatar_pct)
            # ------------------------------------------------------------------------------------

            # Aplica negrito nas linhas chave
            st.dataframe(
                resultado_scenario_formatado.style.apply(
                    lambda s: ["font-weight: bold;" if s.name in ["Receita Líquida (R$)", "EBITDA (R$)"] else "" for _
                               in
                               s],
                    axis=1
                ),
                use_container_width=True
            )
else:
    st.warning("Seção 4: O DRE Base (Seção 2) não foi calculado corretamente.")

st.markdown("---")

# ========================================
# SEÇÃO 5: Simulação de Hedge (Cenário Adverso)
# ========================================

if 'resultado_scenario' in locals() and 'resultado' in locals() and 'ebitda_total' in locals():
    with st.expander("5. Simulação de Hedge (Cenário Adverso)", expanded=False):

        colunas_seguras = [col for col in colunas if col in resultado.columns and col in resultado_scenario.columns]

        if not colunas_seguras:
            st.warning("Cenário Adverso (Seção 4) não foi calculado ou as colunas não são compatíveis.")
        else:
            # Garante que o index é 'Conta' e seleciona apenas as colunas de período
            ebitda_base_safe = resultado.loc["EBITDA (R$)", colunas_seguras].fillna(0).astype(float)
            ebitda_adverso_safe = resultado_scenario.loc["EBITDA (R$)", colunas_seguras].fillna(0).astype(float)

            if ebitda_base_safe.sum() == 0 and ebitda_adverso_safe.sum() == 0:
                st.warning("DRE Base e/ou Cenário Adverso estão zerados. A simulação de Hedge não pode ser executada.")
            else:
                ebitda_comparativo = pd.DataFrame({
                    "EBITDA Base (R$)": ebitda_base_safe,
                    "EBITDA Sem Hedge (R$)": ebitda_adverso_safe
                })
                ebitda_comparativo["EaR (Δ R$)"] = (
                        ebitda_comparativo["EBITDA Base (R$)"] - ebitda_comparativo["EBITDA Sem Hedge (R$)"])
                ebitda_comparativo["EaR (%)"] = np.where(ebitda_comparativo["EBITDA Base (R$)"] != 0, (
                        ebitda_comparativo["EaR (Δ R$)"] / ebitda_comparativo["EBITDA Base (R$)"] * 100), 0.0)
                df_plot = ebitda_comparativo.copy()

                st.markdown("### Nível de Hedge por Período (%)")

                # Paleta de cores para os gráficos
                color_map = {'EBITDA Base (R$)': '#0d47a1', 'EBITDA Sem Hedge (R$)': '#d9534f',
                             'EBITDA com Hedge (R$)': '#5cb85c'}

                hedge_default = 0
                sugerir_hedge = False  # CORRIGIDO: Inicializa a variável no escopo correto
                hedge_dict = {}
                if 'ebitda_meta_valor_abs' not in locals(): ebitda_meta_valor_abs = 0.0  # Garante que exista

                # Lógica para sugestão de Hedge
                if 'metodo_ear' in locals() and metodo_ear.startswith("1."):
                    sugerir_hedge = st.toggle(f"Sugerir hedge para atingir a Meta (definida na Seção 4)",
                                              key="toggle_sugestao")

                cols = st.columns(len(df_plot))

                if sugerir_hedge:
                    if 'ebitda_meta_tipo' in locals() and ebitda_meta_tipo == "Valor Absoluto (R$)":
                        ebitda_adverso_total_s5 = df_plot["EBITDA Sem Hedge (R$)"].sum()
                        ear_total_s5 = df_plot["EaR (Δ R$)"].sum()

                        gap_total = ebitda_meta_valor_abs - ebitda_adverso_total_s5

                        hedge_pct_sugerido = (gap_total / ear_total_s5 * 100) if ear_total_s5 != 0 else 0
                        hedge_default = int(np.clip(np.round(hedge_pct_sugerido / 10) * 10, 0, 100))
                        st.info(
                            f"Para atingir a meta total de {formatar_brl(ebitda_meta_valor_abs)}, é sugerido um hedge de ~{hedge_default}% em todos os períodos.")

                        for i, periodo in enumerate(df_plot.index):
                            with cols[i]:
                                hedge_dict[periodo] = st.slider(f"{periodo}", 0, 100, hedge_default, step=10,
                                                                key=f"hedge_{i}")

                    elif 'ebitda_meta_tipo' in locals() and ebitda_meta_tipo == "Percentual da Receita Líquida Adversa":
                        st.info(
                            f"Sugerindo hedge por período para atingir a meta de {ebitda_meta_pct * 100:.1f}% de Margem (calculado sobre a Receita Líquida Adversa de cada período).")
                        rec_liq_adv_plot = (
                            resultado_scenario.loc["Receita Líquida (R$)", colunas_seguras]).fillna(0)

                        for i, periodo in enumerate(df_plot.index):
                            rec_liq_adv_periodo = rec_liq_adv_plot.loc[periodo]
                            ebitda_adv_periodo = df_plot.loc[periodo, "EBITDA Sem Hedge (R$)"]
                            ear_periodo = df_plot.loc[periodo, "EaR (Δ R$)"]

                            ebitda_meta_periodo = ebitda_meta_pct * rec_liq_adv_periodo
                            gap_periodo = ebitda_meta_periodo - ebitda_adv_periodo

                            hedge_pct_sugerido = (gap_periodo / ear_periodo * 100) if ear_periodo != 0 else 0
                            hedge_default_periodo = int(
                                np.clip(np.round(hedge_pct_sugerido / 10) * 10, 0, 100))

                            with cols[i]:
                                hedge_dict[periodo] = st.slider(f"{periodo}", 0, 100, hedge_default_periodo, step=10,
                                                                key=f"hedge_{i}")

                # Se o toggle estiver OFF ou o método não for Goal Seek %
                if not sugerir_hedge:
                    for i, periodo in enumerate(df_plot.index):
                        with cols[i]:
                            hedge_dict[periodo] = st.slider(f"{periodo}", 0, 100, hedge_default, step=10,
                                                            key=f"hedge_{i}")

                # Continuação do cálculo do hedge...
                df_plot["Hedge (%)"] = df_plot.index.map(hedge_dict)
                df_plot["EBITDA com Hedge (R$)"] = (
                        df_plot["EBITDA Sem Hedge (R$)"] + (df_plot["Hedge (%)"] / 100 * df_plot["EaR (Δ R$)"]))
                df_plot["Impacto do Hedge (R$)"] = df_plot["EBITDA com Hedge (R$)"] - df_plot["EBITDA Sem Hedge (R$)"]
                df_plot["Impacto do Hedge (%)"] = np.where(df_plot["EBITDA Sem Hedge (R$)"] != 0, (
                        df_plot["Impacto do Hedge (R$)"] / df_plot["EBITDA Sem Hedge (R$)"] * 100), 0.0)

                st.markdown("### Comparativo Gráfico: EBITDA Base vs. Adverso vs. Com Hedge")
                df_plot_melt = df_plot.reset_index().melt(
                    id_vars='index',
                    value_vars=['EBITDA Base (R$)', 'EBITDA Sem Hedge (R$)', 'EBITDA com Hedge (R$)'],
                    var_name='Cenário', value_name='EBITDA (R$)'
                )
                df_plot_melt.rename(columns={'index': 'Período'}, inplace=True)

                fig_comp_hedge = px.bar(
                    df_plot_melt, x='Período', y='EBITDA (R$)', color='Cenário', barmode='group',
                    title='Comparativo: EBITDA Base vs. Adverso vs. Com Hedge',
                    color_discrete_map=color_map
                )
                fig_comp_hedge.update_layout(
                    xaxis_title="Período", yaxis_title="EBITDA (R$)", template="plotly_white",
                    yaxis_tickformat=".2s",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5)
                )
                st.plotly_chart(fig_comp_hedge, use_container_width=True)

                # --- INÍCIO DO BLOCO ATUALIZADO (SIMULAÇÃO DIÁRIA) ---

                if (cotacoes is not None and not cotacoes.empty):
                    try:
                        # 1. Obter premissas TOTAIS/MÉDIAS
                        price_usd_avg = dados.loc["Preço de Venda (USD)", colunas_seguras].astype(float).mean()
                        qty_total = dados.loc["Quantidade Vendida (Unid)", colunas_seguras].astype(float).sum()

                        # --- INCLUSÃO DA RECEITA DOMÉSTICA TOTAL ---
                        receita_domestica_total = resultado.loc["  Receita Mercado Interno (R$)", "Total"]
                        # ------------------------------------------

                        deducoes_rs_total = resultado.loc["Deduções sobre Vendas (R$)", "Total"]
                        custos_rs_total = resultado.loc["Custos (R$)", "Total"]
                        despesas_rs_total = resultado.loc["Despesas Operacionais (R$)", "Total"]
                        cotacao_base_avg = dados.loc["Cotação USD/BRL", colunas_seguras].apply(pd.to_numeric,
                                                                                               errors='coerce').mean()
                        if math.isnan(cotacao_base_avg) or cotacao_base_avg == 0: cotacao_base_avg = cotacoes[
                            "Cotação"].mean()

                        # 2. Calcular valores diários (desagregação)
                        num_dias_sim = len(cotacoes)
                        if num_dias_sim == 0: raise ValueError("Dados históricos (cotações) estão vazios.")

                        daily_qty = qty_total / num_dias_sim
                        daily_fixed_costs_rs = (custos_rs_total + despesas_rs_total) / num_dias_sim
                        daily_deducoes_rs = deducoes_rs_total / num_dias_sim

                        # --- CÁLCULO DA RECEITA DOMÉSTICA DIÁRIA ---
                        daily_revenue_domestic_rs = receita_domestica_total / num_dias_sim
                        # ------------------------------------------

                        # 3. Preparar o DataFrame de simulação
                        df_daily_sim = pd.DataFrame(index=cotacoes.index)
                        df_daily_sim['Cotação Diária'] = cotacoes['Cotação']

                        # 4. Calcular Receita Bruta Diária (AGORA INCLUINDO DOMÉSTICA)
                        receita_me_diaria = (price_usd_avg * daily_qty) * df_daily_sim['Cotação Diária']
                        df_daily_sim[
                            'Receita Bruta Diária (R$)'] = receita_me_diaria + daily_revenue_domestic_rs  # CORRIGIDO

                        df_daily_sim['Receita Líquida Diária (R$)'] = df_daily_sim[
                                                                          'Receita Bruta Diária (R$)'] - daily_deducoes_rs

                        # 5. Calcular EBITDAs Diários (R$)
                        df_daily_sim['EBITDA Sem Hedge Diário (R$)'] = df_daily_sim[
                                                                         'Receita Líquida Diária (R$)'] - daily_fixed_costs_rs

                        # Recálculo Receita Base (Para BASE orçada, usa cotação média)
                        receita_me_base_diaria = (price_usd_avg * daily_qty * cotacao_base_avg)
                        receita_bruta_base_diaria = receita_me_base_diaria + daily_revenue_domestic_rs  # CORRIGIDO
                        receita_base_diaria_liquida = receita_bruta_base_diaria - daily_deducoes_rs

                        df_daily_sim['EBITDA Base Diário (R$)'] = receita_base_diaria_liquida - daily_fixed_costs_rs

                        # 6. Calcular Risco e Hedge Diários (R$)
                        df_daily_sim['EaR Diário (Δ R$)'] = df_daily_sim['EBITDA Base Diário (R$)'] - df_daily_sim[
                            'EBITDA Sem Hedge Diário (R$)']
                        hedge_level_pct_avg = np.mean(list(hedge_dict.values())) / 100.0
                        df_daily_sim['Impacto Hedge Diário (R$)'] = df_daily_sim[
                                                                        'EaR Diário (Δ R$)'] * hedge_level_pct_avg
                        df_daily_sim['EBITDA com Hedge Diário (R$)'] = df_daily_sim['EBITDA Sem Hedge Diário (R$)'] + \
                                                                       df_daily_sim['Impacto Hedge Diário (R$)']

                        # 7. CALCULAR MARGENS E RETORNOS
                        epsilon = 1e-9

                        df_daily_sim['Margem EBITDA Sem Hedge (%)'] = np.where(
                            df_daily_sim['Receita Líquida Diária (R$)'] != 0,
                            (df_daily_sim['EBITDA Sem Hedge Diário (R$)'] / df_daily_sim[
                                'Receita Líquida Diária (R$)']) * 100,
                            0.0
                        )
                        df_daily_sim['Margem EBITDA com Hedge (%)'] = np.where(
                            df_daily_sim['Receita Líquida Diária (R$)'] != 0,
                            (df_daily_sim['EBITDA com Hedge Diário (R$)'] / df_daily_sim[
                                'Receita Líquida Diária (R$)']) * 100,
                            0.0
                        )

                        # 8. CALCULAR RETORNOS LOGARÍTMICOS DIÁRIOS
                        df_daily_sim['Retorno Log EBITDA Sem Hedge'] = np.log(
                            (df_daily_sim['EBITDA Sem Hedge Diário (R$)'] + epsilon) /
                            (df_daily_sim['EBITDA Sem Hedge Diário (R$)'].shift(1) + epsilon)
                        )

                        df_daily_sim['Retorno Log EBITDA com Hedge'] = np.log(
                            (df_daily_sim['EBITDA com Hedge Diário (R$)'] + epsilon) /
                            (df_daily_sim['EBITDA com Hedge Diário (R$)'].shift(1) + epsilon)
                        )

                        df_daily_sim.replace([np.inf, -np.inf], np.nan, inplace=True)
                        df_daily_sim.dropna(inplace=True)

                        # NOVO GRÁFICO DE LINHAS PARA RETORNOS
                        st.markdown("### Variação Diária do EBITDA: Cenário Sem Hedge vs. Com Hedge")

                        fig_retornos_ebitda = go.Figure()

                        fig_retornos_ebitda.add_trace(go.Scatter(
                            x=df_daily_sim.index,
                            y=df_daily_sim['Retorno Log EBITDA Sem Hedge'],
                            mode='lines',
                            name='EBITDA sem Hedge',
                            line=dict(color=color_map['EBITDA Sem Hedge (R$)'], width=1.5)
                        ))

                        fig_retornos_ebitda.add_trace(go.Scatter(
                            x=df_daily_sim.index,
                            y=df_daily_sim['Retorno Log EBITDA com Hedge'],
                            mode='lines',
                            name=f'EBITDA com Hedge ({hedge_level_pct_avg * 100:.0f}%)',
                            line=dict(color=color_map['EBITDA com Hedge (R$)'], width=3)
                        ))

                        fig_retornos_ebitda.update_layout(
                            title="Variação Diária do EBITDA: Cenário Sem Hedge vs. Com Hedge",
                            yaxis_title="Retorno Logarítmico do EBITDA",
                            hovermode="x unified",
                            template="plotly_white",
                            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
                            yaxis_tickformat=".2%"
                        )
                        st.plotly_chart(fig_retornos_ebitda, use_container_width=True)

                        with st.expander("Ver dados detalhados da Simulação Diária"):
                            st.markdown("#### Base de Cálculo da Simulação Diária")
                            if not df_daily_sim.empty:
                                st.markdown(
                                    f"Abaixo está o detalhamento de como os valores para o **primeiro dia** da simulação (Data: **{df_daily_sim.index[0].strftime('%d/%m/%Y')}**) foram calculados. Os demais dias seguem a mesma lógica.")

                                st.markdown(f"##### 1. Premissas Diárias (Desagregadas do Orçamento)")
                                st.markdown(
                                    f"Cálculos baseados em **{num_dias_sim} dias** de dados históricos (Seção 2).")

                                # Variáveis do Orçamento (Seção 1)
                                price_usd_avg_base = dados.loc["Preço de Venda (USD)", colunas_seguras].astype(float)
                                qty_total_base = dados.loc["Quantidade Vendida (Unid)", colunas_seguras].astype(
                                    float).sum()
                                deducoes_total_base = resultado.loc["Deduções sobre Vendas (R$)", "Total"]
                                custos_total_base = resultado.loc["Custos (R$)", "Total"]
                                despesas_total_base = resultado.loc["Despesas Operacionais (R$)", "Total"]
                                custo_fixo_operacional_total_base = custos_total_base + despesas_total_base

                                # Calculo da Receita Diária em USD
                                receita_usd_diaria = price_usd_avg * daily_qty

                                col1, col2 = st.columns(2)

                                with col1:
                                    st.metric("Preço Médio (USD)", f"$ {price_usd_avg:,.2f}")
                                    st.caption(
                                        f"**Fórmula:** Média(Preços USD Seção 1) = Média({', '.join([f'{p:,.2f}' for p in price_usd_avg_base])})")

                                    st.metric("Quantidade Diária (Calc)", f"{daily_qty:,.2f} un")
                                    st.caption(
                                        f"**Fórmula:** Quantidade Total / Nº Dias = {qty_total_base:,.0f} / {num_dias_sim}")

                                with col2:
                                    st.metric("Receita Diária (USD)", f"$ {receita_usd_diaria:,.2f}")
                                    st.caption(
                                        f"**Fórmula:** Preço Médio USD × Quantidade Diária = ${price_usd_avg:,.2f} × {daily_qty:,.2f}")

                                    st.metric("Custo Fixo Operacional Diário (R$)", formatar_brl(daily_fixed_costs_rs))
                                    st.caption(
                                        f"**Fórmula:** (Custos + Despesas) / Nº Dias = {formatar_brl(custo_fixo_operacional_total_base)} / {num_dias_sim}")

                                st.markdown("---")
                                st.markdown(
                                    f"##### 2. Cálculo do Primeiro Dia (Cotação: {formatar_brl(df_daily_sim.iloc[0]['Cotação Diária'])})")

                                # Puxa os dados do primeiro dia para facilitar a leitura
                                primeiro_dia = df_daily_sim.iloc[0]
                                cotacao_dia_1 = primeiro_dia['Cotação Diária']
                                rec_bruta_dia_1 = primeiro_dia['Receita Bruta Diária (R$)']
                                rec_liq_dia_1 = primeiro_dia['Receita Líquida Diária (R$)']
                                ebitda_adv_dia_1 = primeiro_dia['EBITDA Sem Hedge Diário (R$)']
                                ebitda_base_dia_1 = primeiro_dia['EBITDA Base Diário (R$)']
                                ear_dia_1 = primeiro_dia['EaR Diário (Δ R$)']
                                hedge_gain_dia_1 = primeiro_dia['Impacto Hedge Diário (R$)']
                                ebitda_hedge_dia_1 = primeiro_dia['EBITDA com Hedge Diário (R$)']

                                # Usando st.markdown com formatação de código para clareza
                                st.markdown(f"""
                                - **Receita Bruta (R$)** (ME + Doméstica): `Receita Diária (USD)` × `Cotação do Dia` + `Receita Doméstica Diária (R$)`
                                  - `({f"$ {receita_usd_diaria:,.2f}"}` × `{formatar_brl(cotacao_dia_1)})` + `{formatar_brl(daily_revenue_domestic_rs)}` = **{formatar_brl(rec_bruta_dia_1)}**

                                - **Receita Líquida (R$)**: `Receita Bruta (R$)` - `Deduções Diárias (R$)`
                                  - `{formatar_brl(rec_bruta_dia_1)}` - `{formatar_brl(daily_deducoes_rs)}` = **{formatar_brl(rec_liq_dia_1)}**

                                - **EBITDA Sem Hedge (R$)**: `Receita Líquida (R$)` − `Custo Fixo Operacional Diário (R$)`
                                  - `{formatar_brl(rec_liq_dia_1)}` − `{formatar_brl(daily_fixed_costs_rs)}` = **{formatar_brl(ebitda_adv_dia_1)}**

                                - **EBITDA Base (R$)**: (`Rec Liq Base`) − `Custo Fixo Diário`
                                  - `{formatar_brl(receita_base_diaria_liquida)}` − `{formatar_brl(daily_fixed_costs_rs)}` = **{formatar_brl(ebitda_base_dia_1)}**

                                - **EaR (Perda) (Δ R$)**: `EBITDA Base` − `EBITDA Sem Hedge`
                                  - `{formatar_brl(ebitda_base_dia_1)}` − `{formatar_brl(ebitda_adv_dia_1)}` = **{formatar_brl(ear_dia_1)}**

                                - **Impacto Hedge (R$)**: `EaR (Perda)` × `% Hedge`
                                  - `{formatar_brl(ear_dia_1)}` × `{hedge_level_pct_avg * 100:.0f}%` = **{formatar_brl(hedge_gain_dia_1)}**

                                - **EBITDA com Hedge (R$)**: `EBITDA Sem Hedge` + `Impacto Hedge`
                                  - `{formatar_brl(ebitda_adv_dia_1)}` + `{formatar_brl(hedge_gain_dia_1)}` = **{formatar_brl(ebitda_hedge_dia_1)}**
                                """)

                                st.divider()
                                st.markdown("#### Tabela Completa da Simulação Diária")
                                st.dataframe(df_daily_sim.style.format({
                                    'Cotação Diária': 'R$ {:,.4f}',
                                    'Receita Bruta Diária (R$)': 'R$ {:,.2f}',
                                    'Receita Líquida Diária (R$)': 'R$ {:,.2f}',
                                    'EBITDA Sem Hedge Diário (R$)': 'R$ {:,.2f}',
                                    'EBITDA Base Diário (R$)': 'R$ {:,.2f}',
                                    'EaR Diário (Δ R$)': 'R$ {:,.2f}',
                                    'Impacto Hedge Diário (R$)': 'R$ {:,.2f}',
                                    'EBITDA com Hedge Diário (R$)': 'R$ {:,.2f}',
                                    'Margem EBITDA Sem Hedge (%)': '{:,.2f}%',
                                    'Margem EBITDA com Hedge (%)': '{:,.2f}%',
                                    'Retorno Log EBITDA Sem Hedge': '{:,.4%}',
                                    'Retorno Log EBITDA com Hedge': '{:,.4%}'
                                }))
                            else:
                                st.warning("Dados para detalhamento da simulação estão vazios após dropna.")


                    except Exception as e:
                        st.error(f"Erro ao gerar a simulação diária: {e}")
                else:
                    st.warning("Simulação diária requer que os dados históricos da Seção 2 sejam carregados.")
                # --- FIM DO BLOCO ATUALIZADO (SIMULAÇÃO DIÁRIA) ---

                st.markdown("### Tabela Consolidada de Resultados (Hedge)")
                ebitda_base_total_sum = df_plot["EBITDA Base (R$)"].sum()
                ear_delta_total_sum = df_plot["EaR (Δ R$)"].sum()
                impacto_hedge_total_sum = df_plot["Impacto do Hedge (R$)"].sum()
                ebitda_adverso_total_sum = df_plot["EBITDA Sem Hedge (R$)"].sum()
                ebitda_hedge_total_sum = df_plot["EBITDA com Hedge (R$)"].sum()

                ear_pct_total = (
                        ear_delta_total_sum / ebitda_base_total_sum * 100) if ebitda_base_total_sum != 0 else 0.0
                impacto_pct_total = (
                        impacto_hedge_total_sum / ebitda_adverso_total_sum * 100) if ebitda_adverso_total_sum != 0 else 0.0

                total_row_hedge = pd.DataFrame({
                    "EBITDA Base (R$)": [ebitda_base_total_sum], "EBITDA Sem Hedge (R$)": [ebitda_adverso_total_sum],
                    "EaR (Δ R$)": [ear_delta_total_sum], "EaR (%)": [ear_pct_total],
                    "Hedge (%)": [df_plot["Hedge (%)"].mean()],
                    "EBITDA com Hedge (R$)": [ebitda_hedge_total_sum],
                    "Impacto do Hedge (R$)": [impacto_hedge_total_sum],
                    "Impacto do Hedge (%)": [impacto_pct_total]
                }, index=["Total"])
                tabela_final = pd.concat([df_plot, total_row_hedge])

                st.dataframe(
                    tabela_final.style.format({
                        "EBITDA Base (R$)": "R$ {:,.2f}", "EBITDA Sem Hedge (R$)": "R$ {:,.2f}",
                        "EaR (Δ R$)": "R$ {:,.2f}", "EaR (%)": "{:.2f}%", "Hedge (%)": "{:.0f}%",
                        "EBITDA com Hedge (R$)": "R$ {:,.2f}", "Impacto do Hedge (R$)": "R$ {:,.2f}",
                        "Impacto do Hedge (%)": "{:.2f}%"
                    }),
                    use_container_width=True
                )

                # Novo Painel de Métricas
                st.markdown("### Painel de Desempenho (Resultados Totais)")

                ebitda_base_kpi = tabela_final.loc["Total", "EBITDA Base (R$)"]
                ebitda_adv_kpi = tabela_final.loc["Total", "EBITDA Sem Hedge (R$)"]
                ebitda_hedge_kpi = tabela_final.loc["Total", "EBITDA com Hedge (R$)"]
                ear_loss_kpi = tabela_final.loc["Total", "EaR (Δ R$)"]
                hedge_gain_kpi = tabela_final.loc["Total", "Impacto do Hedge (R$)"]

                col1, col2, col3, col4, col5 = st.columns(5)

                col1.metric(
                    "EBITDA Base (Orçado)",
                    formatar_brl(ebitda_base_kpi)
                )

                delta_adv_kpi = ebitda_adv_kpi - ebitda_base_kpi
                delta_adv_kpi_formatado_brl = formatar_brl(delta_adv_kpi)
                col2.metric(
                    "EBITDA Sem Hedge (Sem Hedge)",
                    formatar_brl(ebitda_adv_kpi),
                    delta=f"{delta_adv_kpi:.2f}",
                    delta_color="normal",
                    help=f"Variação vs Base: {delta_adv_kpi_formatado_brl}"
                )

                delta_hedge_kpi = ebitda_hedge_kpi - ebitda_base_kpi
                delta_hedge_kpi_formatado_brl = formatar_brl(delta_hedge_kpi)
                col3.metric(
                    "EBITDA com Hedge",
                    formatar_brl(ebitda_hedge_kpi),
                    delta=f"{delta_hedge_kpi:.2f}",
                    delta_color="normal",
                    help=f"Variação vs Base: {delta_hedge_kpi_formatado_brl}"
                )

                delta_adv_pct_kpi = (delta_adv_kpi / ebitda_base_kpi * 100) if ebitda_base_kpi != 0 else 0.0
                col4.metric(
                    "EBITDA @Risk (Perda)",
                    formatar_brl(ear_loss_kpi),
                    delta=f"{delta_adv_pct_kpi:.1f}%",
                    delta_color="normal",
                    help="Variação percentual vs Base"
                )

                recuperacao_pct_kpi = (hedge_gain_kpi / ear_loss_kpi * 100) if ear_loss_kpi != 0 else 0.0
                col5.metric(
                    "Recuperação (Hedge)",
                    formatar_brl(hedge_gain_kpi),
                    delta=f"{recuperacao_pct_kpi:.1f}%",
                    delta_color="normal",
                    help="Percentual da perda recuperado pelo hedge"
                )

                st.markdown("### Análise de Margem EBITDA (Sem vs Com Hedge)")

                receita_liquida_adversa = resultado_scenario.loc["Receita Líquida (R$)", colunas_seguras].fillna(0)
                receita_liquida_adversa_plot = receita_liquida_adversa.reindex(df_plot.index).fillna(0)
                df_margens = pd.DataFrame({
                    "Período": df_plot.index,
                    "Receita Líquida (Adverso)": receita_liquida_adversa_plot,
                    "EBITDA Sem Hedge (R$)": df_plot["EBITDA Sem Hedge (R$)"],
                    "EBITDA com Hedge (R$)": df_plot["EBITDA com Hedge (R$)"]
                })
                df_margens["Margem EBITDA Sem Hedge (%)"] = np.where(df_margens["Receita Líquida (Adverso)"] != 0, (
                        df_margens["EBITDA Sem Hedge (R$)"] / df_margens["Receita Líquida (Adverso)"] * 100), 0.0)
                df_margens["Margem EBITDA Com Hedge (%)"] = np.where(df_margens["Receita Líquida (Adverso)"] != 0, (
                        df_margens["EBITDA com Hedge (R$)"] / df_margens["Receita Líquida (Adverso)"] * 100), 0.0)
                df_margens["Impacto do Hedge (p.p.)"] = df_margens["Margem EBITDA Com Hedge (%)"] - df_margens[
                    "Margem EBITDA Sem Hedge (%)"]

                col1, col2 = st.columns(2)
                with col1:
                    fig_margem = go.Figure()
                    fig_margem.add_trace(
                        go.Scatter(x=df_margens["Período"], y=df_margens["Margem EBITDA Sem Hedge (%)"],
                                   mode='lines+markers',
                                   name='Margem Sem Hedge', line=dict(color=color_map['EBITDA Sem Hedge (R$)'])))
                    fig_margem.add_trace(
                        go.Scatter(x=df_margens["Período"], y=df_margens["Margem EBITDA Com Hedge (%)"],
                                   mode='lines+markers',
                                   name='Margem Com Hedge',
                                   line=dict(color=color_map['EBITDA com Hedge (R$)'])))
                    fig_margem.update_layout(title="Evolução da Margem EBITDA", xaxis_title="Período",
                                             yaxis_title="Margem EBITDA (%)", hovermode="x unified",
                                             template="plotly_white",
                                             legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center",
                                                         x=0.5),
                                             yaxis_tickformat=".2f", yaxis_ticksuffix="%")
                    st.plotly_chart(fig_margem, use_container_width=True)
                with col2:
                    fig_impacto = go.Figure()
                    fig_impacto.add_trace(
                        go.Bar(x=df_margens["Período"], y=df_margens["Impacto do Hedge (p.p.)"],
                               marker_color=color_map['EBITDA Base (R$)'],
                               name='Impacto do Hedge'))
                    fig_impacto.update_layout(title="Impacto do Hedge sobre a Margem (p.p.)", xaxis_title="Período",
                                              yaxis_title="Impacto (p.p.)", template="plotly_white", showlegend=False,
                                              yaxis_tickformat=".2f", yaxis_ticksuffix="%")
                    st.plotly_chart(fig_impacto, use_container_width=True)

                with st.expander("Ver Tabela Detalhada das Margens"):
                    df_margens_display = df_margens.set_index("Período")
                    st.dataframe(
                        df_margens_display.style.format({
                            "Receita Líquida (Adverso)": "R$ {:,.2f}", "EBITDA Sem Hedge (R$)": "R$ {:,.2f}",
                            "EBITDA com Hedge (R$)": "R$ {:,.2f}", "Margem EBITDA Sem Hedge (%)": "{:.2f}%",
                            "Margem EBITDA Com Hedge (%)": "{:.2f}%", "Impacto do Hedge (p.p.)": "{:+.2f} p.p."
                        }),
                        use_container_width=True
                    )
else:
    st.warning("Seção 5: A simulação de Hedge requer que as Seções 2 e 4 sejam executadas.")

st.markdown("---")


# ========================================
# SEÇÃO 6: Simulação de Monte Carlo
# ========================================

if 'cot_med_usuario' in locals() and 'retorno_mensal' in locals() and 'volatilidade_mensal' in locals() and 'dados' in locals():
    with st.expander("6. Simulação de Monte Carlo (EBITDA @Risk)", expanded=False):

        st.markdown("### Simulação de Monte Carlo (Câmbio e EBITDA)")
        st.markdown("""
        Esta seção executa uma simulação estocástica independente, usando os parâmetros de volatilidade e retorno
        calculados ou inseridos na Seção 3.
        """)
        st.info("""
        **Metodologia Monte Carlo:**
        1.  Simula milhares de cotações de câmbio (`cambio_simulado`) com base nos parâmetros de retorno e volatilidade.
        2.  Para *cada* cotação simulada, recalcula o **EBITDA Total** (somando todos os meses).
        3.  Isso gera uma distribuição de probabilidade do EBITDA Total.
        4.  O **EBITDA Mínimo Simulado** é o 5º (ou 1º) percentil dessa distribuição, representando o pior cenário esperado.
        """)

        S0 = cot_med_usuario if cot_med_usuario > 0 else 1.0
        mu = retorno_mensal
        sigma = volatilidade_mensal
        nivel_pct = int(nivel_confianca.strip("%"))
        percentil_adverso = 100 - nivel_pct
        num_simulacoes = st.number_input(
            "Número de simulações Monte Carlo:",
            min_value=1000, max_value=200000, value=50000, step=1000, key="mc_sims_main"
        )
        t = 1.0  # Horizonte de 1 mês
        np.random.seed(42)
        Z = np.random.randn(num_simulacoes)
        sigma_safe = max(sigma, 0.00001)
        # O cálculo do câmbio simulado está correto para um horizonte t=1
        cambio_simulado = S0 * np.exp((mu - 0.5 * sigma_safe ** 2) * t + sigma_safe * np.sqrt(t) * Z)

        cambio_min_sim = np.percentile(cambio_simulado, percentil_adverso)
        cambio_mean = np.mean(cambio_simulado)
        cambio_max_sim = np.max(cambio_simulado)

        st.markdown("### Resultados da Simulação de Câmbio")
        col1, col2, col3 = st.columns(3)
        col1.metric(f"Câmbio Mínimo ({nivel_confianca})", f"R$ {cambio_min_sim:,.4f}")
        col2.metric("Câmbio Média (Simulado)", f"R$ {cambio_mean:,.4f}")
        col3.metric("Câmbio Máximo (Simulado)", f"R$ {cambio_max_sim:,.4f}")

        fig_sim = px.histogram(x=cambio_simulado, nbins=100,
                               title=f"Distribuição Simulada do Câmbio ({num_simulacoes:,} sim.)",
                               labels={'x': 'Câmbio Simulado (R$/US$)', 'y': 'Frequência'},
                               histnorm='probability density')
        fig_sim.add_vline(x=cambio_min_sim, line_dash="dash", line_color=color_map['EBITDA Sem Hedge (R$)'],
                          annotation_text=f"Câmbio mínimo ({nivel_confianca}): {cambio_min_sim:,.4f}")
        fig_sim.add_vline(x=cambio_mean, line_dash="dot", line_color=color_map['EBITDA com Hedge (R$)'],
                          annotation_text=f"Média: {cambio_mean:,.4f}")
        fig_sim.update_layout(template="plotly_white")
        st.plotly_chart(fig_sim, use_container_width=True)

        st.markdown("### Resultados da Simulação de EBITDA")
        # --- Selecionar Receitas USD (Exposição Bruta) ---
        receitas_usd = (dados.loc["Preço de Venda (USD)", colunas].astype(float) * dados.loc[
            "Quantidade Vendida (Unid)", colunas].astype(float))
        # ------------------------------------------------------------------

        # --- Variáveis de Custo e Receita Doméstica TOTAL (R$) ---
        deducoes_total = resultado.loc["Deduções sobre Vendas (R$)", "Total"]
        custos_total = resultado.loc["Custos (R$)", "Total"]
        despesas_total = resultado.loc["Despesas Operacionais (R$)", "Total"]

        # OBTENÇÃO DA RECEITA DOMÉSTICA TOTAL
        receita_domestica_total = resultado.loc["  Receita Mercado Interno (R$)", "Total"]
        # ---------------------------------------------------------

        # 1. Multiplica Receita USD pela cotação simulada para obter Receita ME Simulada (R$)
        receitas_usd_values = receitas_usd.values
        if receitas_usd_values.ndim == 1 and len(receitas_usd_values) == num_meses:
            receitas_me_sum_por_sim = cambio_simulado[:, None] * receitas_usd_values[None, :]

            # 2. Soma as Receitas ME Simuladas por período para obter a Receita Bruta ME Total Simulada
            receita_me_total_simulada = receitas_me_sum_por_sim.sum(axis=1)

            # 3. Calcula o EBITDA Total
            # EBITDA = (Receita ME Simulada + Receita Doméstica) - Deduções - Custos - Despesas
            ebitda_simulado = (
                                      receita_me_total_simulada + receita_domestica_total
                              ) - deducoes_total - custos_total - despesas_total
        else:
            st.error(
                f"Erro no formato das Receitas USD para simulação Monte Carlo (Esperado: {num_meses}, Obtido: {len(receitas_usd_values)})")
            ebitda_simulado = np.array([0.0] * num_simulacoes)

        ebitda_mean_sim = np.mean(ebitda_simulado)
        ebitda_min_sim = np.percentile(ebitda_simulado, percentil_adverso)
        ebitda_at_risk_mc = ebitda_total - ebitda_min_sim

        col1, col2, col3 = st.columns(3)
        col1.metric("EBITDA Base (Orçado)", formatar_brl(ebitda_total))

        # EBITDA Mínimo Simulado
        delta_mc_valor = ebitda_min_sim - ebitda_total
        delta_mc_formatado_brl = formatar_brl(delta_mc_valor)
        col2.metric(f"EBITDA Mínimo Sim. ({nivel_confianca})", formatar_brl(ebitda_min_sim),
                    delta=f"{delta_mc_valor:.2f}", delta_color="normal",
                    help=f"Variação vs Base: {delta_mc_formatado_brl}")

        # EaR (Monte Carlo)
        delta_mc_pct = (delta_mc_valor / ebitda_total * 100) if ebitda_total != 0 else 0.0
        col3.metric(f"EBITDA @Risk (Monte Carlo)", formatar_brl(ebitda_at_risk_mc),
                    delta=f"{delta_mc_pct:.1f}%", delta_color="normal",
                    help=f"Perda vs Base: {formatar_brl(ebitda_at_risk_mc)} ({delta_mc_pct:.1f}%)")

        fig_eb = px.histogram(x=ebitda_simulado, nbins=100,
                              title="Distribuição Simulada do EBITDA (Total Períodos)",
                              labels={'x': 'EBITDA Simulado (R$)', 'y': 'Frequência'}, histnorm='probability density')
        fig_eb.add_vline(x=ebitda_min_sim, line_dash="dash", line_color=color_map['EBITDA Sem Hedge (R$)'],
                         annotation_text=f"EBITDA mínimo ({nivel_confianca}): {formatar_brl(ebitda_min_sim)}")
        fig_eb.add_vline(x=ebitda_mean_sim, line_dash="dot", line_color=color_map['EBITDA com Hedge (R$)'],
                         annotation_text=f"Média: {formatar_brl(ebitda_mean_sim)}")
        fig_eb.add_vline(x=ebitda_total, line_dash="solid", line_color=color_map['EBITDA Base (R$)'],
                         annotation_text=f"Base Orçada: {formatar_brl(ebitda_total)}")
        fig_eb.update_layout(template="plotly_white")
        st.plotly_chart(fig_eb, use_container_width=True)



        ebitda_mean_sim = np.mean(ebitda_simulado)
        ebitda_min_sim = np.percentile(ebitda_simulado, percentil_adverso)
        ebitda_at_risk_mc = ebitda_total - ebitda_min_sim

        # ---- NOVO: Cálculo do Erro Padrão ----
        # ---- Cálculo do Erro Padrão ----
        std_ebitda_sim = np.std(ebitda_simulado, ddof=1)
        erro_padrao_mc = std_ebitda_sim / np.sqrt(num_simulacoes)

        erro_padrao_pct = (erro_padrao_mc / ebitda_mean_sim) * 100



    st.markdown("---")

    # ========================================
    # SEÇÃO 7: Consolidação de Cenários de Risco
    # ========================================

    if ('ebitda_total' in locals() and
            'cambio_minimo_var' in locals() and
            'cambio_min_sim' in locals() and
            'ebitda_min_total' in locals() and
            'ebitda_min_sim' in locals()):

        with st.expander("7. Consolidação de Cenários de Risco", expanded=True):

            # --- 1. Preparar dados do Cenário Selecionado (Seção 4) ---
            if 'metodo_ear' not in locals(): metodo_ear = "N/A"

            label_cenario_selecionado = "Cenário Selecionado (Seção 4)"
            if metodo_ear.startswith("1."):
                label_cenario_selecionado = "Cenário Meta (Goal Seek)"
            elif metodo_ear.startswith("2."):
                label_cenario_selecionado = "Cenário Analítico (VaR)"
            elif metodo_ear.startswith("3."):
                label_cenario_selecionado = "Cenário Manual"

            cambio_stress = np.mean(cambio_aplicado) if isinstance(cambio_aplicado,
                                                                   (pd.Series, np.ndarray, list)) else cambio_aplicado
            ebitda_stress = ebitda_min_total
            ear_stress = ear_loss

            # --- 2. Preparar dados do Cenário Analítico (VaR Puro) ---
            # --- Selecionar Receitas USD (Exposição Bruta) ---
            receitas_usd_total = (dados.loc["Preço de Venda (USD)", colunas].astype(float) * dados.loc[
                "Quantidade Vendida (Unid)", colunas].astype(float)).sum()
            # ------------------------------------------------------------------

            if 'deducoes_total' not in locals():  # Garante que as variáveis de custo/dedução estejam disponíveis
                deducoes_total = resultado.loc["Deduções sobre Vendas (R$)", "Total"]
                custos_total = resultado.loc["Custos (R$)", "Total"]
                despesas_total = resultado.loc["Despesas Operacionais (R$)", "Total"]
                receita_domestica_total = resultado.loc["  Receita Mercado Interno (R$)", "Total"]

            # EBITDA Mínimo Analítico = (Receita ME Mínima + Receita Doméstica) - Custos
            receitas_minimas_me_var_total = receitas_usd_total * cambio_minimo_var
            ebitda_min_total_var = (
                                           receitas_minimas_me_var_total + receita_domestica_total
                                   ) - deducoes_total - custos_total - despesas_total
            ear_loss_var = ebitda_total - ebitda_min_total_var

            # --- 3. Montar Tabela Comparativa ---
            st.subheader("Análise Comparativa dos Cenários de Risco")

            resumo_comparativo = pd.DataFrame({
                "Métrica": ["Câmbio Mínimo Esperado", "EBITDA Sem Hedge (Cenário)", "EBITDA @Risk (Perda)"],

                label_cenario_selecionado: [
                    f"R$ {cambio_stress:,.4f}",
                    formatar_brl(ebitda_stress),
                    formatar_brl(ear_stress)
                ],

                "Analítico": [
                    f"R$ {cambio_minimo_var:,.4f}",
                    formatar_brl(ebitda_min_total_var),
                    formatar_brl(ear_loss_var)
                ],

                "Monte Carlo": [
                    f"R$ {cambio_min_sim:,.4f}",
                    formatar_brl(ebitda_min_sim),
                    formatar_brl(ebitda_at_risk_mc)
                ]
            })

            st.dataframe(resumo_comparativo.set_index("Métrica"), use_container_width=True)

            st.markdown(f"""
            <div class="insight-box">
            <strong>Interpretação dos Resultados:</strong><br>
            Esta tabela consolida os três principais métodos de análise de risco calculados no aplicativo:
            <ul>
                <li><strong>{label_cenario_selecionado}:</strong> O resultado direto do cenário de stress que você selecionou e detalhou na <strong>Seção 4</strong> (seja ele baseado em Meta, VaR ou Manual).</li>
                <li><strong>Analítico (VaR Puro):</strong> O pior cenário calculado de forma paramétrica (<strong>Seção 3</strong>), com base na volatilidade histórica e nível de confiança.</li>
                <li><strong>Monte Carlo (Estocástico):</strong> O pior cenário obtido após simular milhares de cotações de câmbio (<strong>Seção 6</strong>), refletindo uma distribuição de probabilidade.</li>
            </ul>
            A comparação permite avaliar a robustez do seu hedge e a sensibilidade do seu EBITDA a diferentes metodologias de risco.
            </div>
            """, unsafe_allow_html=True)
    else:
        st.warning(
            "Seção 7: As Seções 3, 4 e 6 precisam ser executadas para gerar o painel de consolidação de cenários.")

else:
    st.warning(
        "Seção 6/7: O cálculo de Monte Carlo e a Consolidação requerem os parâmetros da Seção 3 e os dados das Seções 1 e 2.")

