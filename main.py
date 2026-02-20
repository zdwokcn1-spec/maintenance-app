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
        df = conn.read(worksheet="maintenance_data", ttl="1s")
        stock = conn.read(worksheet="stock_data", ttl="1s")
        return df, stock
    except:
        st.error("データ読み込み失敗。")
        st.stop()

df_raw, stock_df_raw = load_data()

# --- 4. クリーニング ---
def fix_columns(df, target_cols):
    if df is None or df.empty: return pd.DataFrame(columns=target_cols)
    for col in target_cols:
        if col not in df.columns: df[col] = ""
    return df[target_cols]

m_cols = ['設備名', '最終点検日', '作業内容', '費用', '備考', '画像', '画像2']
df = fix_columns(df_raw, m_cols)
s_cols = ['分類', '部品名', '在庫数', '単価', '発注点', '最終更新日']
stock_df = fix_columns(stock_df_raw, s_cols)

for col in ['画像', '画像2']: df[col] = df[col].fillna("").astype(str)
df['最終点検日'] = pd.to_datetime(df['最終点検日'], errors='coerce')
df['費用'] = pd.to_numeric(df['費用'], errors='coerce').fillna(0).astype(int)

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
if st.session_state["logged_in"]:
    tab_titles = ["📊 ダッシュボード", "📁 過去履歴", "📦 在庫管理", "📝 メンテナンス登録"]
else:
    tab_titles = ["📊 ダッシュボード", "📁 過去履歴"]

if "active_tab" not in st.session_state: st.session_state.active_tab = tab_titles[0]
def on_tab_change(): st.session_state.active_tab = st.session_state.menu_radio

selected_tab = st.radio("メニュー", tab_titles, horizontal=True, label_visibility="collapsed", key="menu_radio", index=tab_titles.index(st.session_state.active_tab), on_change=on_tab_change)
categories = ["ジョークラッシャ", "インパクトクラッシャー", "スクリーン", "ベルト", "その他"]

# --- 📊 0. ダッシュボード ---
if st.session_state.active_tab == "📊 ダッシュボード":
    st.header("📊 メンテナンス集計")
    if not df.empty:
        st.subheader("📅 集計期間指定")
        col_d1, col_d2 = st.columns(2)
        start_date = col_d1.date_input("開始日", df['最終点検日'].min().date())
        end_date = col_d2.date_input("終了日", df['最終点検日'].max().date())
        
        mask = (df['最終点検日'].dt.date >= start_date) & (df['最終点検日'].dt.date <= end_date)
        f_df = df.loc[mask].copy()

        if not f_df.empty:
            f_df['大分類'] = f_df['設備名'].str.extract(r'\[(.*?)\]')[0].fillna("その他")
            f_df['年月'] = f_df['最終点検日'].dt.strftime('%Y-%m')
            
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("💰 月別費用 (縦棒)")
                m_cost = f_df.groupby('年月')['費用'].sum().sort_index()
                fig1, ax1 = plt.subplots()
                bars = m_cost.plot(kind='bar', ax=ax1, color='#3498db', zorder=3)
                for bar in bars.patches:
                    ax1.annotate(f'{int(bar.get_height()):,}', 
                                 (bar.get_x() + bar.get_width() / 2, bar.get_height()),
                                 ha='center', va='bottom', fontsize=9)
                ax1.yaxis.set_major_formatter(FuncFormatter(lambda x, p: format(int(x), ',')))
                plt.xticks(rotation=45)
                ax1.grid(axis='y', linestyle='--', alpha=0.7)
                st.pyplot(fig1)

            with c2:
                st.subheader("📈 設備別回数 (折れ線)")
                e_counts = f_df['大分類'].value_counts().sort_index()
                fig2, ax2 = plt.subplots()
                ax2.plot(e_counts.index, e_counts.values, marker='o', color='#e67e22', linewidth=2, zorder=3)
                
                # --- 縦軸の設定：最小値0、単位1、整数のみ ---
                ax2.set_ylim(bottom=0) # 最小値を0に固定
                ax2.yaxis.set_major_locator(MultipleLocator(1)) # 刻み単位を強制的に「1」にする
                ax2.yaxis.set_major_formatter(FuncFormatter(lambda x, p: f'{int(x)}回')) # 整数+「回」
                
                plt.xticks(rotation=45)
                ax2.grid(linestyle='--', alpha=0.7)
                st.pyplot(fig2)
            
            st.markdown("---")
            m1, m2 = st.columns(2)
            m1.metric("期間内合計費用", f"{int(f_df['費用'].sum()):,} 円")
            m2.metric("期間内メンテ回数", f"{len(f_df)} 回")

