import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import japanize_matplotlib
from streamlit_gsheets import GSheetsConnection
import base64
from PIL import Image
import io

# --- ページ設定 ---
st.set_page_config(page_title="設備メンテナンス管理", layout="wide")

# ---------- データ読み込み ----------
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    # キャッシュを無効にして強制読み込み
    df = conn.read(worksheet="maintenance_data", ttl="0")
    stock = conn.read(worksheet="stock_data", ttl="0")
    return df, stock

df_raw, stock_df_raw = load_data()

# --- 列名の強制修復ロジック (KeyError対策) ---
def fix_columns(df, target_cols):
    if df.empty:
        return pd.DataFrame(columns=target_cols)
    # 現在の列名を取得
    current_cols = df.columns.tolist()
    # 足りない列があれば追加
    for col in target_cols:
        if col not in current_cols:
            df[col] = ""
    return df[target_cols] # 必要な列だけを抽出・並び替え

# メンテナンスデータの列固定
m_cols = ['設備名', '最終点検日', '作業内容', '費用', '備考', '画像']
df = fix_columns(df_raw, m_cols)

# 在庫データの列固定
s_cols = ['分類', '部品名', '在庫数', '単価', '発注点', '最終更新日']
stock_df = fix_columns(stock_df_raw, s_cols)

# --- データクリーニング ---
# 画像列を安全に処理
df['画像'] = df['画像'].fillna("").astype(str).replace(['0', '0.0', 'nan'], "")

# 日付型への変換（エラーを無視してNaTにする）
df['最終点検日'] = pd.to_datetime(df['最終点検日'], errors='coerce')
# 日付が壊れている場合は今日にする
df['最終点検日'] = df['最終点検日'].fillna(pd.Timestamp(datetime.today()))

# 数値列のクリーニング
df['費用'] = pd.to_numeric(df['費用'], errors='coerce').fillna(0).astype(int)
stock_df['在庫数'] = pd.to_numeric(stock_df['在庫数'], errors='coerce').fillna(0).astype(int)

# --- 画像処理関数（圧縮強化） ---
def image_to_base64(uploaded_file):
    if uploaded_file is not None:
        img = Image.open(uploaded_file)
        img.thumbnail((400, 400)) 
        if img.mode != 'RGB':
            img = img.convert('RGB')
        buffered = io.BytesIO()
        img.save(buffered, format="JPEG", quality=60, optimize=True)
        return base64.b64encode(buffered.getvalue()).decode()
    return None

# --- タブ状態管理 ---
query_params = st.query_params
default_tab = int(query_params.get("tab", 1))
tab_titles = ["📊 ダッシュボード", "📁 過去履歴", "📦 在庫管理", "📝 メンテナンス登録"]
tabs = st.tabs(tab_titles)

def set_tab(index):
    st.query_params["tab"] = index

categories = ["すべて", "ジョークラッシャ", "インパクトクラッシャー", "スクリーン", "ベルト", "その他"]

# ================================================================
# 📊 1. ダッシュボード
# ================================================================
with tabs[0]:
    set_tab(0)
    st.header("📊 メンテナンス状況概況")
    if not df.empty and len(df) > 0:
        df['大分類'] = df['設備名'].str.extract(r'\[(.*?)\]')[0].fillna("その他")
        col_g1, col_g2 = st.columns(2)
        with col_g1:
            st.subheader("💰 設備別・累計費用")
            cost_by_equip = df.groupby('大分類')['費用'].sum().sort_values(ascending=True)
            fig1, ax1 = plt.subplots(); cost_by_equip.plot(kind='barh', ax=ax1, color='#2ecc71'); st.pyplot(fig1)
        with col_g2:
            st.subheader("📈 月別・設備別の費用推移")
            df_trend = df.copy()
            df_trend['年月'] = df_trend['最終点検日'].dt.strftime('%Y-%m')
            pivot_df = df_trend.pivot_table(index='年月', columns='大分類', values='費用', aggfunc='sum').fillna(0)
            fig2, ax2 = plt.subplots(); pivot_df.plot(kind='line', marker='o', ax=ax2); st.pyplot(fig2)

