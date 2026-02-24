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
            if user == st.secrets["auth"]["username"] and pw == st.secrets["auth"]["password"]:
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
        st.error("Google Sheetsへのアクセス制限中です。しばらく待ってから再読み込みしてください。")
        st.stop()

df_raw, stock_df_raw = load_data()

# --- 4. 列名修復 & クリーニング ---
def fix_columns(df, target_cols):
    if df is None or df.empty: return pd.DataFrame(columns=target_cols)
    for col in target_cols:
        if col not in df.columns: df[col] = ""
    return df[target_cols]

m_cols = ['設備名', '最終点検日', '作業内容', '費用', '備考', '画像', '画像2']
df = fix_columns(df_raw, m_cols)
s_cols = ['分類', '部品名', '在庫数', '単価', '発注点', '最終更新日']
stock_df = fix_columns(stock_df_raw, s_cols)

# 型変換の徹底
for col in ['画像', '画像2']: df[col] = df[col].fillna("").astype(str)
df['最終点検日'] = pd.to_datetime(df['最終点検日'], errors='coerce').fillna(pd.Timestamp(datetime.today()))
df['費用'] = pd.to_numeric(df['費用'], errors='coerce').fillna(0).astype(int)
stock_df['在庫数'] = pd.to_numeric(stock_df['在庫数'], errors='coerce').fillna(0).astype(int)
stock_df['単価'] = pd.to_numeric(stock_df['単価'], errors='coerce').fillna(0).astype(int)

# --- 5. 画像圧縮関数 ---
def image_to_base64(uploaded_file):
    if uploaded_file:
        img = Image.open(uploaded_file)
        img.thumbnail((400, 400))
        if img.mode != 'RGB': img = img.convert('RGB')
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=60, optimize=True)
        return base64.b64encode(buf.getvalue()).decode()
    return None

# --- 6. メニュー切り替え ---
if st.session_state["logged_in"]:
    tab_titles = ["📊 ダッシュボード", "📁 過去履歴", "📦 在庫管理", "📝 メンテナンス登録"]
else:
    tab_titles = ["📊 ダッシュボード", "📁 過去履歴"]

if "active_tab" not in st.session_state or st.session_state.active_tab not in tab_titles:
    st.session_state.active_tab = tab_titles[0]

def on_tab_change():
    st.session_state.active_tab = st.session_state.menu_radio

selected_tab = st.radio(
    "メニュー", 
    tab_titles, 
    horizontal=True, 
    label_visibility="collapsed", 
    key="menu_radio",
    index=tab_titles.index(st.session_state.active_tab),
    on_change=on_tab_change
)

categories = ["ジョークラッシャ", "インパクトクラッシャー", "スクリーン", "ベルト", "その他"]

# --- 7. 各画面の表示ロジック ---

# 📊 ダッシュボード
if st.session_state.active_tab == "📊 ダッシュボード":
    st.header("📊 メンテナンス状況概況")
    if not df.empty:
        df['大分類'] = df['設備名'].str.extract(r'\[(.*?)\]')[0].fillna("その他")
        c1, c2 = st.columns(2)
        
        with c1:
            st.subheader("💰 設備別・累計費用")
            cost_by_equip = df.groupby('大分類')['費用'].sum().sort_values(ascending=True)
            fig1, ax1 = plt.subplots()
            cost_by_equip.plot(kind='barh', ax=ax1, color='#2ecc71')
            st.pyplot(fig1)
            
        with c2:
            st.subheader("🔧 設備別・メンテナンス回数")
            
            # 設備（分類）ごとのメンテナンス回数を集計
            count_by_equip = df.groupby('大分類')['設備名'].count()
            
            fig2, ax2 = plt.subplots(figsize=(7, 4))
            
            # 折れ線グラフ（kind='line'）にマーカー（marker='o'）を指定
            count_by_equip.plot(kind='line', marker='o', ax=ax2, linewidth=2, color='#e74c3c')
            
            # グラフを見やすくするための調整
            ax2.yaxis.set_major_locator(plt.MaxNLocator(integer=True)) # Y軸を必ず整数に
            ax2.grid(True, linestyle='--', alpha=0.6) # 背景に薄いグリッド線
            
            ax2.set_ylabel("メンテナンス回数 (回)") # 左側
            ax2.set_xlabel("設備名（分類）") # 下側
            
            # X軸のラベルが重ならないように45度傾ける
            plt.xticks(rotation=45)
            plt.tight_layout() # レイアウトのはみ出しを防止
            
            st.pyplot(fig2)

