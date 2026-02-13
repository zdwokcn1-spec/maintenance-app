import streamlit as st
import pandas as pd
from datetime import datetime
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
    df = conn.read(worksheet="maintenance_data", ttl="0")
    stock = conn.read(worksheet="stock_data", ttl="0")
    return df, stock

df_raw, stock_df_raw = load_data()

# --- 列名の修復 (データ欠損防止) ---
def fix_columns(df, target_cols):
    if df.empty: return pd.DataFrame(columns=target_cols)
    for col in target_cols:
        if col not in df.columns: df[col] = ""
    return df[target_cols]

# 過去履歴に必要なすべての列を定義
m_cols = ['設備名', '最終点検日', '作業内容', '費用', '備考', '画像']
df = fix_columns(df_raw, m_cols)

# 在庫管理に必要なすべての列を定義
s_cols = ['分類', '部品名', '在庫数', '単価', '発注点', '最終更新日']
stock_df = fix_columns(stock_df_raw, s_cols)

# --- クリーニング ---
df['画像'] = df['画像'].fillna("").astype(str)
df['最終点検日'] = pd.to_datetime(df['最終点検日'], errors='coerce').fillna(pd.Timestamp(datetime.today()))
df['費用'] = pd.to_numeric(df['費用'], errors='coerce').fillna(0).astype(int)
stock_df['在庫数'] = pd.to_numeric(stock_df['在庫数'], errors='coerce').fillna(0).astype(int)

# --- 画像圧縮関数 ---
def image_to_base64(uploaded_file):
    if uploaded_file:
        img = Image.open(uploaded_file)
        img.thumbnail((400, 400))
        if img.mode != 'RGB': img = img.convert('RGB')
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=60, optimize=True)
        return base64.b64encode(buf.getvalue()).decode()
    return None

# --- タブ設定 (session_stateで現在タブを維持) ---
tab_titles = ["📊 ダッシュボード", "📁 過去履歴", "📦 在庫管理", "📝 メンテナンス登録"]
# URLパラメータやセッションを利用してタブ移動を防ぐ
tabs = st.tabs(tab_titles)

categories = ["すべて", "ジョークラッシャ", "インパクトクラッシャー", "スクリーン", "ベルト", "その他"]

# ================================================================
# 📊 0. ダッシュボード
# ================================================================
with tabs[0]:
    st.header("📊 メンテナンス状況概況")
    if not df.empty:
        df['大分類'] = df['設備名'].str.extract(r'\[(.*?)\]')[0].fillna("その他")
        c1, c2 = st.columns(2)
        with c1:
            cost_by_equip = df.groupby('大分類')['費用'].sum().sort_values(ascending=True)
            fig1, ax1 = plt.subplots(); cost_by_equip.plot(kind='barh', ax=ax1, color='#2ecc71'); st.pyplot(fig1)

# ================================================================
# 📁 1. 過去履歴 (詳細表示と全項目修正)
# ================================================================
with tabs[1]:
    st.header("📁 メンテナンス過去履歴")
    if not df.empty:
        # 一覧表示（すべての項目を表示）
        sorted_df = df.sort_values(by="最終点検日", ascending=False)
        for i, row in sorted_df.iterrows():
            with st.expander(f"{row['最終点検日'].strftime('%Y-%m-%d')} | {row['設備名']}"):
                col_view1, col_view2 = st.columns([2, 1])
                with col_view1:
                    st.write(f"**作業内容:** {row['作業内容']}")
                    st.write(f"**備考:** {row['備考']}")
                    st.write(f"**費用:** {row['費用']:,} 円")
                with col_view2:
                    if len(str(row['画像'])) > 20:
                        try:
                            st.image(base64.b64decode(row['画像']), use_container_width=True)
                        except:
                            st.error("画像読み込みエラー")
                    else:
                        st.info("写真なし")
        
        st.markdown("---")
        st.subheader("🛠️ 履歴の修正・削除")
        df['label'] = df['最終点検日'].dt.strftime('%Y-%m-%d') + " | " + df['設備名'].astype(str)
        target_h = st.selectbox("修正する履歴を選択", df['label'].tolist(), key="hist_sel_box")
        
        idx_h = df[df['label'] == target_h].index[0]
        curr_h = df.iloc[idx_h]
        
        with st.form("edit_history_form_full"):
            ca, cb = st.columns(2)
            new_date = ca.date_input("作業日", curr_h["最終点検日"])
            new_equip = ca.text_input("設備名", curr_h["設備名"])
            new_cost = ca.number_input("費用", value=int(curr_h["費用"]))
            new_note = cb.text_area("備考", curr_h["備考"])
            new_file = cb.file_uploader("写真変更", type=['jpg', 'jpeg', 'png'])
            new_desc = st.text_area("作業内容", curr_h["作業内容"])
            
            if st.form_submit_button("修正内容をスプレッドシートに保存"):
                img_b = image_to_base64(new_file)
                if img_b: df.loc[idx_h, "画像"] = img_b
                # すべての列を上書き
                df.loc[idx_h, ["最終点検日", "設備名", "作業内容", "備考", "費用"]] = [
                    pd.to_datetime(new_date), new_equip, new_desc, new_note, new_cost
                ]
                conn.update(worksheet="maintenance_data", data=df.drop(columns=['label'], errors='ignore'))
                st.success("履歴を更新しました")
                st.rerun()

        if st.button("🚨 この履歴を完全に削除", key="del_hist_btn"):
            conn.update(worksheet="maintenance_data", data=df.drop(idx_h).drop(columns=['label'], errors='ignore'))
            st.rerun()