# --- 📁 1. 過去履歴 ---
elif st.session_state.active_tab == "📁 過去履歴":
    st.header("📁 履歴表示・編集・削除")
    if not df.empty:
        s_df = df.sort_values(by="最終点検日", ascending=False)
        for i, row in s_df.iterrows():
            with st.expander(f"{row['最終点検日'].strftime('%Y-%m-%d')} | {row['設備名']}"):
                v1, v2 = st.columns([2, 1])
                v1.write(f"**内容:** {row['作業内容']}\n**費用:** {row['費用']:,} 円\n**備考:** {row['備考']}")
                with v2:
                    i1, i2 = st.columns(2)
                    if len(str(row['画像'])) > 20: i1.image(base64.b64decode(row['画像']), caption="修理前")
                    if len(str(row['画像2'])) > 20: i2.image(base64.b64decode(row['画像2']), caption="修理後")
        
        if st.session_state["logged_in"]:
            st.markdown("---")
            st.subheader("🛠️ 履歴の修正・削除")
            df['label'] = df['最終点検日'].dt.strftime('%Y-%m-%d') + " | " + df['設備名'].astype(str)
            target = st.selectbox("修正対象を選択", df['label'].tolist())
            idx = df[df['label'] == target].index[0]
            with st.form("edit_h"):
                c1, c2 = st.columns(2)
                u_date = c1.date_input("作業日", df.loc[idx, "最終点検日"])
                u_equip = c1.text_input("設備名", df.loc[idx, "設備名"])
                u_cost = c1.number_input("費用", value=int(df.loc[idx, "費用"]))
                u_desc = st.text_area("内容", df.loc[idx, "作業内容"])
                u_note = st.text_area("備考", df.loc[idx, "備考"])
                if st.form_submit_button("修正を保存"):
                    df.loc[idx, ["最終点検日", "設備名", "作業内容", "備考", "費用"]] = [pd.to_datetime(u_date), u_equip, u_desc, u_note, u_cost]
                    conn.update(worksheet="maintenance_data", data=df.drop(columns=['label']))
                    st.success("更新完了"); time.sleep(1); st.rerun()
            if st.button("🚨 この履歴を削除"):
                conn.update(worksheet="maintenance_data", data=df.drop(idx).drop(columns=['label']))
                st.warning("削除完了"); time.sleep(1); st.rerun()

# --- 📦 2. 在庫管理 ---
elif st.session_state.active_tab == "📦 在庫管理" and st.session_state["logged_in"]:
    st.header("📦 在庫管理・修正・削除")
    st.dataframe(stock_df, use_container_width=True)
    with st.expander("➕ 新規登録"):
        with st.form("n_s"):
            nc, nn = st.selectbox("分類", categories), st.text_input("部品名")
            nq, np = st.number_input("在庫", 0), st.number_input("単価", 0)
            if st.form_submit_button("登録"):
                new_s = pd.DataFrame([{"分類": nc, "部品名": nn, "在庫数": nq, "単価": np, "発注点": 5, "最終更新日": date.today().strftime('%Y-%m-%d')}])
                conn.update(worksheet="stock_data", data=pd.concat([stock_df, new_s], ignore_index=True))
                st.success("登録完了"); time.sleep(1); st.rerun()
    st.markdown("---")
    st.subheader("🛠️ 在庫の修正・削除")
    if not stock_df.empty:
        target_s = st.selectbox("部品を選択", stock_df["部品名"].tolist())
        s_idx = stock_df[stock_df["部品名"] == target_s].index[0]
        with st.form("e_s"):
            u_q = st.number_input("在庫数", value=int(stock_df.loc[s_idx, "在庫数"]))
            u_p = st.number_input("単価", value=int(stock_df.loc[s_idx, "単価"]))
            if st.form_submit_button("在庫更新"):
                stock_df.loc[s_idx, ["在庫数", "単価", "最終更新日"]] = [u_q, u_p, date.today().strftime('%Y-%m-%d')]
                conn.update(worksheet="stock_data", data=stock_df)
                st.success("更新完了"); time.sleep(1); st.rerun()
        if st.button(f"🗑️ {target_s} を削除"):
            conn.update(worksheet="stock_data", data=stock_df[stock_df["部品名"] != target_s])
            st.warning("削除完了"); time.sleep(1); st.rerun()

# --- 📝 3. 登録 ---
elif st.session_state.active_tab == "📝 メンテナンス登録" and st.session_state["logged_in"]:
    st.header("📝 記録入力")
    with st.form("reg", clear_on_submit=True):
        c1, c2 = st.columns(2)
        en, ed = c1.selectbox("分類", categories), c1.text_input("名称")
        wt, wc = c2.date_input("作業日", date.today()), c2.number_input("費用", 0)
        wd, wn = st.text_area("内容"), st.text_area("備考")
        up1, up2 = st.file_uploader("修理前写真", type=['jpg','png']), st.file_uploader("修理後写真", type=['jpg','png'])
        if st.form_submit_button("保存"):
            b1, b2 = image_to_base64(up1), image_to_base64(up2)
            new_r = pd.DataFrame([{"設備名": f"[{en}] {ed}", "最終点検日": wt.strftime('%Y-%m-%d'), "作業内容": wd, "費用": wc, "備考": wn, "画像": b1 or "", "画像2": b2 or ""}])
            updated_df = pd.concat([df_raw, new_r], ignore_index=True)
            conn.update(worksheet="maintenance_data", data=updated_df)
            st.success("完了"); time.sleep(1); st.rerun()
