import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import japanize_matplotlib
from streamlit_gsheets import GSheetsConnection

# --- ページ設定 ---
st.set_page_config(page_title="設備メンテナンス管理", layout="wide")

# ---------- データ読み込み ----------
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    df = conn.read(worksheet="maintenance_data", ttl="0")
    stock = conn.read(worksheet="stock_data", ttl="0")
    return df, stock

df, stock_df = load_data()

# 必須列の初期化
for col in ['備考', '費用']:
    if col not in df.columns:
        df[col] = 0 if col == '費用' else ""

# 日付型に変換
df['最終点検日'] = pd.to_datetime(df['最終点検日'], errors='coerce')

# --- タブの保持設定 ---
# 保存後に勝手にダッシュボードに戻らないようにします
if "current_tab" not in st.session_state:
    st.session_state.current_tab = 0

# --- サイドバー：期間絞り込み ---
st.sidebar.header("📅 表示期間の絞り込み")
min_date_val = df['最終点検日'].min().date() if not df.empty and pd.notnull(df['最終点検日'].min()) else datetime.today().date() - timedelta(days=365)
max_date_val = datetime.today().date()
start_date, end_date = st.sidebar.date_input("期間を選択", value=(min_date_val, max_date_val))

mask = (df['最終点検日'].dt.date >= start_date) & (df['最終点検日'].dt.date <= end_date)
filtered_df = df.loc[mask].copy()

# 共通の分類リスト
categories = ["すべて", "ジョークラッシャ", "インパクトクラッシャー", "スクリーン", "ベルト", "その他"]

# --- タブ表示 ---
tabs = ["📊 ダッシュボード", "📁 過去履歴", "📦 在庫管理", "📝 メンテナンス登録"]
tab1, tab2, tab3, tab4 = st.tabs(tabs)

# ================================================================
# 📊 1. ダッシュボード
# ================================================================
with tab1:
    st.header(f"📊 メンテナンス状況概況")
    if not filtered_df.empty:
        col1, col2, col3 = st.columns(3)
        col1.metric("選択期間の回数", f"{len(filtered_df)} 回")
        col2.metric("選択期間の費用", f"{filtered_df['費用'].sum():,} 円")
        
        filtered_df['大分類'] = filtered_df['設備名'].str.extract(r'\[(.*?)\]')[0].fillna("その他")
        col_g1, col_g2 = st.columns(2)
        with col_g1:
            st.subheader("💰 設備別・累計費用")
            cost_by_equip = filtered_df.groupby('大分類')['費用'].sum().sort_values(ascending=True)
            fig1, ax1 = plt.subplots()
            cost_by_equip.plot(kind='barh', ax=ax1, color='#2ecc71')
            st.pyplot(fig1)
        with col_g2:
            st.subheader("📈 月別・設備別の費用推移")
            df_trend = filtered_df.copy()
            df_trend['年月'] = df_trend['最終点検日'].dt.strftime('%Y-%m')
            pivot_df = df_trend.pivot_table(index='年月', columns='大分類', values='費用', aggfunc='sum').fillna(0)
            fig2, ax2 = plt.subplots()
            pivot_df.plot(kind='line', marker='o', ax=ax2)
            st.pyplot(fig2)
    else: st.info("データがありません。")

# ================================================================
# 📁 2. 過去履歴
# ================================================================
with tab2:
    st.header("📁 メンテナンス過去履歴")
    st.dataframe(filtered_df.sort_values(by="最終点検日", ascending=False), use_container_width=True)
    st.markdown("---")
    st.subheader("🛠️ 履歴データの修正・削除")
    if not df.empty:
        df['label'] = df['最終点検日'].dt.strftime('%Y-%m-%d') + " | " + df['設備名']
        target_label = st.selectbox("修正・削除する履歴を選択", df['label'].tolist())
        target_idx = df[df['label'] == target_label].index[0]
        h_data = df.iloc[target_idx]
        with st.form("edit_h_form"):
            n_date = st.date_input("作業日", h_data["最終点検日"])
            n_equip = st.text_input("設備名", h_data["設備名"])
            n_desc = st.text_area("内容", h_data["作業内容"])
            n_cost = st.number_input("費用", value=int(h_data["費用"]), min_value=0)
            if st.form_submit_button("修正保存"):
                df.loc[target_idx, ["最終点検日", "設備名", "作業内容", "費用"]] = [pd.to_datetime(n_date), n_equip, n_desc, n_cost]
                conn.update(worksheet="maintenance_data", data=df.drop(columns=['label'], errors='ignore'))
                st.rerun()

