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
st.set_page_config(page_title="設備メンテナンス管理システム", layout="wide")

# --- 2. 権限管理システム (3人対応 & F5対策) ---
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
                st.error("認証失敗: IDまたはパスワードが違います")
        st.info("💡 ログインなし：閲覧のみ\n💡 ログインあり：編集・登録可能")
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
        st.error("Google Sheetsへのアクセス制限中です。")
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

for col in ['画像', '画像2']: df[col] = df[col].fillna("").astype(str)
df['最終点検日'] = pd.to_datetime(df['最終点検日'], errors='coerce')
df['費用'] = pd.to_numeric(df['費用'], errors='coerce').fillna(0).astype(int)

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
    "メニュー", tab_titles, horizontal=True, label_visibility="collapsed", 
    key="menu_radio", index=tab_titles.index(st.session_state.active_tab),
    on_change=on_tab_change
)

categories = ["ジョークラッシャ", "インパクトクラッシャー", "スクリーン", "ベルト", "その他"]

# ================================================================
# 📊 0. ダッシュボード (期間集計 & 折れ線グラフ版)
# ================================================================
if st.session_state.active_tab == "📊 ダッシュボード":
    st.header("📊 メンテナンス状況集計")
    
    if not df.empty:
        # 期間フィルター用サイドバー/トップ
        min_date = df['最終点検日'].min().date()
        max_date = df['最終点検日'].max().date()
        
        st.subheader("📅 集計期間の指定")
        date_range = st.date_input("期間を選択してください", [min_date, max_date], min_value=min_date, max_value=max_date)
        
        # フィルター適用
        if isinstance(date_range, list) or isinstance(date_range, tuple):
            if len(date_range) == 2:
                start_d, end_d = date_range
                mask = (df['最終点検日'].dt.date >= start_d) & (df['最終点検日'].dt.date <= end_d)
                filtered_df = df.loc[mask].copy()
            else:
                filtered_df = df.copy()
        else:
            filtered_df = df.copy()

        if not filtered_df.empty:
            filtered_df['大分類'] = filtered_df['設備名'].str.extract(r'\[(.*?)\]')[0].fillna("その他")
            filtered_df['年月'] = filtered_df['最終点検日'].dt.strftime('%Y-%m')
            
            c1, c2 = st.columns(2)
            
            with c1:
                st.subheader("💰 月別・費用合計 (縦棒)")
                monthly_cost = filtered_df.groupby('年月')['費用'].sum().sort_index()
                fig1, ax1 = plt.subplots()
                monthly_cost.plot(kind='bar', ax=ax1, color='#3498db', zorder=3)
                ax1.set_ylabel("費用 (円)")
                plt.xticks(rotation=45)
                ax1.grid(axis='y', linestyle='--', alpha=0.7)
                st.pyplot(fig1)

            with c2:
                st.subheader("📈 設備別・メンテナンス回数 (折れ線)")
                # 回数集計
                equip_counts = filtered_df['大分類'].value_counts().sort_index()
                fig2, ax2 = plt.subplots()
                # 折れ線グラフとして描画
                ax2.plot(equip_counts.index, equip_counts.values, marker='o', linestyle='-', color='#e67e22', linewidth=2)
                ax2.set_ylabel("修理・メンテ回数")
                plt.xticks(rotation=45)
                ax2.grid(linestyle='--', alpha=0.7)
                st.pyplot(fig2)
                
            st.markdown("---")
            m1, m2, m3 = st.columns(3)
            m1.metric("指定期間の合計費用", f"{filtered_df['費用'].sum():,} 円")
            m2.metric("指定期間のメンテ回数", f"{len(filtered_df)} 回")
            m3.metric("稼働中の設備カテゴリ", f"{len(filtered_df['大分類'].unique())}")
        else:
            st.warning("選択された期間にデータがありません。")

# ================================================================
# 📁 1. 過去履歴 / 📦 2. 在庫管理 / 📝 3. 登録 (以前と同様)
# ================================================================
elif st.session_state.active_tab == "📁 過去履歴":
    st.header("📁 メンテナンス過去履歴")
    # ... (履歴表示と編集のコードは前回と同じ) ...
    if not df.empty:
        sorted_df = df.sort_values(by="最終点検日", ascending=False)
        for i, row in sorted_df.iterrows():
            with st.expander(f"{row['最終点検日'].strftime('%Y-%m-%d')} | {row['設備名']}"):
                v1, v2 = st.columns([2, 1])
                v1.write(f"**作業内容:** {row['作業内容']}\n\n**費用:** {row['費用']:,} 円")
                with v2:
                    i1, i2 = st.columns(2)
                    if len(str(row['画像'])) > 20: i1.image(base64.b64decode(row['画像']), caption="修理前")
                    if len(str(row['画像2'])) > 20: i2.image(base64.b64decode(row['画像2']), caption="修理後")
        
        if st.session_state["logged_in"]:
            st.markdown("---")
            st.subheader("🛠️ 履歴の修正・削除")
            df['label'] = df['最終点検日'].dt.strftime('%Y-%m-%d') + " | " + df['設備名'].astype(str)
            target_h = st.selectbox("修正対象を選択", df['label'].tolist())
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

elif st.session_state.active_tab == "📦 在庫管理" and st.session_state["logged_in"]:
    st.header("📦 部品在庫管理")
    v_cat = st.selectbox("表示フィルタ", ["すべて"] + categories)
    d_stock = stock_df.copy()
    if v_cat != "すべて": d_stock = d_stock[d_stock["分類"] == v_cat]
    st.dataframe(d_stock, use_container_width=True)
    # ... (在庫登録・編集のコードは前回と同じ) ...

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
            new_record = pd.DataFrame([{"設備名": f"[{en}] {ed}", "最終点検日": wt.strftime('%Y-%m-%d'), "作業内容": wd, "費用": wc, "備考": wn, "画像": b1 or "", "画像2": b2 or ""}])
            conn.update(worksheet="maintenance_data", data=pd.concat([df.drop(columns=['label'], errors='ignore'), new_record], ignore_index=True))
            st.success("保存完了！"); time.sleep(1); st.rerun()