# ================================================================
# 📁 2. 過去履歴 (修正・削除)
# ================================================================
with tabs[1]:
    set_tab(1)
    st.header("📁 メンテナンス過去履歴")
    
    # 履歴表示
    sorted_df = df.sort_values(by="最終点検日", ascending=False)
    for i, row in sorted_df.iterrows():
        with st.expander(f"{row['最終点検日'].strftime('%Y-%m-%d')} | {row['設備名']}"):
            c1, c2 = st.columns([2, 1])
            with c1:
                st.write(f"**内容:** {row['作業内容']}\n\n**備考:** {row['備考']}\n\n**費用:** {row['費用']:,} 円")
            with c2:
                img_data = row.get('画像', "")
                if len(img_data) > 20:
                    try:
                        st.image(base64.b64decode(img_data), use_container_width=True)
                    except:
                        st.warning("画像表示不可")
                else:
                    st.info("写真なし")

    st.markdown("---")
    st.subheader("🛠️ 履歴の修正・写真追加")
    if not df.empty:
        df['label'] = df['最終点検日'].dt.strftime('%Y-%m-%d') + " | " + df['設備名'].astype(str)
        target_h = st.selectbox("修正対象を選択", df['label'].tolist())
        idx_h = df[df['label'] == target_h].index[0]
        curr_h = df.iloc[idx_h]
        
        with st.form("edit_h_form"):
            col_ea, col_eb = st.columns(2)
            with col_ea:
                new_date = st.date_input("作業日", curr_h["最終点検日"])
                new_equip = st.text_input("設備名", curr_h["設備名"])
                new_cost = st.number_input("費用", value=int(curr_h["費用"]))
            with col_eb:
                new_note = st.text_area("備考", curr_h["備考"])
                new_file = st.file_uploader("写真を変更", type=['jpg', 'jpeg', 'png'])
            new_desc = st.text_area("作業内容", curr_h["作業内容"])
            
            if st.form_submit_button("修正保存"):
                img_b = image_to_base64(new_file)
                if img_b: df.loc[idx_h, "画像"] = img_b
                df.loc[idx_h, ["最終点検日", "設備名", "作業内容", "備考", "費用"]] = [pd.to_datetime(new_date), new_equip, new_desc, new_note, new_cost]
                conn.update(worksheet="maintenance_data", data=df.drop(columns=['label'], errors='ignore'))
                st.rerun()
        if st.button("🚨 削除"):
            conn.update(worksheet="maintenance_data", data=df.drop(idx_h).drop(columns=['label'], errors='ignore'))
            st.rerun()

# ================================================================
# 📦 3. 在庫管理 (統合版)
# ================================================================
with tabs[2]:
    set_tab(2)
    st.header("📦 部品在庫管理")
    
    v_cat = st.selectbox("分類フィルタ", categories, key="v_cat")
    d_stock = stock_df.copy()
    if v_cat != "すべて": d_stock = d_stock[d_stock["分類"] == v_cat]
    st.dataframe(d_stock, use_container_width=True)

    with st.expander("➕ 新規登録"):
        with st.form("new_stock"):
            nc = st.selectbox("分類", categories[1:])
            nn = st.text_input("部品名")
            nq = st.number_input("在庫数", min_value=0)
            np = st.number_input("単価", min_value=0)
            if st.form_submit_button("登録"):
                new_s = pd.DataFrame([{"分類": nc, "部品名": nn, "在庫数": nq, "単価": np, "発注点": 5, "最終更新日": datetime.now().strftime('%Y-%m-%d')}])
                conn.update(worksheet="stock_data", data=pd.concat([stock_df, new_s], ignore_index=True))
                st.rerun()

    st.markdown("---")
    st.subheader("🛠️ 在庫修正")
    s_cat = st.selectbox("分類検索", categories[1:], key="s_cat")
    f_items = stock_df[stock_df["分類"] == s_cat]
    if not f_items.empty:
        t_item = st.selectbox("部品名", f_items["部品名"].tolist())
        s_row = stock_df[stock_df["部品名"] == t_item].iloc[0]
        with st.form("edit_stock"):
            eq = st.number_input("在庫数", value=int(s_row["在庫数"]))
            ep = st.number_input("単価", value=int(s_row["単価"]))
            if st.form_submit_button("保存"):
                stock_df.loc[stock_df["部品名"] == t_item, ["在庫数", "単価", "最終更新日"]] = [eq, ep, datetime.now().strftime('%Y-%m-%d')]
                conn.update(worksheet="stock_data", data=stock_df)
                st.rerun()

# ================================================================
# 📝 4. メンテナンス登録
# ================================================================
with tabs[3]:
    set_tab(3)
    st.header("📝 メンテナンス記録の入力")
    with st.form("mainte_reg", clear_on_submit=True):
        en = st.selectbox("対象設備", categories[1:])
        ed = st.text_input("機番・詳細名称")
        wd = st.text_area("作業内容")
        wt = st.date_input("作業日", datetime.today())
        wc = st.number_input("費用", min_value=0)
        wn = st.text_area("備考")
        up_file = st.file_uploader("写真", type=['jpg', 'jpeg', 'png'])
        
        if st.form_submit_button("保存"):
            img_b = image_to_base64(up_file) if up_file else ""
            new_r = pd.DataFrame([{"設備名": f"[{en}] {ed}", "最終点検日": wt.strftime('%Y-%m-%d'), "作業内容": wd, "費用": wc, "備考": wn, "画像": img_b}])
            conn.update(worksheet="maintenance_data", data=pd.concat([df.drop(columns=['label'], errors='ignore'), new_r], ignore_index=True))
            st.rerun()
