import streamlit as st
import pandas as pd
from datetime import datetime
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import japanize_matplotlib  # 日本語文字化け防止
from streamlit_gsheets import GSheetsConnection

# --- ページ設定 ---
st.set_page_config(page_title="設備メンテナンス管理", layout="wide")

# ---------- データ読み込み（Googleスプレッドシート接続） ----------
# Streamlit CloudのSecretsに設定した情報を使って接続します
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data(worksheet_name):
    # 指定したシート（タブ）を読み込む
    return conn.read(worksheet=worksheet_name, ttl="0")

# データの読み込み
try:
    df = load_data("maintenance_data")
    stock_df = load_data("stock_data")
    
    # 日付列の型変換
    df['最終点検日'] = pd.to_datetime(df['最終点検日'], errors='coerce')
    stock_df['最終更新日'] = pd.to_datetime(stock_df['最終更新日'], errors='coerce')
except Exception:
    st.error("スプレッドシートの読み込みに失敗しました。Secretsの設定とシート名を確認してください。")
    st.stop()

# --- 中央タブ ---
tab1, tab2, tab3, tab4 = st.tabs(["📊 ダッシュボード", "📁 過去履歴", "📦 在庫管理", "📝 メンテナンス登録"])

# ================================================================
# 📦 3. 在庫管理
# ================================================================
with tab3:
    st.header("📦 部品在庫管理")
    st.subheader("在庫一覧")
    st.dataframe(stock_df)

    with st.form("stock_form"):
        name = st.text_input("部品名")
        qty = st.number_input("在庫数", min_value=0, step=1)
        price = st.number_input("単価（円）", min_value=0)
        reorder = st.number_input("発注点", min_value=0, value=5)
        s_submit = st.form_submit_button("登録 / 更新")

        if s_submit and name:
            new_stock = stock_df.copy()
            # 既存なら更新、新規なら追加
            if name in new_stock["部品名"].values:
                new_stock.loc[new_stock["部品名"] == name, ["在庫数", "単価", "発注点", "最終更新日"]] = [qty, price, reorder, datetime.now()]
            else:
                add_row = pd.DataFrame([{"部品名": name, "在庫数": qty, "単価": price, "発注点": reorder, "最終更新日": datetime.now()}])
                new_stock = pd.concat([new_stock, add_row], ignore_index=True)
            
            # スプレッドシートに書き込み
            conn.update(worksheet="stock_data", data=new_stock)
            st.success(f"「{name}」を保存しました。")
            st.rerun()

# ================================================================
# 📝 4. メンテナンス登録
# ================================================================
with tab4:
    st.header("📝 メンテナンス作業登録")
    with st.form("maintenance_form"):
        equip_name = st.text_input("設備名")
        work_desc = st.text_area("作業内容")
        work_date = st.date_input("作業日", datetime.today())
        cost = st.number_input("費用（円）", min_value=0, step=1000)
        submitted = st.form_submit_button("登録する")

        if submitted:
            if not equip_name or not work_desc:
                st.error("「設備名」と「作業内容」は必須です。")
            else:
                # 登録データの作成
                new_row = pd.DataFrame([{
                    "設備名": equip_name,
                    "最終点検日": work_date.strftime('%Y-%m-%d'),
                    "作業内容": work_desc,
                    "費用": cost
                }])
                
                # 既存データと結合してスプレッドシートを更新
                updated_df = pd.concat([df, new_row], ignore_index=True)
                conn.update(worksheet="maintenance_data", data=updated_df)
                
                st.success(f"「{equip_name}」の記録を保存しました。")
                st.rerun()