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

# --- 1. ページ設定 ---
st.set_page_config(page_title="設備メンテナンス管理システム", layout="wide")

# --- 2. ログイン機能 (標準セッション管理) ---
def check_password():
    if st.session_state.get("password_correct", False):
        return True

    st.title("🔐 設備管理システム ログイン")
    user = st.text_input("ユーザー名")
    pw = st.text_input("パスワード", type="password")
    
    if st.button("ログイン"):
        if user == st.secrets["auth"]["username"] and pw == st.secrets["auth"]["password"]:
            st.session_state["password_correct"] = True
            st.rerun()
        else:
            st.error("😕 ユーザー名またはパスワードが違います")
    return False

if not check_password():
    st.stop()

# --- 3. ログアウト ---
if st.sidebar.button("ログアウト"):
    st.session_state["password_correct"] = False
    st.rerun()

# --- 4. データ読み込み (API負荷軽減) ---
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    try:
        df = conn.read(worksheet="maintenance_data", ttl="1s")
        stock = conn.read(worksheet="stock_data", ttl="1s")
        return df, stock
    except Exception:
        st.error("アクセス制限中です。30秒待って再読み込みしてください。")
        st.stop()

df_raw, stock_df_raw = load_data()

# --- 5. データ整形 ---
def fix_columns(df, target_cols):
    if df is None or df.empty: return pd.DataFrame(columns=target_cols)
    for col in target_cols:
        if col not in df.columns: df[col] = ""
    return df[target_cols]

df = fix_columns(df_raw, ['設備名', '最終点検日', '作業内容', '費用', '備考', '画像', '画像2'])
stock_df = fix_columns(stock_df_raw, ['分類', '部品名', '在庫数', '単価', '発注点', '最終更新日'])

for col in ['画像', '画像2']: df[col] = df[col].fillna("").astype(str)
df['最終点検日'] = pd.to_datetime(df['最終点検日'], errors='coerce').fillna(pd.Timestamp(datetime.today()))
stock_df['在庫数'] = pd.to_numeric(stock_df['在庫数'], errors='coerce').fillna(0).astype(int)

# --- 6. 共通関数 ---
def image_to_base64(uploaded_file):
    if uploaded_file:
        img = Image.open(uploaded_file)
        img.thumbnail((400, 400))
        if img.mode != 'RGB': img = img.convert('RGB')
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=60)
        return base64.b64encode(buf.getvalue()).decode()
    return None

# --- 7. タブ管理 ---
if "active_tab" not in st.session_state: st.session_state.active_tab = "📁 過去履歴"
tab_titles = ["📊 ダッシュボード", "📁 過去履歴", "📦 在庫管理", "📝 メンテナンス登録"]
selected_tab = st.radio("メニュー", tab_titles, horizontal=True, label_visibility="collapsed", index=tab_titles.index(st.session_state.active_tab))
st.session_state.active_tab = selected_tab
categories = ["ジョークラッシャ", "インパクトクラッシャー", "スクリーン", "ベルト", "その他"]

# ================================================================
# 各機能 (在庫管理の全機能含む)
# ================================================================
if st.session_state.active_tab == "📊 ダッシュボード":
    st.header("📊 状況概況")
    if not df.empty:
        df['大分類'] = df['設備名'].str.extract(r'\[(.*?)\]')[0].fillna("その他")
        c1, c2 = st.columns(2)
        with c1:
            cost_by_equip = df.groupby('大分類')['費用'].sum()
            fig1, ax1 = plt.subplots(); cost_by_equip.plot(kind='barh', ax=ax1); st.pyplot(fig1)
        with c2:
            df_trend = df.copy(); df_trend['年月'] = df_trend['最終点検日'].dt.strftime('%Y-%m')
            pivot_df = df_trend.pivot_table(index='年月', columns='大分類', values='費用', aggfunc='sum').fillna(0)
            fig2, ax2 = plt.subplots(); pivot_df.plot(kind='line', ax=ax2); st.pyplot(fig2)

