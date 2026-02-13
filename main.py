import streamlit as st
import pandas as pd
from datetime import datetime
import matplotlib.pyplot as plt
import japanize_matplotlib
from streamlit_gsheets import GSheetsConnection
import base64
from PIL import Image
import io
import time

# --- ページ設定 ---
st.set_page_config(page_title="設備メンテナンス管理", layout="wide")

# --- セッション管理 (タブ状態の維持) ---
if "active_tab" not in st.session_state:
    st.session_state.active_tab = "📁 過去履歴"

# ---------- データ読み込み (API負荷軽減版) ----------
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    try:
        # ttl=1sで過剰なリクエストを防止
        df = conn.read(worksheet="maintenance_data", ttl="1s")
        stock = conn.read(worksheet="stock_data", ttl="1s")
        return df, stock
    except Exception as e:
        st.error("Google Sheetsへのアクセス制限中です。しばらく待ってから更新してください。")
        st.stop()

df_raw, stock_df_raw = load_data()

# --- 列名の修復 ---
def fix_columns(df, target_cols):
    if df is None or df.empty: return pd.DataFrame(columns=target_cols)
    for col in target_cols:
        if col not in df.columns: df[col] = ""
    return df[target_cols]

df = fix_columns(df_raw, ['設備名', '最終点検日', '作業内容', '費用', '備考', '画像'])
stock_df = fix_columns(stock_df_raw, ['分類', '部品名', '在庫数', '単価', '発注点', '最終更新日'])

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

# --- メニュー選択 (タブ固定用ラジオボタン) ---
tab_titles = ["📊 ダッシュボード", "📁 過去履歴", "📦 在庫管理", "📝 メンテナンス登録"]
# session_stateを使って選択状態を同期
selected_tab = st.radio("メニュー", tab_titles, horizontal=True, label_visibility="collapsed", index=tab_titles.index(st.session_state.active_tab))
st.session_state.active_tab = selected_tab

# ================================================================
# 📊 0. ダッシュボード
# ================================================================
if st.session_state.active_tab == "📊 ダッシュボード":
    st.header("📊 メンテナンス状況概況")
    if not df.empty:
        df['大分類'] = df['設備名'].str.extract(r'\[(.*?)\]')[0].fillna("その他")
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("💰 設備別・累計費用")
            cost_by_equip = df.groupby('大分類')['費用'].sum().sort_values(ascending=True)
            fig1, ax1 = plt.subplots(); cost_by_equip.plot(kind='barh', ax=ax1, color='#2ecc71'); st.pyplot(fig1)

# ================================================================
# 📁 1. 過去履歴 (削除ボタン復活版)
# ================================================================
elif st.session_state.active_tab == "📁 過去履歴":
    st.header("📁 メンテナンス過去履歴")
    if not df.empty:
        # 履歴一覧表示
        sorted_df = df.sort_values(by="最終点検日", ascending=False)
        for i, row in sorted_df.iterrows():
            with st.expander(f"{row['最終点検日'].strftime('%Y-%m-%d')} | {row['設備名']}"):
                col_v1, col_v2 = st.columns([2, 1])
                with col_v1:
                    st.write(f"**作業内容:** {row['作業内容']}")
                    st.write(f"**備考:** {row['備考']}")
                    st.write(f"**費用:** {row['費用']:,} 円")
                with col_v2:
                    if len(str(row['画像'])) > 20:
                        st.image(base64.b64decode(row['画像']), use_container_width=True)
                    else: st.info("写真なし")
        
        st.markdown("---")
        st.subheader("🛠️ 履歴の修正・削除")
        df['label'] = df['最終点検日'].dt.strftime('%Y-%m-%d') + " | " + df['設備名'].astype(str)
        target_h = st.selectbox("対象の履歴を選択", df['label'].tolist(), key="h_fix_sel")
        idx_h = df[df['label'] == target_h].index[0]
        curr_h = df.iloc[idx_h]
        
        with st.form("edit_h_form"):
            ca, cb = st.columns(2)
            new_date = ca.date_input("作業日", curr_h["最終点検日"])
            new_equip = ca.text_input("設備名", curr_h["設備名"])
            new_cost = ca.number_input("費用", value=int(curr_h["費用"]))
            new_note = cb.text_area("備考", curr_h["備考"])
            new_file = cb.file_uploader("写真変更", type=['jpg', 'jpeg', 'png'])
            new_desc = st.text_area("作業内容", curr_h["作業内容"])
            
            if st.form_submit_button("修正内容を保存"):
                img_b = image_to_base64(new_file)
                if img_b: df.loc[idx_h, "画像"] = img_b
                df.loc[idx_h, ["最終点検日", "設備名", "作業内容", "備考", "費用"]] = [pd.to_datetime(new_date), new_equip, new_desc, new_note, new_cost]
                conn.update(worksheet="maintenance_data", data=df.drop(columns=['label'], errors='ignore'))
                time.sleep(1)
                st.rerun()

        # --- ここに削除ボタンを復活 ---
        st.warning("⚠️ この履歴を完全に削除しますか？")
        if st.button("🚨 履歴を完全に削除する", key="h_del_btn"):
            # 選択したインデックスの行を削除
            updated_df = df.drop(idx_h).drop(columns=['label'], errors='ignore')
            conn.update(worksheet="maintenance_data", data=updated_df)
            st.success("削除が完了しました")
            time.sleep(1)
            st.rerun()

