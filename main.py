import streamlit as st
import pandas as pd
from datetime import datetime
import matplotlib.pyplot as plt
import japanize_matplotlib
from streamlit_gsheets import GSheetsConnection

# --- ページ設定 ---
st.set_page_config(page_title="設備メンテナンス管理", layout="wide")

# ---------- データ読み込み ----------
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    # キャッシュを0にして常に最新を取得
    df = conn.read(worksheet="maintenance_data", ttl="0")
    stock = conn.read(worksheet="stock_data", ttl="0")
    return df, stock

df, stock_df = load_data()

# 日付型に変換
df['最終点検日'] = pd.to_datetime(df['最終点検日'], errors='coerce')

# --- タブ設定 ---
tab1, tab2, tab3, tab4 = st.tabs(["📊 ダッシュボード", "📁 過去履歴", "📦 在庫管理", "📝 メンテナンス登録"])

# ================================================================
# 📊 1. ダッシュボード
# ================================================================
with tab1:
    st.header("📊 メンテナンス状況概況")
    
    if not df.empty:
        # メトリクス表示（合計数など）
        col1, col2, col3 = st.columns(3)
        col1.metric("総メンテナンス回数", f"{len(df)} 回")
        col2.metric("累計メンテナンス費用", f"{df['費用'].sum():,} 円")
        col3.metric("登録設備数", f"{df['設備名'].nunique()} 種類")

        # 費用推移グラフ
        st.subheader("月別メンテナンス費用推移")
        df_monthly = df.set_index('最終点検日').resample('M')['費用'].sum().reset_index()
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.bar(df_monthly['最終点検日'].dt.strftime('%Y-%m'), df_monthly['費用'], color='#0073e6')
        ax.set_ylabel("費用（円）")
        st.pyplot(fig)
    else:
        st.info("データが登録されるとここにグラフが表示されます。")

# ================================================================
# 📁 2. 過去履歴
# ================================================================
with tab2:
    st.header("📁 メンテナンス過去履歴")
    if not df.empty:
        # 日付の新しい順に並び替え
        df_display = df.sort_values(by="最終点検日", ascending=False).copy()
        # 表示用に日付フォーマットを整形
        df_display['最終点検日'] = df_display['最終点検日'].dt.strftime('%Y-%m-%d')
        st.dataframe(df_display, use_container_width=True)
    else:
        st.warning("履歴データが見つかりません。")

# ================================================================
# 📦 3. 在庫管理
# ================================================================
with tab3:
    st.header("📦 部品在庫管理")
    st.subheader("現在の在庫一覧")
    st.dataframe(stock_df, use_container_width=True)

    with st.expander("新しい部品を登録 / 在庫を更新する"):
        with st.form("stock_form"):
            name = st.text_input("部品名")
            qty = st.number_input("在庫数", min_value=0, step=1)
            price = st.number_input("単価（円）", min_value=0)
            reorder = st.number_input("発注点（これ以下で警告）", min_value=0, value=5)
            s_submit = st.form_submit_button("在庫データを保存")

            if s_submit and name:
                new_stock = stock_df.copy()
                if name in new_stock["部品名"].values:
                    new_stock.loc[new_stock["部品名"] == name, ["在庫数", "単価", "発注点", "最終更新日"]] = [qty, price, reorder, datetime.now().strftime('%Y-%m-%d')]
                else:
                    add_row = pd.DataFrame([{"部品名": name, "在庫数": qty, "単価": price, "発注点": reorder, "最終更新日": datetime.now().strftime('%Y-%m-%d')}])
                    new_stock = pd.concat([new_stock, add_row], ignore_index=True)
                
                conn.update(worksheet="stock_data", data=new_stock)
                st.success(f"「{name}」の在庫を更新しました。")
                st.rerun()

# ================================================================
# 📝 4. メンテナンス登録
# ================================================================
with tab4:
    st.header("📝 新規メンテナンス記録の入力")
    with st.form("maintenance_form", clear_on_submit=True):
        equip_name = st.text_input("設備名（例：B4 ベルト）")
        work_desc = st.text_area("作業内容の詳細")
        work_date = st.date_input("作業実施日", datetime.today())
        cost = st.number_input("かかった費用（円）", min_value=0, step=1000)
        submitted = st.form_submit_button("この内容でスプレッドシートに保存")

        if submitted:
            if not equip_name or not work_desc:
                st.error("「設備名」と「作業内容」を入力してください。")
            else:
                new_row = pd.DataFrame([{
                    "設備名": equip_name,
                    "最終点検日": work_date.strftime('%Y-%m-%d'),
                    "作業内容": work_desc,
                    "費用": cost
                }])
                updated_df = pd.concat([df, new_row], ignore_index=True)
                conn.update(worksheet="maintenance_data", data=updated_df)
                st.success("スプレッドシートへの保存が完了しました！")
                st.rerun()
