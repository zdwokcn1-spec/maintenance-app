import streamlit as st
import pandas as pd
from datetime import datetime, date
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator, FuncFormatter
import japanize_matplotlib
from streamlit_gsheets import GSheetsConnection
import base64
from PIL import Image
import io
import time

# --- 1. ページ設定 ---
st.set_page_config(page_title="設備メンテナンス管理システム", layout="wide")

# --- 2. 権限管理システム ---
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if st.query_params.get("auth") == "success":
    st.session_state["logged_in"] = True

with st.sidebar:
    st.title("🔑 権限管理")
    if not st.session_state["logged_in"]:
        user = st.text_input("ユーザー名")
        pw = st.text_input("パスワード", type="password")
        if st.button("編集モードでログイン"):
            is_u1 = (user == st.secrets["auth"]["username"] and pw == st.secrets["auth"]["password"])
            is_u2 = (user == st.secrets["auth_extra"]["username"] and pw == st.secrets["auth_extra"]["password"])
            is_u3 = (user == st.secrets["auth_3"]["username"] and pw == st.secrets["auth_3"]["password"])
            if is_u1 or is_u2 or is_u3:
                st.session_state["logged_in"] = True
                st.query_params["auth"] = "success"
                st.rerun()
            else:
                st.error("認証失敗")
    else:
        st.success("✅ 編集モード：有効")
        if st.button("ログアウト"):
            st.session_state["logged_in"] = False
            st.query_params.clear()
            st.rerun()

# --- 3. データ読み込み ---
conn = st.connection("gsheets", type=GSheetsConnection)
def load_data():
    try:
        df_raw = conn.read(worksheet="maintenance_data", ttl="1s")
        stock_raw = conn.read(worksheet="stock_data", ttl="1s")
        if df_raw is not None and not df_raw.empty:
            df_raw['最終点検日'] = pd.to_datetime(df_raw['最終点検日'], errors='coerce')
        return df_raw, stock_raw
    except:
        st.error("データ読み込み失敗。")
        st.stop()

df, stock_df = load_data()

# --- 4. クリーニング ---
def fix_columns(target_df, target_cols):
    if target_df is None or target_df.empty: return pd.DataFrame(columns=target_cols)
    for col in target_cols:
        if col not in target_df.columns: target_df[col] = ""
    return target_df[target_cols]

m_cols = ['設備名', '最終点検日', '作業内容', '費用', '備考', '画像', '画像2']
df = fix_columns(df, m_cols)
s_cols = ['分類', '部品名', '在庫数', '単価', '発注点', '最終更新日']
stock_df = fix_columns(stock_df, s_cols)

def image_to_base64(uploaded_file):
    if uploaded_file:
        img = Image.open(uploaded_file)
        img.thumbnail((400, 400))
        if img.mode != 'RGB': img = img.convert('RGB')
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=60, optimize=True)
        return base64.b64encode(buf.getvalue()).decode()
    return None

# --- 5. メニュー ---
tab_titles = ["📊 ダッシュボード", "📁 過去履歴"]
if st.session_state["logged_in"]:
    tab_titles += ["📦 在庫管理", "📝 メンテナンス登録"]

if "active_tab" not in st.session_state or st.session_state.active_tab not in tab_titles:
    st.session_state.active_tab = tab_titles[0]

def on_tab_change():
    st.session_state.active_tab = st.session_state.menu_radio

selected_tab = st.radio("メニュー", tab_titles, horizontal=True, label_visibility="collapsed", key="menu_radio", index=tab_titles.index(st.session_state.active_tab), on_change=on_tab_change)
categories = ["ジョークラッシャ", "インパクトクラッシャー", "スクリーン", "ベルト", "その他"]

# --- 📊 0. ダッシュボード (中略 - 変更なし) ---
if st.session_state.active_tab == "📊 ダッシュボード":
    st.header("📊 メンテナンス集計分析")
    if not df.empty:
        valid_dates = df['最終点検日'].dropna()
        default_start = valid_dates.min().date() if not valid_dates.empty else date.today()
        default_end = valid_dates.max().date() if not valid_dates.empty else date.today()
        col_d1, col_d2 = st.columns(2)
        start_date = col_d1.date_input("開始日", default_start)
        end_date = col_d2.date_input("終了日", default_end)
        mask = (df['最終点検日'].dt.date >= start_date) & (df['最終点検日'].dt.date <= end_date)
        f_df = df.loc[mask].copy()
        if not f_df.empty:
            f_df['大分類'] = f_df['設備名'].str.extract(r'\[(.*?)\]')[0].fillna("その他")
            f_df['年月'] = f_df['最終点検日'].dt.strftime('%Y-%m')
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("💰 月別費用")
                m_cost = f_df.groupby('年月')['費用'].sum().sort_index()
                fig1, ax1 = plt.subplots(); m_cost.plot(kind='bar', ax=ax1, color='#3498db', zorder=3)
                ax1.yaxis.set_major_formatter(FuncFormatter(lambda x, p: format(int(x), ',')))
                st.pyplot(fig1)
            with c2:
                st.subheader("📈 設備別回数")
                e_counts = f_df['大分類'].value_counts().sort_index()
                fig2, ax2 = plt.subplots(); ax2.plot(e_counts.index, e_counts.values, marker='o', color='#e67e22', zorder=3)
                ax2.yaxis.set_major_locator(MultipleLocator(1))
                ax2.yaxis.set_major_formatter(FuncFormatter(lambda x, p: f'{int(x)}回'))
                st.pyplot(fig2)
            st.metric("合計費用", f"{int(f_df['費用'].sum()):,} 円")

