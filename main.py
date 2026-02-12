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

# ================================================================
# 📊 1. ダッシュボード
# ================================================================
with tab1:
    st.header(f"📊 メンテナンス状況概況")
    if not filtered_df.empty:
        col1, col2, col3 = st.columns(3)
        col1.metric("選択期間の回数", f"{len(filtered_df)} 回")
        col2.metric("選択期間の費用", f"{filtered_df['費用'].sum():,} 円")
    else: st.info("データがありません。")

# ================================================================
# 📁 2. 過去履歴（修正・削除機能追加）
# ================================================================
with tab2:
    st.header("📁 メンテナンス過去履歴")
    st.dataframe(filtered_df.sort_values(by="最終点検日", ascending=False), use_container_width=True)

    st.markdown("---")
    st.subheader("🛠️ 履歴データの修正・削除")
    
    if not df.empty:
        # 修正対象を特定するためのラベル作成（日付 - 設備名）
        df['label'] = df['最終点検日'].dt.strftime('%Y-%m-%d') + " | " + df['設備名']
        target_label = st.selectbox("修正または削除する履歴を選択", df['label'].tolist())
        target_idx = df[df['label'] == target_label].index[0]
        item_data = df.iloc[target_idx]

        col_h1, col_h2 = st.columns(2)
        with col_h1:
            st.write("📝 **履歴を修正する**")
            with st.form("edit_history_form"):
                new_date = st.date_input("作業日", value=item_data["最終点検日"])
                new_equip = st.text_input("設備名", value=item_data["設備名"])
                new_desc = st.text_area("作業内容", value=item_data["作業内容"])
                new_cost = st.number_input("費用", value=int(item_data["費用"]), min_value=0)
                
                if st.form_submit_button("履歴の修正を保存"):
                    df.loc[target_idx, ["最終点検日", "設備名", "作業内容", "費用"]] = \
                        [pd.to_datetime(new_date), new_equip, new_desc, new_cost]
                    # 不要なラベル列を削除して保存
                    conn.update(worksheet="maintenance_data", data=df.drop(columns=['label']))
                    st.success("履歴を修正しました。")
                    st.rerun()

        with col_h2:
            st.write("🗑️ **履歴を削除する**")
            st.warning("この操作は取り消せません。")
            if st.button("この履歴を完全に削除"):
                df = df.drop(target_idx)
                conn.update(worksheet="maintenance_data", data=df.drop(columns=['label']))
                st.error("履歴を削除しました。")
                st.rerun()

# ================================================================
# 📦 3. 在庫管理（前回同様）
# ================================================================
with tab3:
    st.header("📦 部品在庫管理")
    categories = ["すべて", "ジョークラッシャ", "インパクトクラッシャー", "スクリーン", "ベルト", "その他"]
    selected_cat = st.selectbox("表示する分類を選択", categories)
    display_stock = stock_df.copy()
    if selected_cat != "すべて" and "分類" in display_stock.columns:
        display_stock = display_stock[display_stock["分類"] == selected_cat]
    st.dataframe(display_stock, use_container_width=True)

    st.markdown("---")
    st.subheader("🛠️ 在庫データの修正・削除")
    if not stock_df.empty:
        target_item = st.selectbox("修正または削除する部品を選択", stock_df["部品名"].tolist())
        item_stock = stock_df[stock_df["部品名"] == target_item].iloc[0]
        col_s1, col_s2 = st.columns(2)
        with col_s1:
            with st.form("edit_stock_form"):
                edit_qty = st.number_input("在庫数", value=int(item_stock["在庫数"]), min_value=0)
                edit_price = st.number_input("単価", value=int(item_stock["単価"]), min_value=0)
                if st.form_submit_button("在庫を修正"):
                    stock_df.loc[stock_df["部品名"] == target_item, ["在庫数", "単価", "最終更新日"]] = [edit_qty, edit_price, datetime.now().strftime('%Y-%m-%d')]
                    conn.update(worksheet="stock_data", data=stock_df)
                    st.rerun()
        with col_s2:
            if st.button(f"「{target_item}」を削除"):
                stock_df = stock_df[stock_df["部品名"] != target_item]
                conn.update(worksheet="stock_data", data=stock_df)
                st.rerun()

# ================================================================
# 📝 4. メンテナンス登録（前回同様）
# ================================================================
with tab4:
    st.header("📝 メンテナンス記録の入力")
    with st.form("mainte_reg_form"):
        e_name = st.selectbox("対象設備", ["ジョークラッシャ", "インパクトクラッシャー", "スクリーン", "ベルト", "その他"])
        e_detail = st.text_input("機番・詳細名称")
        w_desc = st.text_area("作業内容")
        w_date = st.date_input("作業日", datetime.today())
        w_cost = st.number_input("費用", min_value=0)
        if st.form_submit_button("保存"):
            new_row = pd.DataFrame([{"設備名": f"[{e_name}] {e_detail}", "最終点検日": w_date.strftime('%Y-%m-%d'), "作業内容": w_desc, "費用": w_cost}])
            df_new = pd.concat([df.drop(columns=['label'], errors='ignore'), new_row], ignore_index=True)
            conn.update(worksheet="maintenance_data", data=df_new)
            st.success("保存しました")
            st.rerun()