# 📁 過去履歴
elif st.session_state.active_tab == "📁 過去履歴":
    st.header("📁 メンテナンス過去履歴")
    if not df.empty:
        df['label'] = df['最終点検日'].dt.strftime('%Y-%m-%d') + " | " + df['設備名'].astype(str)
        sorted_df = df.sort_values(by="最終点検日", ascending=False)
        
        for i, row in sorted_df.iterrows():
            with st.expander(f"{row['最終点検日'].strftime('%Y-%m-%d')} | {row['設備名']}"):
                v1, v2 = st.columns([2, 1])
                v1.write(f"**作業内容:** {row['作業内容']}\n\n**備考:** {row['備考']}\n\n**費用:** {row['費用']:,} 円")
                with v2:
                    i1, i2 = st.columns(2)
                    if len(str(row['画像'])) > 20: i1.image(base64.b64decode(row['画像']), caption="修理前")
                    if len(str(row['画像2'])) > 20: i2.image(base64.b64decode(row['画像2']), caption="修理後")
        
        if st.session_state["logged_in"]:
            st.markdown("---")
            st.subheader("🛠️ 履歴の修正・削除")
            target_h = st.selectbox("修正対象を選択（作業日 | 設備名）", df['label'].tolist())
            idx_h = df[df['label'] == target_h].index[0]
            curr_h = df.iloc[idx_h]
            
            with st.form("edit_h_form"):
                ca, cb = st.columns(2)
                new_date = ca.date_input("作業日", curr_h["最終点検日"])
                new_equip = ca.text_input("設備名", curr_h["設備名"])
                new_cost = ca.number_input("費用", value=int(curr_h["費用"]))
                new_note = cb.text_area("備考", curr_h["備考"])
                new_desc = st.text_area("内容", curr_h["作業内容"])
                up_f1 = st.file_uploader("修理前を更新", type=['jpg','png'], key="up_f1")
                up_f2 = st.file_uploader("修理後を更新", type=['jpg','png'], key="up_f2")
                
                if st.form_submit_button("修正を保存"):
                    img_b1, img_b2 = image_to_base64(up_f1), image_to_base64(up_f2)
                    if img_b1: df.loc[idx_h, "画像"] = img_b1
                    if img_b2: df.loc[idx_h, "画像2"] = img_b2
                    df.loc[idx_h, ["最終点検日", "設備名", "作業内容", "備考", "費用"]] = [pd.to_datetime(new_date), new_equip, new_desc, new_note, new_cost]
                    conn.update(worksheet="maintenance_data", data=df.drop(columns=['label'], errors='ignore'))
                    st.success("保存完了"); time.sleep(1); st.rerun()
            
            if st.button("🚨 この履歴を削除"):
                conn.update(worksheet="maintenance_data", data=df.drop(idx_h).drop(columns=['label'], errors='ignore'))
                st.warning("削除完了"); time.sleep(1); st.rerun()

# 📦 在庫管理
elif st.session_state.active_tab == "📦 在庫管理" and st.session_state["logged_in"]:
    st.header("📦 部品在庫管理")
    v_cat = st.selectbox("表示フィルタ", ["すべて"] + categories)
    d_stock = stock_df.copy()
    if v_cat != "すべて": d_stock = d_stock[d_stock["分類"] == v_cat]
    st.dataframe(d_stock, use_container_width=True)

    with st.expander("➕ 新しい部品を登録する"):
        with st.form("new_stock"):
            n_cat, n_name = st.selectbox("分類", categories), st.text_input("部品名")
            n_qty, n_price = st.number_input("在庫数", 0), st.number_input("単価", 0)
            if st.form_submit_button("登録"):
                new_row = pd.DataFrame([{"分類": n_cat, "部品名": n_name, "在庫数": n_qty, "単価": n_price, "発注点": 5, "最終更新日": datetime.now().strftime('%Y-%m-%d')}])
                conn.update(worksheet="stock_data", data=pd.concat([stock_df, new_row], ignore_index=True))
                st.success("登録完了"); time.sleep(1); st.rerun()

    st.markdown("---")
    st.subheader("🛠️ 在庫の修正・削除")
    s_cat_sel = st.selectbox("分類選択", categories, key="s_cat")
    f_items = stock_df[stock_df["分類"] == s_cat_sel]
    if not f_items.empty:
        t_item = st.selectbox("部品を選択", f_items["部品名"].tolist())
        s_idx = stock_df[stock_df["部品名"] == t_item].index[0]
        with st.form("edit_stk"):
            eq = st.number_input("在庫数", value=int(stock_df.loc[s_idx, "在庫数"]))
            ep = st.number_input("単価", value=int(stock_df.loc[s_idx, "単価"]))
            if st.form_submit_button("在庫情報を更新"):
                stock_df.loc[s_idx, ["在庫数", "単価", "最終更新日"]] = [eq, ep, datetime.now().strftime('%Y-%m-%d')]
                conn.update(worksheet="stock_data", data=stock_df); st.success("更新完了"); time.sleep(1); st.rerun()
        if st.button(f"🗑️ {t_item} を削除"):
            conn.update(worksheet="stock_data", data=stock_df[stock_df["部品名"] != t_item]); st.warning("削除完了"); time.sleep(1); st.rerun()

# 📝 メンテナンス登録
elif st.session_state.active_tab == "📝 メンテナンス登録" and st.session_state["logged_in"]:
    st.header("📝 メンテナンス記録の入力")
    with st.form("main_reg", clear_on_submit=True):
        c1, c2 = st.columns(2)
        en, ed = c1.selectbox("分類", categories), c1.text_input("機番・名称")
        wt, wc = c2.date_input("作業日", datetime.today()), c2.number_input("費用", 0)
        wd, wn = st.text_area("作業内容"), st.text_area("備考")
        up1, up2 = st.file_uploader("修理前", type=['jpg','png']), st.file_uploader("修理後", type=['jpg','png'])
        
        if st.form_submit_button("記録を保存"):
            b1, b2 = image_to_base64(up1), image_to_base64(up2)
            new_record = pd.DataFrame([{
                "設備名": f"[{en}] {ed}", 
                "最終点検日": wt.strftime('%Y-%m-%d'), 
                "作業内容": wd, 
                "費用": wc, 
                "備考": wn, 
                "画像": b1 or "", 
                "画像2": b2 or ""
            }])
            conn.update(worksheet="maintenance_data", data=pd.concat([df.drop(columns=['label'], errors='ignore'), new_record], ignore_index=True))
            st.success("保存完了！"); time.sleep(1); st.rerun()
