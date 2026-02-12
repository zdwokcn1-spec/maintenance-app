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

# 日付型に変換
df['最終点検日'] = pd.to_datetime(df['最終点検日'], errors='coerce')

# --- サイドバーで期間選択 ---
st.sidebar.header("📅 表示期間の絞り込み")
# 初期値として「全期間」を表示するための設定
min_date = df['最終点検日'].min().date() if not df.empty else datetime.today().date() - timedelta(days=365)
max_date = datetime.today().date()

start_date, end_date = st.sidebar.date_input(
    "期間を選択してください",
    value=(min_date, max_date),
    min_value=min_date - timedelta(days=365),
    max_value=max_date + timedelta(days=365)
)

# データを期間でフィルタリング
mask = (df['最終点検日'].dt.date >= start_date) & (df['最終点検日'].dt.date <= end_date)
filtered_df = df.loc[mask]

# --- タブ設定 ---
tab1, tab2, tab3, tab4 = st.tabs(["📊 ダッシュボード", "📁 過去履歴", "📦 在庫管理", "📝 メンテナンス登録"])

# ================================================================
# 📊 1. ダッシュボード
# ================================================================
with tab1:
    st.header(f"📊 メンテナンス状況 ({start_date} ～ {end_date})")
    
    if not filtered_df.empty:
        col1, col2, col3 = st.columns(3)
        col1.metric("選択期間の回数", f"{len(filtered_df)} 回")
        col2.metric("選択期間の費用", f"{filtered_df['費用'].sum():,} 円")
        col3.metric("対象設備数", f"{filtered_df['設備名'].nunique()} 種類")

        st.subheader("月別メンテナンス費用推移")
        df_monthly = filtered_df.set_index('最終点検日').resample('M')['費用'].sum().reset_index()
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.bar(df_monthly['最終点検日'].dt.strftime('%Y-%m'), df_monthly['費用'], color='#0073e6')
        ax.set_ylabel("費用（円）")
        plt.xticks(rotation=45)
        st.pyplot(fig)
    else:
        st.info("選択された期間にデータはありません。左側のメニューで期間を変更してください。")

# ================================================================
# 📁 2. 過去履歴
# ================================================================
with tab2:
    st.header(f"📁 メンテナンス過去履歴 ({start_date} ～ {end_date})")
    if not filtered_df.empty:
        df_display = filtered_df.sort_values(by="最終点検日", ascending=False).copy()
        df_display['最終点検日'] = df_display['最終点検日'].dt.strftime('%Y-%m-%d')
        st.dataframe(df_display, use_container_width=True)
    else:
        st.warning("この期間の履歴データは見つかりません。")

# --- (以下、在庫管理とメンテナンス登録のコードは前回と同じ) ---
with tab3:
    st.header("📦 部品在庫管理")
    st.dataframe(stock_df, use_container_width=True)

with tab4:
    st.header("📝 新規メンテナンス記録の入力")
    with st.form("maintenance_form", clear_on_submit=True):
        equip_name = st.text_input("設備名")
        work_desc = st.text_area("作業内容の詳細")
        work_date = st.date_input("作業実施日", datetime.today())
        cost = st.number_input("費用（円）", min_value=0)
        submitted = st.form_submit_button("スプレッドシートに保存")
        if submitted:
            new_row = pd.DataFrame([{"設備名": equip_name, "最終点検日": work_date.strftime('%Y-%m-%d'), "作業内容": work_desc, "費用": cost}])
            updated_df = pd.concat([df, new_row], ignore_index=True)
            conn.update(worksheet="maintenance_data", data=updated_df)
            st.success("保存完了！")
            st.rerun()
