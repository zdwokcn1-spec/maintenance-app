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
import extra_streamlit_components as stx  # クッキー管理用

# --- 1. ページ設定 ---
st.set_page_config(page_title="設備メンテナンス管理システム", layout="wide")

# --- 2. ログイン状態管理 (Cookie) ---
@st.cache_resource
def get_cookie_manager():
    return stx.CookieManager()

cookie_manager = get_cookie_manager()

def check_password():
    # クッキーからログイン済みフラグを確認
    if cookie_manager.get("is_logged_in") == "true":
        return True

    def password_entered():
        if (
            st.session_state["username"] == st.secrets["auth"]["username"]
            and st.session_state["password"] == st.secrets["auth"]["password"]
        ):
            # ログイン成功時、クッキーに保存 (30日間有効)
            cookie_manager.set("is_logged_in", "true", expires_at=datetime.now() + pd.Timedelta(days=30))
            st.session_state["password_correct"] = True
            del st.session_state["password"]
            del st.session_state["username"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state or not st.session_state["password_correct"]:
        st.title("🔐 設備管理システム ログイン")
        st.text_input("ユーザー名", key="username")
        st.text_input("パスワード", type="password", key="password")
        st.button("ログイン", on_click=password_entered)
        if st.session_state.get("password_correct") == False:
            st.error("😕 ユーザー名またはパスワードが違います")
        return False
    return True

# ログインチェック実行
if not check_password():
    st.stop()

# --- 3. セッション管理 & ログアウト ---
if "active_tab" not in st.session_state:
    st.session_state.active_tab = "📁 過去履歴"

# ログアウトボタン (サイドバー)
if st.sidebar.button("ログアウト"):
    cookie_manager.delete("is_logged_in")  # クッキー削除
    st.session_state["password_correct"] = False
    st.rerun()

# --- 4. データ読み込み ---
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    try:
        df = conn.read(worksheet="maintenance_data", ttl="1s")
        stock = conn.read(worksheet="stock_data", ttl="1s")
        return df, stock
    except Exception as e:
        st.error("Google Sheetsへのアクセス制限中です。少し待ってから更新してください。")
        st.stop()

df_raw, stock_df_raw = load_data()

# --- 5. 列名修復 & クリーニング ---
def fix_columns(df, target_cols):
    if df is None or df.empty: return pd.DataFrame(columns=target_cols)
    for col in target_cols:
        if col not in df.columns: df[col] = ""
    return df[target_cols]

m_cols = ['設備名', '最終点検日', '作業内容', '費用', '備考', '画像', '画像2']
df = fix_columns(df_raw, m_cols)
s_cols = ['分類', '部品名', '在庫数', '単価', '発注点', '最終更新日']
stock_df = fix_columns(stock_df_raw, s_cols)

for col in ['画像', '画像2']:
    df[col] = df[col].fillna("").astype(str)
df['最終点検日'] = pd.to_datetime(df['最終点検日'], errors='coerce').fillna(pd.Timestamp(datetime.today()))
df['費用'] = pd.to_numeric(df['費用'], errors='coerce').fillna(0).astype(int)
stock_df['在庫数'] = pd.to_numeric(stock_df['在庫数'], errors='coerce').fillna(0).astype(int)
stock_df['単価'] = pd.to_numeric(stock_df['単価'], errors='coerce').fillna(0).astype(int)

# --- 6. 共通関数 (画像圧縮) ---
def image_to_base64(uploaded_file):
    if uploaded_file:
        img = Image.open(uploaded_file)
        img.thumbnail((400, 400))
        if img.mode != 'RGB': img = img.convert('RGB')
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=60, optimize=True)
        return base64.b64encode(buf.getvalue()).decode()
    return None

# --- 7. メニュー選択 ---
tab_titles = ["📊 ダッシュボード", "📁 過去履歴", "📦 在庫管理", "📝 メンテナンス登録"]
selected_tab = st.radio("メニュー", tab_titles, horizontal=True, label_visibility="collapsed", 
                        index=tab_titles.index(st.session_state.active_tab))