elif st.session_state.active_tab == "📁 過去履歴":
    st.header("📁 履歴（画像2枚対応）")
    for i, row in df.sort_values(by="最終点検日", ascending=False).iterrows():
        with st.expander(f"{row['最終点検日'].strftime('%Y-%m-%d')} | {row['設備名']}"):
            v1, v2 = st.columns([2, 1])
            v1.write(f"**内容:** {row['作業内容']}\n**費用:** {row['費用']:,}円")
            with v2:
                i1, i2 = st.columns(2)
                if len(row['画像']) > 20: i1.image(base64.b64decode(row['画像']), caption="修理前")
                if len(row['画像2']) > 20: i2.image(base64.b64decode(row['画像2']), caption="完成後")

    st.markdown("---")
    st.subheader("🛠️ 削除")
    df['label'] = df['最終点検日'].dt.strftime('%Y-%m-%d') + " | " + df['設備名']
    target = st.selectbox("削除する履歴を選択", df['label'].tolist())
    if st.button("🚨 選択した履歴を削除"):
        new_df = df[df['label'] != target].drop(columns=['label'])
        conn.update(worksheet="maintenance_data", data=new_df)
        time.sleep(1); st.rerun()

elif st.session_state.active_tab == "📦 在庫管理":
    st.header("📦 部品在庫管理")
    st.dataframe(stock_df, use_container_width=True)
    
    with st.expander("➕ 新規登録"):
        with st.form("new_st"):
            c1, c2 = st.columns(2)
            cat, name = c1.selectbox("分類", categories), c1.text_input("部品名")
            qty, prc = c2.number_input("在庫", 0), c2.number_input("単価", 0)
            if st.form_submit_button("登録"):
                new_r = pd.DataFrame([{"分類": cat, "部品名": name, "在庫数": qty, "単価": prc, "最終更新日": datetime.now().strftime('%Y-%m-%d')}])
                conn.update(worksheet="stock_data", data=pd.concat([stock_df, new_r], ignore_index=True))
                time.sleep(1); st.rerun()

    st.subheader("🛠️ 在庫修正/削除")
    target_st = st.selectbox("部品を選択", stock_df["部品名"].tolist())
    s_idx = stock_df[stock_df["部品名"] == target_st].index[0]
    with st.form("edit_st"):
        new_q = st.number_input("在庫数更新", value=int(stock_df.loc[s_idx, "在庫数"]))
        if st.form_submit_button("更新"):
            stock_df.loc[s_idx, ["在庫数", "最終更新日"]] = [new_q, datetime.now().strftime('%Y-%m-%d')]
            conn.update(worksheet="stock_data", data=stock_df)
            time.sleep(1); st.rerun()
    if st.button(f"🗑️ {target_st} を削除"):
        conn.update(worksheet="stock_data", data=stock_df[stock_df["部品名"] != target_st])
        time.sleep(1); st.rerun()

elif st.session_state.active_tab == "📝 メンテナンス登録":
    st.header("📝 記録入力")
    with st.form("reg"):
        c1, c2 = st.columns(2)
        en, ed = c1.selectbox("設備", categories), c1.text_input("機番")
        wt, wc = c2.date_input("日"), c2.number_input("費用", 0)
        wd, wn = st.text_area("内容"), st.text_area("備考")
        up1, up2 = st.file_uploader("前"), st.file_uploader("後")
        if st.form_submit_button("保存"):
            b1, b2 = image_to_base64(up1), image_to_base64(up2)
            new_rec = pd.DataFrame([{"設備名": f"[{en}] {ed}", "最終点検日": wt.strftime('%Y-%m-%d'), "作業内容": wd, "費用": wc, "備考": wn, "画像": b1 or "", "画像2": b2 or ""}])
            conn.update(worksheet="maintenance_data", data=pd.concat([df.drop(columns=['label'], errors='ignore'), new_rec], ignore_index=True))
            time.sleep(1); st.rerun()
