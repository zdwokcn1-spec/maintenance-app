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

# --- サイドバーで期間選択 ---
st.sidebar.header("📅 表示期間の絞り込み")
min_date = df['最終点検日'].min().date() if not df.empty else datetime.today().date() - timedelta(days=365)
max_date = datetime.today().date()
start_date, end_date = st.sidebar.date_input("期間を選択", value=(min_date, max_date))

# フィルタリング
mask = (df['最終点検日'].dt.date >= start_date) & (df['最終点検日'].dt.date <= end_date)
filtered_df = df.loc[mask]

# --- タブ設定 ---
tab1, tab2, tab3, tab4 = st.tabs(["📊 ダッシュボード", "📁 過去履歴", "📦 在庫管理", "📝 メンテナンス登録"])

# (1.ダッシュボード と 2.過去履歴 は前回と同じため省略可ですが、一貫性のために含めています)
with tab1:
    st.header(f"📊 メンテナンス状況 ({start_date} ～ {end_date})")
    if not filtered_df.empty:
        col1, col2, col3 = st.columns(3)
        col1.metric("選択期間の回数", f"{len(filtered_df)} 回")
        col2.metric("選択期間の費用", f"{filtered_df['費用'].sum():,} 円")
        col3.metric("対象設備数", f"{filtered_df['設備名'].nunique()} 種類")
    else:
        st.info("データがありません。")

with tab2:
    st.header("📁 メンテナンス過去履歴")
    st.dataframe(filtered_df, use_container_width=True)

# ================================================================
# 📦 3. 在庫管理（分類機能付き）
# ================================================================
with tab3:
    st.header("📦 部品在庫管理")
    
    # 大分類のリスト
    categories = ["すべて", "ジョークラッシャ", "インパクトクラッシャー", "スクリーン", "ベルト", "その他"]
    selected_cat = st.selectbox("表示する分類を選択してください", categories)

    # フィルタリング表示
    display_stock = stock_df.copy()
    if selected_cat != "すべて":
        if "分類" in display_stock.columns:
            display_stock = display_stock[display_stock["分類"] == selected_cat]
        else:
            st.warning("スプレッドシートに『分類』列がありません。新しく登録すると作成されます。")

    st.subheader(f"【{selected_cat}】の在庫一覧")
    st.dataframe(display_stock, use_container_width=True)

    with st.expander("新しい部品を登録 / 在庫を更新する"):
        with st.form("stock_form_new"):
            st.write("※新しい部品を登録する際は、分類を選択してください。")
            new_cat = st.selectbox("分類", categories[1:]) # 「すべて」以外
            new_name = st.text_input("個別部品名（例：トグルプレート、Vベルトなど）")
            new_qty = st.number_input("在庫数", min_value=0, step=1)
            new_price = st.number_input("単価（円）", min_value=0)
            new_reorder = st.number_input("発注点", min_value=0, value=5)
            
            s_submit = st.form_submit_button("在庫データを保存")

            if s_submit and new_name:
                # 既存データに「分類」列がない場合の対策
                if "分類" not in stock_df.columns:
                    stock_df["分類"] = "未分類"
                
                # 更新または追加
                if new_name in stock_df["部品名"].values:
                    stock_df.loc[stock_df["部品名"] == new_name, ["分類", "在庫数", "単価", "発注点", "最終更新日"]] = \
                        [new_cat, new_qty, new_price, new_reorder, datetime.now().strftime('%Y-%m-%d')]
                else:
                    add_row = pd.DataFrame([{"分類": new_cat, "部品名": new_name, "在庫数": new_qty, "単価": new_price, "発注点": new_reorder, "最終更新日": datetime.now().strftime('%Y-%m-%d')}])
                    stock_df = pd.concat([stock_df, add_row], ignore_index=True)
                
                conn.update(worksheet="stock_data", data=stock_df)
                st.success(f"「{new_cat}」の「{new_name}」を保存しました。")
                st.rerun()

# ================================================================
# 📝 4. メンテナンス登録
# ================================================================
with tab4:
    st.header("📝 メンテナンス記録の入力")
    with st.form("mainte_form_new"):
        # 設備名も選択式にすると入力が楽になります
        e_name = st.selectbox("対象設備", ["ジョークラッシャ", "インパクトクラッシャー", "スクリーン", "ベルト", "その他"])
        e_detail = st.text_input("具体的な機番・名称（例：No.1ベルト）")
        w_desc = st.text_area("作業内容")
        w_date = st.date_input("作業日", datetime.today())
        w_cost = st.number_input("費用", min_value=0)
        
        if st.form_submit_button("保存"):
            full_name = f"[{e_name}] {e_detail}"
            new_row = pd.DataFrame([{"設備名": full_name, "最終点検日": w_date.strftime('%Y-%m-%d'), "作業内容": w_desc, "費用": w_cost}])
            df = pd.concat([df, new_row], ignore_index=True)
            conn.update(worksheet="maintenance_data", data=df)
            st.success("保存しました")
            st.rerun()
