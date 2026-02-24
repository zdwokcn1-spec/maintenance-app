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

# --- 3. データ読み込み（TTL=0で即時反映） ---
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    df = conn.read(worksheet="maintenance_data", ttl=0)
    stock = conn.read(worksheet="stock_data", ttl=0)
    return df, stock

df_raw, stock_df_raw = load_data()

# --- 4. メンテナンスデータ整形 ---
m_cols = ['設備名', '最終点検日', '作業内容', '費用', '備考', '画像', '画像2']
df = df_raw.copy()
for col in m_cols:
    if col not in df.columns: df[col] = ""

df['画像'] = df['画像'].fillna("").astype(str)
df['画像2'] = df['画像2'].fillna("").astype(str)
df['最終点検日'] = df['最終点検日'].fillna("").astype(str)
df['費用'] = pd.to_numeric(df['費用'], errors='coerce').fillna(0).astype(int)
df['dt_temp'] = pd.to_datetime(df['最終点検日'], errors='coerce')

# --- 5. 在庫データ整形 ---
s_cols = ['分類', '部品名', '在庫数', '単価', '発注点', '最終更新日']
stock_df = stock_df_raw.copy()
for col in s_cols:
    if col not in stock_df.columns: stock_df[col] = ""

stock_df['在庫数'] = pd.to_numeric(stock_df['在庫数'], errors='coerce').fillna(0).astype(int)
stock_df['単価'] = pd.to_numeric(stock_df['単価'], errors='coerce').fillna(0).astype(int)
stock_df['発注点'] = pd.to_numeric(stock_df['発注点'], errors='coerce').fillna(5).astype(int)

# 共通関数：画像変換
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
# 📊 0. ダッシュボード（期間指定フィルター ＆ 折れ線グラフ）
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
                st.subheader("💰 月別費用（棒グラフ）")
                st.bar_chart(f_df.groupby('年月')['費用'].sum())
            with c2:
                st.subheader("📈 設備別回数（折れ線グラフ）")
                st.line_chart(f_df['設備名'].value_counts().sort_index())
        else:
            st.warning("該当日付のデータがありません。")
    else:
        st.info("データがありません。登録を行ってください。")

# ================================================================
# 📁 1. 過去履歴（新しい順表示 ＆ 修正・削除）
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
                    if len(row['画像']) > 20: st.image(base64.b64decode(row['画像']), caption="修理前")
                    if len(row['画像2']) > 20: st.image(base64.b64decode(row['画像2']), caption="修理後")
        
        if st.session_state["logged_in"]:
            st.markdown("---")
            st.subheader("🛠️ 履歴の修正・削除")
            df_sel = display_df.copy()
            df_sel['label'] = df_sel['最終点検日'] + " | " + df_sel['設備名']
            target = st.selectbox("対象を選択", df_sel['label'].tolist())
            idx = df_sel[df_sel['label'] == target].index[0]
            
            with st.form("edit_history"):
                raw_dt = df.loc[idx, 'dt_temp']
                u_date = st.date_input("作業日", raw_dt.date() if pd.notnull(raw_dt) else date.today())
                u_equip = st.text_input("設備名", df.loc[idx, '設備名'])
                u_cost = st.number_input("費用", value=int(df.loc[idx, '費用']))
                u_desc = st.text_area("内容", df.loc[idx, '作業内容'])
                u_note = st.text_area("備考", df.loc[idx, '備考'])
                if st.form_submit_button("修正を保存"):
                    df.loc[idx, '最終点検日'] = u_date.strftime('%Y-%m-%d')
                    df.loc[idx, ['設備名', '作業内容', '備考', '費用']] = [u_equip, u_desc, u_note, u_cost]
                    save_df = df[m_cols].copy()
                    save_df['t'] = pd.to_datetime(save_df['最終点検日'], errors='coerce')
                    save_df = save_df.sort_values(by='t', ascending=False).drop(columns=['t'])
                    conn.update(worksheet="maintenance_data", data=save_df)
                    st.success("更新しました"); time.sleep(1); st.rerun()
            
            if st.button("🚨 この履歴を完全に削除"):
                conn.update(worksheet="maintenance_data", data=df.drop(idx)[m_cols])
                st.warning("削除しました"); time.sleep(1); st.rerun()