# --- 📁 1. 過去履歴 (中略 - 変更なし) ---
elif st.session_state.active_tab == "📁 過去履歴":
    st.header("📁 履歴表示・編集・削除")
    if not df.empty:
        s_df = df.sort_values(by="最終点検日", ascending=False)
        for i, row in s_df.iterrows():
            d_str = row['最終点検日'].strftime('%Y-%m-%d') if pd.notnull(row['最終点検日']) else "日付不明"
            with st.expander(f"{d_str} | {row['設備名']}"):
                st.write(f"**内容:** {row['作業内容']} / **費用:** {row['費用']:,}円")
        if st.session_state["logged_in"]:
            st.markdown("---")
            st.subheader("🛠️ 履歴の修正・削除")
            labels = [f"{idx}: {(r['最終点検日'].strftime('%Y-%m-%d') if pd.notnull(r['最終点検日']) else '不明')} | {r['設備名']}" for idx, r in df.iterrows()]
            target_label = st.selectbox("修正対象を選択", labels)
            t_idx = int(target_label.split(":")[0])
            if st.button("🚨 履歴を削除"):
                df_dropped = df.drop(t_idx)
                df_dropped['最終点検日'] = df_dropped['最終点検日'].dt.strftime('%Y-%m-%d')
                conn.update(worksheet="maintenance_data", data=df_dropped)
                st.rerun()

# --- 📦 2. 在庫管理 (修正・削除機能追加！) ---
elif st.session_state.active_tab == "📦 在庫管理" and st.session_state["logged_in"]:
    st.header("📦 在庫管理")
    
    # 在庫一覧の表示
    st.dataframe(stock_df, use_container_width=True, hide_index=True)
    
    col_add, col_edit = st.columns(2)
    
    with col_add:
        with st.expander("➕ 新規部品の登録"):
            with st.form("new_stock_form"):
                n_cat = st.selectbox("分類", categories)
                n_name = st.text_input("部品名")
                n_qty = st.number_input("初期在庫数", min_value=0, value=0)
                n_prc = st.number_input("単価", min_value=0, value=0)
                if st.form_submit_button("新規登録"):
                    new_s = pd.DataFrame([{"分類": n_cat, "部品名": n_name, "在庫数": n_qty, "単価": n_prc, "発注点": 5, "最終更新日": date.today().strftime('%Y-%m-%d')}])
                    updated_stock = pd.concat([stock_df, new_s], ignore_index=True)
                    conn.update(worksheet="stock_data", data=updated_stock)
                    st.success("登録しました"); time.sleep(1); st.rerun()

    with col_edit:
        with st.expander("🛠️ 在庫数の修正・削除"):
            if not stock_df.empty:
                # 修正対象の選択
                stock_labels = [f"{idx}: {r['部品名']} (現在:{r['在庫数']})" for idx, r in stock_df.iterrows()]
                s_label = st.selectbox("修正する部品を選択", stock_labels)
                s_idx = int(s_label.split(":")[0])
                
                with st.form("edit_stock_form"):
                    u_qty = st.number_input("在庫数変更", value=int(stock_df.loc[s_idx, "在庫数"]))
                    u_prc = st.number_input("単価変更", value=int(stock_df.loc[s_idx, "単価"]))
                    u_lim = st.number_input("発注点変更", value=int(stock_df.loc[s_idx, "発注点"]))
                    
                    col_btn1, col_btn2 = st.columns(2)
                    if col_btn1.form_submit_button("✅ 更新保存"):
                        stock_df.loc[s_idx, ["在庫数", "単価", "発注点", "最終更新日"]] = [u_qty, u_prc, u_lim, date.today().strftime('%Y-%m-%d')]
                        conn.update(worksheet="stock_data", data=stock_df)
                        st.success("在庫を更新しました"); time.sleep(1); st.rerun()
                
                if st.button("🗑️ この部品を削除",用="primary"):
                    new_stock_df = stock_df.drop(s_idx)
                    conn.update(worksheet="stock_data", data=new_stock_df)
                    st.warning("部品を削除しました"); time.sleep(1); st.rerun()
            else:
                st.write("データがありません")

# --- 📝 3. メンテナンス登録 ---
elif st.session_state.active_tab == "📝 メンテナンス登録" and st.session_state["logged_in"]:
    st.header("📝 記録入力")
    with st.form("reg", clear_on_submit=True):
        c1, c2 = st.columns(2)
        en, ed = c1.selectbox("分類", categories), c1.text_input("機番・名称")
        wt, wc = c2.date_input("作業日", date.today()), c2.number_input("費用", 0)
        wd, wn = st.text_area("内容"), st.text_area("備考")
        up1, up2 = st.file_uploader("修理前", type=['jpg','png']), st.file_uploader("修理後", type=['jpg','png'])
        if st.form_submit_button("保存"):
            b1, b2 = image_to_base64(up1), image_to_base64(up2)
            new_r = pd.DataFrame([{"設備名": f"[{en}] {ed}", "最終点検日": wt.strftime('%Y-%m-%d'), "作業内容": wd, "費用": wc, "備考": wn, "画像": b1 or "", "画像2": b2 or ""}])
            df_to_save = df.copy()
            df_to_save['最終点検日'] = df_to_save['最終点検日'].dt.strftime('%Y-%m-%d')
            updated_df = pd.concat([df_to_save, new_r], ignore_index=True)
            conn.update(worksheet="maintenance_data", data=updated_df)
            st.success("完了"); time.sleep(1); st.rerun()
