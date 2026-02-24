import streamlit as st
import pandas as pd
from datetime import datetime, date
import matplotlib.pyplot as plt
import japanize_matplotlib
from streamlit_gsheets import GSheetsConnection
import base64
from PIL import Image
import io
import time

# --- 1. ページ設定 ---
st.set_page_config(page_title="設備・在庫管理システム", layout="wide")

# --- 2. 権限管理 ---
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

with st.sidebar:
    st.title("🔑 権限管理")
    if not st.session_state["logged_in"]:
        user = st.text_input("ユーザー名")
        pw = st.text_input("パスワード", type="password")
        if st.button("編集モードでログイン"):
            if user == st.secrets["auth"]["username"] and pw == st.secrets["auth"]["password"]:
                st.session_state["logged_in"] = True
                st.rerun()
            else:
                st.error("認証失敗")
    else:
        st.success("✅ 編集モード：有効")
        if st.button("ログアウト"):
            st.session_state["logged_in"] = False
            st.rerun()

# --- 3. データ読み込み（TTL=0） ---
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    df = conn.read(worksheet="maintenance_data", ttl=0)
    stock = conn.read(worksheet="stock_data", ttl=0)
    return df, stock

df_raw, stock_df_raw = load_data()

# --- 4. メンテナンスデータ整形（TypeError対策強化） ---
m_cols = ['設備名', '最終点検日', '作業内容', '費用', '備考', '画像', '画像2']
df = df_raw.copy()

# すべての列が存在することを確認
for col in m_cols:
    if col not in df.columns:
        df[col] = ""

# ★【最重要】画像列のエラー対策：強制的に文字列化し、NaNを空文字にする
df['画像'] = df['画像'].fillna("").astype(str)
df['画像2'] = df['画像2'].fillna("").astype(str)

df['最終点検日'] = df['最終点検日'].fillna("").astype(str)
df['費用'] = pd.to_numeric(df['費用'], errors='coerce').fillna(0).astype(int)
df['dt_temp'] = pd.to_datetime(df['最終点検日'], errors='coerce')

# --- 5. 在庫データ整形 ---
stock_df = stock_df_raw.copy()
s_cols = ['分類', '部品名', '在庫数', '単価', '発注点', '最終更新日']
for col in s_cols:
    if col not in stock_df.columns: stock_df[col] = ""
stock_df['在庫数'] = pd.to_numeric(stock_df['在庫数'], errors='coerce').fillna(0).astype(int)

def image_to_base64(uploaded_file):
    if uploaded_file:
        img = Image.open(uploaded_file)
        img.thumbnail((400, 400))
        if img.mode != 'RGB': img = img.convert('RGB')
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=60, optimize=True)
        return base64.b64encode(buf.getvalue()).decode()
    return ""

# --- 6. メニュー ---
tab_titles = ["📊 ダッシュボード", "📁 過去履歴"]
if st.session_state["logged_in"]:
    tab_titles += ["📦 在庫管理", "📝 メンテナンス登録"]

selected_tab = st.radio("メニュー", tab_titles, horizontal=True, label_visibility="collapsed")
categories = ["ジョークラッシャ", "インパクトクラッシャー", "スクリーン", "ベルト", "その他"]

# ================================================================
# 📊 0. ダッシュボード
# ================================================================
if selected_tab == "📊 ダッシュボード":
    st.header("📊 メンテナンス集計分析")
    valid_df = df.dropna(subset=['dt_temp']).copy()
    if not valid_df.empty:
        st.subheader("📅 集計期間指定")
        col_d1, col_d2 = st.columns(2)
        start_date = col_d1.date_input("開始日", valid_df['dt_temp'].min().date())
        end_date = col_d2.date_input("終了日", valid_df['dt_temp'].max().date())
        mask = (valid_df['dt_temp'].dt.date >= start_date) & (valid_df['dt_temp'].dt.date <= end_date)
        f_df = valid_df.loc[mask].copy()
        if not f_df.empty:
            f_df['年月'] = f_df['dt_temp'].dt.strftime('%Y-%m')
            st.metric("期間内 合計費用", f"{int(f_df['費用'].sum()):,} 円")
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("💰 月別費用")
                st.bar_chart(f_df.groupby('年月')['費用'].sum())
            with c2:
                st.subheader("📈 設備別回数（折れ線）")
                st.line_chart(f_df['設備名'].value_counts().sort_index())
    else:
        st.info("データがありません。")