# ================================================================
# 📦 2. 在庫管理（省略なし完全実装）
# ================================================================
elif selected_tab == "📦 在庫管理" and st.session_state["logged_in"]:
    st.header("📦 在庫管理")
    
    # アラート表示
    low_stock = stock_df[stock_df['在庫数'] <= stock_df['発注点']]
    if not low_stock.empty:
        for _, r in low_stock.iterrows():
            st.error(f"⚠️ 発注警告: {r['部品名']} (残り: {r['在庫数']})")

    st.dataframe(stock_df, use_container_width=True)
    
    col_s1, col_s2 = st.columns(2)
    with col_s1.expander("🛠️ 在庫修正・削除"):
        if not stock_df.empty:
            sel_p = st.selectbox("修正する部品", stock_df['部品名'].tolist())
            s_idx = stock_df[stock_df['部品名'] == sel_p].index[0]
            with st.form("stock_edit"):
                u_qty = st.number_input("在庫数", value=int(stock_df.loc[s_idx, '在庫数']))
                u_prc = st.number_input("単価", value=int(stock_df.loc[s_idx, '単価']))
                u_alt = st.number_input("発注点", value=int(stock_df.loc[s_idx, '発注点']))
                if st.form_submit_button("在庫データを更新"):
                    stock_df.loc[s_idx, ['在庫数', '単価', '発注点', '最終更新日']] = [u_qty, u_prc, u_alt, date.today().strftime('%Y-%m-%d')]
                    conn.update(worksheet="stock_data", data=stock_df)
                    st.success("更新完了"); time.sleep(1); st.rerun()
            if st.button("🗑️ この部品を名簿から削除"):
                conn.update(worksheet="stock_data", data=stock_df.drop(s_idx))
                st.rerun()

    with col_s2.expander("➕ 新規部品登録"):
        with st.form("stock_new"):
            n_cat = st.selectbox("分類", categories)
            n_name = st.text_input("新しい部品名")
            n_qty = st.number_input("初期在庫数", 0)
            n_prc = st.number_input("単価", 0)
            if st.form_submit_button("新規登録"):
                if n_name:
                    new_s = pd.DataFrame([{"分類": n_cat, "部品名": n_name, "在庫数": n_qty, "単価": n_prc, "発注点": 5, "最終更新日": date.today().strftime('%Y-%m-%d')}])
                    conn.update(worksheet="stock_data", data=pd.concat([stock_df_raw, new_s], ignore_index=True))
                    st.success("登録しました"); time.sleep(1); st.rerun()

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
        f_desc = st.text_area("内容")
        f_note = st.text_area("備考")
        up1, up2 = st.file_uploader("前写真", type=['jpg','png']), st.file_uploader("後写真", type=['jpg','png'])
        
        if st.form_submit_button("保存"):
            new_entry = pd.DataFrame([{
                "設備名": f"[{f_cat}] {f_name}",
                "最終点検日": f_date.strftime('%Y-%m-%d'),
                "作業内容": f_desc, "費用": f_cost, "備考": f_note,
                "画像": image_to_base64(up1), "画像2": image_to_base64(up2)
            }])
            res_df = pd.concat([df_raw, new_entry], ignore_index=True)
            res_df['t'] = pd.to_datetime(res_df['最終点検日'], errors='coerce')
            final_df = res_df.sort_values(by='t', ascending=False).drop(columns=['t'])
            conn.update(worksheet="maintenance_data", data=final_df)
            st.success("登録完了。ダッシュボードに反映されました。"); time.sleep(1); st.rerun()