# ================================================================
# 📦 2. 在庫管理 (部品選択時のダッシュボード戻り対策)
# ================================================================
with tabs[2]:
    st.header("📦 部品在庫管理")
    v_cat = st.selectbox("分類フィルタ", categories, key="stk_v_cat")
    d_stock = stock_df.copy()
    if v_cat != "すべて": d_stock = d_stock[d_stock["分類"] == v_cat]
    st.dataframe(d_stock, use_container_width=True)

    st.markdown("---")
    st.subheader("🛠️ 在庫の修正・削除")
    s_cat_sel = st.selectbox("分類選択", categories[1:], key="stk_s_cat")
    f_items = stock_df[stock_df["分類"] == s_cat_sel]
    
    if not f_items.empty:
        t_item = st.selectbox("部品名を選択", f_items["部品名"].tolist(), key="stk_item_name")
        s_idx = stock_df[stock_df["部品名"] == t_item].index[0]
        s_row = stock_df.loc[s_idx]
        
        with st.form("edit_stock_form_full"):
            c1, c2 = st.columns(2)
            eq = c1.number_input("在庫数", value=int(s_row["在庫数"]))
            ep = c2.number_input("単価", value=int(s_row["単価"]))
            if st.form_submit_button("在庫修正を保存"):
                stock_df.loc[s_idx, ["在庫数", "単価", "最終更新日"]] = [eq, ep, datetime.now().strftime('%Y-%m-%d')]
                conn.update(worksheet="stock_data", data=stock_df)
                st.rerun()
        
        if st.button(f"🗑️ {t_item} を削除", key="stk_del_btn"):
            conn.update(worksheet="stock_data", data=stock_df[stock_df["部品名"] != t_item])
            st.rerun()

# ================================================================
# 📝 3. メンテナンス登録
# ================================================================
with tabs[3]:
    st.header("📝 メンテナンス記録の入力")
    with st.form("main_reg_form_full", clear_on_submit=True):
        col_reg1, col_reg2 = st.columns(2)
        en = col_reg1.selectbox("対象設備", categories[1:], key="reg_cat_sel")
        ed = col_reg1.text_input("機番・詳細名称")
        wt = col_reg2.date_input("作業日", datetime.today())
        wc = col_reg2.number_input("費用", min_value=0)
        
        wd = st.text_area("作業内容")
        wn = st.text_area("備考 (交換部品や注意点など)")
        up_file = st.file_uploader("写真", type=['jpg', 'jpeg', 'png'])
        
        if st.form_submit_button("新規記録を保存"):
            img_b = image_to_base64(up_file) if up_file else ""
            new_r = pd.DataFrame([{
                "設備名": f"[{en}] {ed}", 
                "最終点検日": wt.strftime('%Y-%m-%d'), 
                "作業内容": wd, 
                "費用": wc, 
                "備考": wn,
                "画像": img_b
            }])
            conn.update(worksheet="maintenance_data", data=pd.concat([df.drop(columns=['label'], errors='ignore'), new_r], ignore_index=True))
            st.rerun()
