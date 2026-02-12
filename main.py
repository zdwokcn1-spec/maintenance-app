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

# 備考列がない場合の初期化
if '備考' not in df.columns:
    df['備考'] = ""

# 日付型に変換
df['最終点検日'] = pd.to_datetime(df['最終点検日'], errors='coerce')

# --- サイドバー：期間絞り込み ---
st.sidebar.header("📅 表示期間の絞り込み")
# データの最小日を取得（データがなければ1年前）
min_date_val = df['最終点検日'].min().date() if not df.empty and pd.notnull(df['最終点検日'].min()) else datetime.today().date() - timedelta(days=365)
max_date_val = datetime.today().date()

start_date, end_date = st.sidebar.date_input("期間を選択", value=(min_date_val, max_date_val))

# データを期間でフィルタリング
mask = (df['最終点検日'].dt.date >= start_date) & (df['最終点検日'].dt.date <= end_date)
filtered_df = df.loc[mask].copy()

# --- タブ設定 ---
tab1, tab2, tab3, tab4 = st.tabs(["📊 ダッシュボード", "📁 過去履歴", "📦 在庫管理", "📝 メンテナンス登録"])

# ================================================================
# 📊 1. ダッシュボード（グラフ表示部分を強化）
# ================================================================
with tab1:
    st.header(f"📊 メンテナンス状況概況")
    
    if not filtered_df.empty:
        col1, col2, col3 = st.columns(3)
        col1.metric("選択期間の回数", f"{len(filtered_df)} 回")
        col2.metric("選択期間の費用", f"{filtered_df['費用'].sum():,} 円")
        col3.metric("平均費用/回", f"{int(filtered_df['費用'].mean()):,} 円")

        # グラフ描画
        st.subheader("📈 月別メンテナンス費用推移")
        # 月ごとに集計
        df_monthly = filtered_df.set_index('最終点検日').resample('M')['費用'].sum().reset_index()
        
        if not df_monthly.empty and df_monthly['費用'].sum() > 0:
            fig, ax = plt.subplots(figsize=(10, 4))
            ax.bar(df_monthly['最終点検日'].dt.strftime('%Y-%m'), df_monthly['費用'], color='#0073e6')
            ax.set_ylabel("費用（円）")
            plt.xticks(rotation=45)
            st.pyplot(fig)
        else:
            st.info("集計可能な費用のデータがありません。")
    else:
        st.warning("選択された期間にデータが見つかりません。左側のメニューで期間を広げてください。")

# ================================================================
# 📁 2. 過去履歴（修正・削除機能）
# ================================================================
with tab2:
    st.header("📁 メンテナンス過去履歴")
    st.dataframe(filtered_df.sort_values(by="最終点検日", ascending=False), use_container_width=True)

    st.markdown("---")
    st.subheader("🛠️ 履歴データの修正・削除")
    
    if not df.empty:
        df['label'] = df['最終点検日'].dt.strftime('%Y-%m-%d') + " | " + df['設備名']
        target_label = st.selectbox("修正または削除する履歴を選択", df['label'].tolist())
        target_idx = df[df['label'] == target_label].index[0]
        item_data = df.iloc[target_idx]

        col_h1, col_h2 = st.columns(2)
        with col_h1:
            with st.form("edit_history_form"):
                new_date = st.date_input("作業日", value=item_data["最終点検日"])
                new_equip = st.text_input("設備名", value=item_data["設備名"])
                new_desc = st.text_area("作業内容", value=item_data["作業内容"])
                new_note = st.text_area("備考", value=item_data.get("備考", ""))
                new_cost = st.number_input("費用", value=int(item_data["費用"]), min_value=0)
                if st.form_submit_button("修正を保存"):
                    df.loc[target_idx, ["最終点検日", "設備名", "作業内容", "備考", "費用"]] = \
                        [pd.to_datetime(new_date), new_equip, new_desc, new_note, new_cost]
                    conn.update(worksheet="maintenance_data", data=df.drop(columns=['label']))
                    st.rerun()
        with col_h2:
            if st.button("この履歴を削除"):
                df = df.drop(target_idx)
                conn.update(worksheet="maintenance_data", data=df.drop(columns=['label']))
                st.rerun()

# --- 在庫管理と登録は前回同様 ---
with tab3:
    st.header("📦 部品在庫管理")
    categories = ["すべて", "ジョークラッシャ", "インパクトクラッシャー", "スクリーン", "ベルト", "その他"]
    selected_cat = st.selectbox("表示する分類を選択", categories)
    d_stock = stock_df.copy()
    if selected_cat != "すべて" and "分類" in d_stock.columns:
        d_stock = d_stock[d_stock["分類"] == selected_cat]
    st.dataframe(d_stock, use_container_width=True)

with tab4:
    st.header("📝 メンテナンス記録の入力")
    with st.form("mainte_reg_form"):
        e_name = st.selectbox("対象設備", ["ジョークラッシャ", "インパクトクラッシャー", "スクリーン", "ベルト", "その他"])
        e_detail = st.text_input("機番・詳細名称")
        w_desc = st.text_area("作業内容")
        w_note = st.text_area("備考（業者名など）")
        w_date = st.date_input("作業日", datetime.today())
        w_cost = st.number_input("費用", min_value=0)
        if st.form_submit_button("保存"):
            new_row = pd.DataFrame([{"設備名": f"[{e_name}] {e_detail}", "最終点検日": w_date.strftime('%Y-%m-%d'), "作業内容": w_desc, "備考": w_note, "費用": w_cost}])
            df_final = pd.concat([df.drop(columns=['label'], errors='ignore'), new_row], ignore_index=True)
            conn.update(worksheet="maintenance_data", data=df_final)
            st.rerun()
