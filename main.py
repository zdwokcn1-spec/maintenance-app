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

# --- サイドバー：期間絞り込み ---
st.sidebar.header("📅 表示期間の絞り込み")
min_date_val = df['最終点検日'].min().date() if not df.empty and pd.notnull(df['最終点検日'].min()) else datetime.today().date() - timedelta(days=365)
max_date_val = datetime.today().date()
start_date, end_date = st.sidebar.date_input("期間を選択", value=(min_date_val, max_date_val))

mask = (df['最終点検日'].dt.date >= start_date) & (df['最終点検日'].dt.date <= end_date)
filtered_df = df.loc[mask].copy()

# --- タブ設定 ---
tab1, tab2, tab3, tab4 = st.tabs(["📊 ダッシュボード", "📁 過去履歴", "📦 在庫管理", "📝 メンテナンス登録"])

# ================================================================
# 📊 1. ダッシュボード（設備別集計グラフ）
# ================================================================
with tab1:
    st.header(f"📊 メンテナンス状況概況")
    
    if not filtered_df.empty:
        col1, col2, col3 = st.columns(3)
        col1.metric("選択期間の回数", f"{len(filtered_df)} 回")
        col2.metric("選択期間の費用", f"{filtered_df['費用'].sum():,} 円")
        
        # 設備名の「大分類」を抽出（[ジョークラッシャ] などから抽出）
        filtered_df['大分類'] = filtered_df['設備名'].str.extract(r'\[(.*?)\]')[0].fillna("その他")

        col_g1, col_g2 = st.columns(2)
        
        with col_g1:
            st.subheader("💰 設備別・累計費用")
            # 設備ごとの合計費用
            cost_by_equip = filtered_df.groupby('大分類')['費用'].sum().sort_values(ascending=True)
            fig1, ax1 = plt.subplots()
            cost_by_equip.plot(kind='barh', ax=ax1, color='#2ecc71')
            ax1.set_xlabel("費用（円）")
            st.pyplot(fig1)

        with col_g2:
            st.subheader("📈 月別・設備別の費用推移")
            # 月別かつ設備別の集計
            df_trend = filtered_df.copy()
            df_trend['年月'] = df_trend['最終点検日'].dt.strftime('%Y-%m')
            pivot_df = df_trend.pivot_table(index='年月', columns='大分類', values='費用', aggfunc='sum').fillna(0)
            
            fig2, ax2 = plt.subplots()
            pivot_df.plot(kind='line', marker='o', ax=ax2)
            ax2.set_ylabel("費用（円）")
            plt.xticks(rotation=45)
            st.pyplot(fig2)
    else:
        st.warning("表示期間内にデータがありません。")

# ================================================================
# 📁 2. 過去履歴
# ================================================================
with tab2:
    st.header("📁 メンテナンス過去履歴")
    st.dataframe(filtered_df.drop(columns=['大分類'], errors='ignore').sort_values(by="最終点検日", ascending=False), use_container_width=True)

# ================================================================
# 📦 3. 在庫管理
# ================================================================
with tab3:
    st.header("📦 部品在庫管理")
    categories = ["すべて", "ジョークラッシャ", "インパクトクラッシャー", "スクリーン", "ベルト", "その他"]
    selected_cat = st.selectbox("表示する分類を選択", categories)
    d_stock = stock_df.copy()
    if selected_cat != "すべて" and "分類" in d_stock.columns:
        d_stock = d_stock[d_stock["分類"] == selected_cat]
    st.dataframe(d_stock, use_container_width=True)

# ================================================================
# 📝 4. メンテナンス登録
# ================================================================
with tab4:
    st.header("📝 メンテナンス記録の入力")
    with st.form("mainte_reg_form"):
        e_name = st.selectbox("対象設備", ["ジョークラッシャ", "インパクトクラッシャー", "スクリーン", "ベルト", "その他"])
        e_detail = st.text_input("機番・詳細名称（例：No.1）")
        w_desc = st.text_area("作業内容")
        w_note = st.text_area("備考（業者名など）")
        w_date = st.date_input("作業日", datetime.today())
        w_cost = st.number_input("費用", min_value=0)
        
        if st.form_submit_button("保存"):
            # 保存時に [ジョークラッシャ] の形式で保存することでグラフ集計を可能にする
            new_row = pd.DataFrame([{
                "設備名": f"[{e_name}] {e_detail}", 
                "最終点検日": w_date.strftime('%Y-%m-%d'), 
                "作業内容": w_desc, 
                "備考": w_note, 
                "費用": w_cost
            }])
            df_final = pd.concat([df.drop(columns=['label', '大分類'], errors='ignore'), new_row], ignore_index=True)
            conn.update(worksheet="maintenance_data", data=df_final)
            st.success("保存しました")
            st.rerun()