# ================================================================
# 📦 2. 在庫管理
# ================================================================
elif st.session_state.active_tab == "📦 在庫管理":
    st.header("📦 部品在庫管理")
    v_cat = st.selectbox("分類フィルタ", ["すべて", "ジョークラッシャ", "インパクトクラッシャー", "スクリーン", "ベルト", "その他"], key="stk_filter")
    d_stock = stock_df.copy()
    if v_cat != "すべて": d_stock = d_stock[d_stock["分類"] == v_cat]
    st.dataframe(d_stock, use_container_width=True)

    st.markdown("---")
    st.subheader("🛠️ 在庫の修正・削除")
    s_cat_sel = st.selectbox("分類選択", ["ジョークラッシャ", "インパクトクラッシャー", "スクリーン", "ベルト", "その他"], key="stk_cat_sel")
    f_items = stock_df[stock_df["分類"] == s_cat_sel]
    
    if not f_items.empty:
        t_item = st.selectbox("部品名を選択", f_items["部品名"].tolist(), key="stk_item_sel")
        s_idx = stock_df[stock_df["部品名"] == t_item].index[0]
        s_row = stock_df.loc[s_idx]
        
        with st.form("edit_stk_form"):
            c1, c2 = st.columns(2)
            eq = c1.number_input("在庫数", value=int(s_row["在庫数"]))
            ep = c2.number_input("単価", value=int(s_row["単価"]))
            if st.form_submit_button("在庫数を更新保存"):
                stock_df.loc[s_idx, ["在庫数", "単価", "最終更新日"]] = [eq, ep, datetime.now().strftime('%Y-%m-%d')]
                conn.update(worksheet="stock_data", data=stock_df)
                time.sleep(1)
                st.rerun()
        
        if st.button(f"🗑️ {t_item} をデータから削除", key="stk_del"):
            conn.update(worksheet="stock_data", data=stock_df[stock_df["部品名"] != t_item])
            time.sleep(1)
            st.rerun()

# ================================================================
# 📝 3. メンテナンス登録
# ================================================================
elif st.session_state.active_tab == "📝 メンテナンス登録":
    st.header("📝 メンテナンス記録の入力")
    with st.form("reg_form", clear_on_submit=True):
        en = st.selectbox("対象設備", ["ジョークラッシャ", "インパクトクラッシャー", "スクリーン", "ベルト", "その他"], key="reg_cat")
        ed = st.text_input("機番・詳細名称")
        wt = st.date_input("作業日", datetime.today())
        wc = st.number_input("費用", min_value=0)
        wd, wn = st.text_area("作業内容"), st.text_area("備考")
        up_file = st.file_uploader("写真", type=['jpg', 'jpeg', 'png'])
        if st.form_submit_button("保存"):
            img_b = image_to_base64(up_file) if up_file else ""
            new_r = pd.DataFrame([{"設備名": f"[{en}] {ed}", "最終点検日": wt.strftime('%Y-%m-%d'), "作業内容": wd, "費用": wc, "備考": wn, "画像": img_b}])
            conn.update(worksheet="maintenance_data", data=pd.concat([df.drop(columns=['label'], errors='ignore'), new_r], ignore_index=True))
            time.sleep(1)
            st.rerun()
