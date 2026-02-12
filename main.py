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
df['最終点検日'] = pd.to_datetime(df['最終点検日'], errors='coerce')

# --- サイドバー：期間絞り込み ---
st.sidebar.header("📅 表示期間の絞り込み")
min_date = df['最終点検日'].min().date() if not df.empty else datetime.today().date() - timedelta(days=365)
max_date = datetime.today().date()
start_date, end_date = st.sidebar.date_input("期間を選択", value=(min_date, max_date))

mask = (df['最終点検日'].dt.date >= start_date) & (df['最終点検日'].dt.date <= end_date)
filtered_df = df.loc[mask]

# --- タブ設定 ---
tab1, tab2, tab3, tab4 = st.tabs(["📊 ダッシュボード", "📁 過去履歴", "📦 在庫管理", "📝 メンテナンス登録"])

# 1&2は既存通り（省略せず含めます）
with tab1:
    st.header(f"📊 メンテナンス状況概況")
    if not filtered_df.empty:
        col1, col2, col3 = st.columns(3)
        col1.metric("選択期間の回数", f"{len(filtered_df)} 回")
        col2.metric("選択期間の費用", f"{filtered_df['費用'].sum():,} 円")
    else: st.info("データがありません。")

with tab2:
    st.header("📁 メンテナンス過去履歴")
    st.dataframe(filtered_df, use_container_width=True)

# ================================================================
# 📦 3. 在庫管理（修正・削除機能追加）
# ================================================================
with tab3:
    st.header("📦 部品在庫管理")
    
    categories = ["すべて", "ジョークラッシャ", "インパクトクラッシャー", "スクリーン", "ベルト", "その他"]
    selected_cat = st.selectbox("表示する分類を選択", categories)

    display_stock = stock_df.copy()
    if selected_cat != "すべて" and "分類" in display_stock.columns:
        display_stock = display_stock[display_stock["分類"] == selected_cat]

    st.subheader(f"【{selected_cat}】の在庫一覧")
    st.dataframe(display_stock, use_container_width=True)

    # --- 修正・削除セクション ---
    st.markdown("---")
    st.subheader("🛠️ 在庫データの修正・削除")
    
    if not stock_df.empty:
        # 修正したい部品を選択
        target_item = st.selectbox("修正または削除する部品を選択してください", stock_df["部品名"].tolist())
        item_data = stock_df[stock_df["部品名"] == target_item].iloc[0]

        col_edit1, col_edit2 = st.columns(2)
        
        with col_edit1:
            st.write("📝 **内容を修正する**")
            with st.form("edit_form"):
                edit_cat = st.selectbox("分類", categories[1:], index=categories[1:].index(item_data["分類"]) if "分類" in item_data else 0)
                edit_qty = st.number_input("在庫数", value=int(item_data["在庫数"]), min_value=0)
                edit_price = st.number_input("単価", value=int(item_data["単価"]), min_value=0)
                edit_reorder = st.number_input("発注点", value=int(item_data["発注点"]), min_value=0)
                
                if st.form_submit_button("修正内容を保存"):
                    stock_df.loc[stock_df["部品名"] == target_item, ["分類", "在庫数", "単価", "発注点", "最終更新日"]] = \
                        [edit_cat, edit_qty, edit_price, edit_reorder, datetime.now().strftime('%Y-%m-%d')]
                    conn.update(worksheet="stock_data", data=stock_df)
                    st.success(f"「{target_item}」を修正しました。")
                    st.rerun()

        with col_edit2:
            st.write("🗑️ **データを削除する**")
            st.warning(f"「{target_item}」を完全に削除しますか？")
            if st.button(f"「{target_item}」を削除する"):
                new_stock_df = stock_df[stock_df["部品名"] != target_item]
                conn.update(worksheet="stock_data", data=new_stock_df)
                st.error(f"「{target_item}」を削除しました。")
                st.rerun()
    
    # 新規登録（既存のexpander）
    with st.expander("➕ 新しい部品を新規登録する"):
        with st.form("stock_form_new"):
            new_cat = st.selectbox("分類を選択", categories[1:])
            new_name = st.text_input("個別部品名")
            new_qty = st.number_input("初期在庫数", min_value=0)
            if st.form_submit_button("新規登録"):
                if new_name:
                    add_row = pd.DataFrame([{"分類": new_cat, "部品名": new_name, "在庫数": new_qty, "単価": 0, "発注点": 5, "最終更新日": datetime.now().strftime('%Y-%m-%d')}])
                    stock_df = pd.concat([stock_df, add_row], ignore_index=True)
                    conn.update(worksheet="stock_data", data=stock_df)
                    st.rerun()

# 4.メンテナンス登録
with tab4:
    st.header("📝 メンテナンス記録の入力")
    with st.form("mainte_form_new"):
        e_name = st.selectbox("対象設備", ["ジョークラッシャ", "インパクトクラッシャー", "スクリーン", "ベルト", "その他"])
        e_detail = st.text_input("機番・詳細名称")
        w_desc = st.text_area("作業内容")
        w_date = st.date_input("作業日", datetime.today())
        w_cost = st.number_input("費用", min_value=0)
        if st.form_submit_button("記録を保存"):
            new_row = pd.DataFrame([{"設備名": f"[{e_name}] {e_detail}", "最終点検日": w_date.strftime('%Y-%m-%d'), "作業内容": w_desc, "費用": w_cost}])
            df = pd.concat([df, new_row], ignore_index=True)
            conn.update(worksheet="maintenance_data", data=df)
            st.success("保存しました")
            st.rerun()