# ================================================================
# 📦 3. 在庫管理（修正・削除時に分類検索を追加）
# ================================================================
with tab3:
    st.header("📦 部品在庫管理")
    
    # 閲覧用表示
    view_cat = st.selectbox("表示する分類を選択", categories, key="view_cat")
    d_stock = stock_df.copy()
    if view_cat != "すべて" and "分類" in d_stock.columns:
        d_stock = d_stock[d_stock["分類"] == view_cat]
    st.dataframe(d_stock, use_container_width=True)

    # 新規登録
    with st.expander("➕ 新しい部品をカタログに追加する"):
        with st.form("new_stock"):
            new_c = st.selectbox("分類", categories[1:])
            new_n = st.text_input("部品名")
            new_q = st.number_input("在庫数", min_value=0)
            if st.form_submit_button("新規登録"):
                new_row = pd.DataFrame([{"分類": new_c, "部品名": new_n, "在庫数": new_q, "最終更新日": datetime.now().strftime('%Y-%m-%d')}])
                stock_df = pd.concat([stock_df, new_row], ignore_index=True)
                conn.update(worksheet="stock_data", data=stock_df)
                st.rerun()

    # --- 修正・削除（分類検索機能付き） ---
    st.markdown("---")
    st.subheader("🛠️ 在庫データの修正・削除")
    
    # 1. まず分類で絞り込む
    search_cat = st.selectbox("修正したい部品の【分類】を選択", categories[1:], key="search_cat")
    
    # 2. その分類に属する部品だけをリストに出す
    filtered_items = stock_df[stock_df["分類"] == search_cat] if "分類" in stock_df.columns else stock_df
    
    if not filtered_items.empty:
        target_item = st.selectbox("修正する【部品】を選択", filtered_items["部品名"].tolist())
        s_data = stock_df[stock_df["部品名"] == target_item].iloc[0]
        
        col_s1, col_s2 = st.columns(2)
        with col_s1:
            with st.form("edit_s"):
                e_qty = st.number_input("在庫数", value=int(s_data["在庫数"]))
                if st.form_submit_button("在庫修正を保存"):
                    stock_df.loc[stock_df["部品名"] == target_item, ["在庫数", "最終更新日"]] = [e_qty, datetime.now().strftime('%Y-%m-%d')]
                    conn.update(worksheet="stock_data", data=stock_df)
                    st.rerun()
        with col_s2:
            if st.button(f"「{target_item}」を削除"):
                stock_df = stock_df[stock_df["部品名"] != target_item]
                conn.update(worksheet="stock_data", data=stock_df)
                st.rerun()
    else:
        st.info(f"{search_cat} に登録されている部品はありません。")

# ================================================================
# 📝 4. メンテナンス登録
# ================================================================
with tab4:
    st.header("📝 メンテナンス記録の入力")
    with st.form("mainte_reg"):
        e_name = st.selectbox("対象設備", categories[1:])
        e_detail = st.text_input("機番・詳細名称")
        w_desc = st.text_area("作業内容")
        w_date = st.date_input("作業日", datetime.today())
        w_cost = st.number_input("費用", min_value=0)
        if st.form_submit_button("保存"):
            new_row = pd.DataFrame([{"設備名": f"[{e_name}] {e_detail}", "最終点検日": w_date.strftime('%Y-%m-%d'), "作業内容": w_desc, "費用": w_cost}])
            df_final = pd.concat([df.drop(columns=['label'], errors='ignore'), new_row], ignore_index=True)
            conn.update(worksheet="maintenance_data", data=df_final)
            st.rerun()