st.session_state.active_tab = selected_tab

categories = ["ジョークラッシャ", "インパクトクラッシャー", "スクリーン", "ベルト", "その他"]

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
        with c2:
            st.subheader("📈 月別費用推移")
            df_trend = df.copy()
            df_trend['年月'] = df_trend['最終点検日'].dt.strftime('%Y-%m')
            pivot_df = df_trend.pivot_table(index='年月', columns='大分類', values='費用', aggfunc='sum').fillna(0)
            fig2, ax2 = plt.subplots(); pivot_df.plot(kind='line', marker='o', ax=ax2); st.pyplot(fig2)

# ================================================================
# 📁 1. 過去履歴 (画像2枚対応・修正・削除)
# ================================================================
elif st.session_state.active_tab == "📁 過去履歴":
    st.header("📁 メンテナンス過去履歴")
    if not df.empty:
        sorted_df = df.sort_values(by="最終点検日", ascending=False)
        for i, row in sorted_df.iterrows():
            with st.expander(f"{row['最終点検日'].strftime('%Y-%m-%d')} | {row['設備名']}"):
                col_v1, col_v2 = st.columns([2, 1])
                with col_v1:
                    st.write(f"**内容:** {row['作業内容']}\n**備考:** {row['備考']}\n**費用:** {row['費用']:,} 円")
                with col_v2:
                    c_img1, c_img2 = st.columns(2)
                    if len(str(row['画像'])) > 20: c_img1.image(base64.b64decode(row['画像']), caption="修理前", use_container_width=True)
                    if len(str(row['画像2'])) > 20: c_img2.image(base64.b64decode(row['画像2']), caption="完成後", use_container_width=True)
        
        st.markdown("---")
        st.subheader("🛠️ 履歴の修正・削除")
        df['label'] = df['最終点検日'].dt.strftime('%Y-%m-%d') + " | " + df['設備名'].astype(str)
        target_h = st.selectbox("修正対象を選択", df['label'].tolist(), key="h_fix_sel")
        idx_h = df[df['label'] == target_h].index[0]
        curr_h = df.iloc[idx_h]
        
        with st.form("edit_h_form"):
            ca, cb = st.columns(2)
            new_date = ca.date_input("作業日", curr_h["最終点検日"])
            new_equip = ca.text_input("設備名", curr_h["設備名"])
            new_cost = ca.number_input("費用", value=int(curr_h["費用"]))
            new_note = cb.text_area("備考", curr_h["備考"])
            new_desc = st.text_area("作業内容", curr_h["作業内容"])
            f_col1, f_col2 = st.columns(2)
            up_f1 = f_col1.file_uploader("修理前を変更", type=['jpg','jpeg','png'])
            up_f2 = f_col2.file_uploader("完成後を変更", type=['jpg','jpeg','png'])
            if st.form_submit_button("修正内容を保存"):
                img_b1, img_b2 = image_to_base64(up_f1), image_to_base64(up_f2)
                if img_b1: df.loc[idx_h, "画像"] = img_b1
                if img_b2: df.loc[idx_h, "画像2"] = img_b2
                df.loc[idx_h, ["最終点検日", "設備名", "作業内容", "備考", "費用"]] = [pd.to_datetime(new_date), new_equip, new_desc, new_note, new_cost]
                conn.update(worksheet="maintenance_data", data=df.drop(columns=['label'], errors='ignore'))
                time.sleep(1); st.rerun()

        if st.button("🚨 この履歴を完全に削除する", key="h_del_btn"):
            conn.update(worksheet="maintenance_data", data=df.drop(idx_h).drop(columns=['label'], errors='ignore'))
            time.sleep(1); st.rerun()