# ================================================================
# 📁 1. 過去履歴（TypeError対策済み）
# ================================================================
elif selected_tab == "📁 過去履歴":
    st.header("📁 履歴表示（新しい順）")
    if not df.empty:
        display_df = df.sort_values(by="dt_temp", ascending=False)
        for i, row in display_df.iterrows():
            d_label = row['最終点検日'] if row['最終点検日'] != "" else "日付未設定"
            with st.expander(f"{d_label} | {row['設備名']}"):
                v1, v2 = st.columns([2, 1])
                v1.write(f"**内容:** {row['作業内容']}\n**費用:** {row['費用']:,} 円\n**備考:** {row['備考']}")
                with v2:
                    # 安全な画像表示ロジック：型を確認してから len() を使う
                    img1 = row['画像']
                    img2 = row['画像2']
                    if isinstance(img1, str) and len(img1) > 20:
                        st.image(base64.b64decode(img1), caption="修理前")
                    if isinstance(img2, str) and len(img2) > 20:
                        st.image(base64.b64decode(img2), caption="修理後")
        
        if st.session_state["logged_in"]:
            st.markdown("---")
            st.subheader("🛠️ 履歴の修正・削除")
            df_sel = display_df.copy()
            df_sel['label'] = df_sel['最終点検日'] + " | " + df_sel['設備名']
            target = st.selectbox("対象を選択", df_sel['label'].tolist())
            idx = df_sel[df_sel['label'] == target].index[0]
            
            with st.form("edit_form"):
                dt_val = df.loc[idx, 'dt_temp']
                u_date = st.date_input("作業日", dt_val.date() if pd.notnull(dt_val) else date.today())
                u_equip = st.text_input("設備名", df.loc[idx, '設備名'])
                u_cost = st.number_input("費用", value=int(df.loc[idx, '費用']))
                u_desc = st.text_area("内容", df.loc[idx, '作業内容'])
                if st.form_submit_button("修正を保存"):
                    st.cache_data.clear()
                    df.loc[idx, '最終点検日'] = u_date.strftime('%Y-%m-%d')
                    df.loc[idx, ['設備名', '作業内容', '費用']] = [u_equip, u_desc, u_cost]
                    conn.update(worksheet="maintenance_data", data=df[m_cols])
                    st.success("更新しました"); time.sleep(1); st.rerun()

# ================================================================
# 📦 2. 在庫管理（省略なし完全版）
# ================================================================
elif selected_tab == "📦 在庫管理" and st.session_state["logged_in"]:
    st.header("📦 在庫管理")
    st.dataframe(stock_df, use_container_width=True)
    c1, c2 = st.columns(2)
    with c1.expander("🛠️ 在庫修正"):
        sel_p = st.selectbox("部品名", stock_df['部品名'].tolist())
        s_idx = stock_df[stock_df['部品名'] == sel_p].index[0]
        with st.form("s_edit"):
            sq = st.number_input("在庫数", value=int(stock_df.loc[s_idx, '在庫数']))
            if st.form_submit_button("更新"):
                st.cache_data.clear()
                stock_df.loc[s_idx, '在庫数'] = sq
                stock_df.loc[s_idx, '最終更新日'] = date.today().strftime('%Y-%m-%d')
                conn.update(worksheet="stock_data", data=stock_df)
                st.rerun()
    with c2.expander("➕ 新規登録"):
        with st.form("s_new"):
            nc, nn = st.selectbox("分類", categories), st.text_input("部品名")
            if st.form_submit_button("登録"):
                st.cache_data.clear()
                new_s = pd.DataFrame([{"分類": nc, "部品名": nn, "在庫数": 0, "単価": 0, "発注点": 5, "最終更新日": date.today().strftime('%Y-%m-%d')}])
                conn.update(worksheet="stock_data", data=pd.concat([stock_df_raw, new_s], ignore_index=True))
                st.rerun()

# ================================================================
# 📝 3. メンテナンス登録
# ================================================================
elif selected_tab == "📝 メンテナンス登録" and st.session_state["logged_in"]:
    st.header("📝 記録入力")
    with st.form("reg_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        f_cat = c1.selectbox("分類", categories)
        f_name = c1.text_input("機番・名称")
        f_date = c2.date_input("作業日", date.today())
        f_cost = c2.number_input("費用", 0)
        f_desc = st.text_area("作業内容")
        up1, up2 = st.file_uploader("前写真", type=['jpg','png']), st.file_uploader("後写真", type=['jpg','png'])
        
        if st.form_submit_button("保存"):
            st.cache_data.clear()
            new_entry = pd.DataFrame([{
                "設備名": f"[{f_cat}] {f_name}",
                "最終点検日": f_date.strftime('%Y-%m-%d'),
                "作業内容": f_desc, "費用": f_cost, "備考": "",
                "画像": image_to_base64(up1), "画像2": image_to_base64(up2)
            }])
            res_df = pd.concat([df_raw, new_entry], ignore_index=True)
            res_df['t'] = pd.to_datetime(res_df['最終点検日'], errors='coerce')
            final_df = res_df.sort_values(by='t', ascending=False).drop(columns=['t'])
            conn.update(worksheet="maintenance_data", data=final_df)
            st.success("登録完了！"); time.sleep(1); st.rerun()