# ================================================================
# 📦 2. 在庫管理 (新規登録・修正・削除)
# ================================================================
elif st.session_state.active_tab == "📦 在庫管理":
    st.header("📦 部品在庫管理")
    v_cat = st.selectbox("表示フィルタ", ["すべて"] + categories, key="stk_view_filter")
    d_stock = stock_df.copy()
    if v_cat != "すべて": d_stock = d_stock[d_stock["分類"] == v_cat]
    st.dataframe(d_stock, use_container_width=True)

    with st.expander("➕ 新しい部品を登録する"):
        with st.form("new_stock_reg_form"):
            col_n1, col_n2 = st.columns(2)
            n_cat = col_n1.selectbox("分類", categories, key="n_cat")
            n_name = col_n1.text_input("部品名")
            n_qty = col_n2.number_input("初期在庫数", min_value=0)
            n_price = col_n2.number_input("単価", min_value=0)
            if st.form_submit_button("新しい部品を登録"):
                new_row = pd.DataFrame([{"分類": n_cat, "部品名": n_name, "在庫数": n_qty, "単価": n_price, "発注点": 5, "最終更新日": datetime.now().strftime('%Y-%m-%d')}])
                conn.update(worksheet="stock_data", data=pd.concat([stock_df, new_row], ignore_index=True))
                time.sleep(1); st.rerun()

    st.markdown("---")
    st.subheader("🛠️ 在庫の修正・削除")
    s_cat_sel = st.selectbox("分類選択", categories, key="stk_fix_cat")
    f_items = stock_df[stock_df["分類"] == s_cat_sel]
    if not f_items.empty:
        t_item = st.selectbox("部品を選択", f_items["部品名"].tolist(), key="stk_fix_item")
        s_idx = stock_df[stock_df["部品名"] == t_item].index[0]
        s_row = stock_df.loc[s_idx]
        with st.form("edit_stk_form"):
            c1, c2 = st.columns(2)
            eq = c1.number_input("在庫数", value=int(s_row["在庫数"]))
            ep = c2.number_input("単価", value=int(s_row["単価"]))
            if st.form_submit_button("在庫情報を更新"):
                stock_df.loc[s_idx, ["在庫数", "単価", "最終更新日"]] = [eq, ep, datetime.now().strftime('%Y-%m-%d')]
                conn.update(worksheet="stock_data", data=stock_df)
                time.sleep(1); st.rerun()
        if st.button(f"🗑️ {t_item} を削除", key="stk_del_btn"):
            conn.update(worksheet="stock_data", data=stock_df[stock_df["部品名"] != t_item])
            time.sleep(1); st.rerun()

# ================================================================
# 📝 3. メンテナンス登録 (画像2枚対応)
# ================================================================
elif st.session_state.active_tab == "📝 メンテナンス登録":
    st.header("📝 メンテナンス記録の入力")
    with st.form("main_reg_form", clear_on_submit=True):
        col_r1, col_r2 = st.columns(2)
        en = col_r1.selectbox("設備分類", categories, key="reg_cat_sel")
        ed = col_r1.text_input("機番・名称")
        wt = col_r2.date_input("作業日", datetime.today())
        wc = col_r2.number_input("費用", min_value=0)
        wd, wn = st.text_area("作業内容"), st.text_area("備考")
        st.write("📸 写真の追加")
        u_col1, u_col2 = st.columns(2)
        up1 = u_col1.file_uploader("修理前", type=['jpg','jpeg','png'], key="reg_up1")
        up2 = u_col2.file_uploader("完成後", type=['jpg','jpeg','png'], key="reg_up2")
        if st.form_submit_button("メンテナンス記録を保存"):
            img_b1, img_b2 = image_to_base64(up1), image_to_base64(up2)
            new_rec = pd.DataFrame([{"設備名": f"[{en}] {ed}", "最終点検日": wt.strftime('%Y-%m-%d'), "作業内容": wd, "費用": wc, "備考": wn, "画像": img_b1 or "", "画像2": img_b2 or ""}])
            conn.update(worksheet="maintenance_data", data=pd.concat([df.drop(columns=['label'], errors='ignore'), new_rec], ignore_index=True))
            time.sleep(1); st.rerun()
