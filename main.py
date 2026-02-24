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

# --- 3. データ読み込み ---
conn = st.connection("gsheets", type=GSheetsConnection)
def load_data():
    df = conn.read(worksheet="maintenance_data", ttl="1s")
    stock = conn.read(worksheet="stock_data", ttl="1s")
    return df, stock

df_raw, stock_df_raw = load_data()

# --- 4. データ整形 ---
# メンテナンスデータ
m_cols = ['設備名', '最終点検日', '作業内容', '費用', '備考', '画像', '画像2']
df = df_raw.copy()
for col in m_cols:
    if col not in df.columns: df[col] = ""
df = df[m_cols]

# グラフ計算用の日付（errors='coerce'で不正なものはNaTにするが、元の'最終点検日'列は書き換えない）
df['最終点検日_dt'] = pd.to_datetime(df['最終点検日'], errors='coerce')
df['費用'] = pd.to_numeric(df['費用'], errors='coerce').fillna(0).astype(int)

# 在庫データ
s_cols = ['分類', '部品名', '在庫数', '単価', '発注点', '最終更新日']
stock_df = stock_df_raw.copy()
for col in s_cols:
    if col not in stock_df.columns: stock_df[col] = ""
stock_df['在庫数'] = pd.to_numeric(stock_df['在庫数'], errors='coerce').fillna(0).astype(int)
stock_df['単価'] = pd.to_numeric(stock_df['単価'], errors='coerce').fillna(0).astype(int)

def image_to_base64(uploaded_file):
    if uploaded_file:
        img = Image.open(uploaded_file)
        img.thumbnail((400, 400))
        if img.mode != 'RGB': img = img.convert('RGB')
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=60, optimize=True)
        return base64.b64encode(buf.getvalue()).decode()
    return ""

# --- 5. メニュー ---
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
    valid_df = df.dropna(subset=['最終点検日_dt'])
    if not valid_df.empty:
        st.subheader("📅 集計期間指定")
        col_d1, col_d2 = st.columns(2)
        start_date = col_d1.date_input("開始日", valid_df['最終点検日_dt'].min().date())
        end_date = col_d2.date_input("終了日", valid_df['最終点検日_dt'].max().date())
        
        mask = (df['最終点検日_dt'].dt.date >= start_date) & (df['最終点検日_dt'].dt.date <= end_date)
        f_df = df.loc[mask].copy()

        if not f_df.empty:
            f_df['大分類'] = f_df['設備名'].str.extract(r'\[(.*?)\]')[0].fillna("その他")
            f_df['年月'] = f_df['最終点検日_dt'].dt.strftime('%Y-%m')
            
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
                fig2, ax2 = plt.subplots(); ax2.plot(e_counts.index, e_counts.values, marker='o', color='#e67e22')
                ax2.yaxis.set_major_locator(MultipleLocator(1))
                st.pyplot(fig2)
            st.metric("期間内合計費用", f"{int(f_df['費用'].sum()):,} 円")
    else:
        st.warning("日付の入ったデータがありません。")

# ================================================================
# 📁 1. 過去履歴
# ================================================================
elif selected_tab == "📁 過去履歴":
    st.header("📁 履歴表示・編集・削除")
    if not df.empty:
        s_df = df.sort_values(by="最終点検日_dt", ascending=False)
        for i, row in s_df.iterrows():
            # ★重要：補正された日付ではなく、スプレッドシートの文字をそのまま出す
            d_display = str(row['最終点検日']).split(" ")[0] if row['最終点検日'] else "日付未設定"
            with st.expander(f"{d_display} | {row['設備名']}"):
                v1, v2 = st.columns([2, 1])
                v1.write(f"**内容:** {row['作業内容']}\n**費用:** {row['費用']:,} 円\n**備考:** {row['備考']}")
                with v2:
                    if len(row['画像']) > 20: st.image(base64.b64decode(row['画像']), caption="修理前")
                    if len(row['画像2']) > 20: st.image(base64.b64decode(row['画像2']), caption="修理後")
        
        if st.session_state["logged_in"]:
            st.markdown("---")
            st.subheader("🛠️ 履歴の修正・削除")
            df['label'] = [f"{r['最終点検日']} | {r['設備名']}" for _, r in df.iterrows()]
            target = st.selectbox("修正対象を選択", df['label'].tolist())
            idx = df[df['label'] == target].index[0]
            
            with st.form("edit_h"):
                cur_d = row['最終点検日_dt'].date() if pd.notnull(df.loc[idx, '最終点検日_dt']) else date.today()
                u_date = st.date_input("作業日", cur_d)
                u_equip = st.text_input("設備名", df.loc[idx, "設備名"])
                u_cost = st.number_input("費用", value=int(df.loc[idx, "費用"]))
                u_desc = st.text_area("内容", df.loc[idx, "作業内容"])
                u_note = st.text_area("備考", df.loc[idx, "備考"])
                up1 = st.file_uploader("前写真変更", type=['jpg','png'])
                up2 = st.file_uploader("後写真変更", type=['jpg','png'])

                if st.form_submit_button("修正を保存"):
                    df.loc[idx, "最終点検日"] = u_date.strftime('%Y-%m-%d')
                    df.loc[idx, ["設備名", "作業内容", "備考", "費用"]] = [u_equip, u_desc, u_note, u_cost]
                    if up1: df.loc[idx, "画像"] = image_to_base64(up1)
                    if up2: df.loc[idx, "画像2"] = image_to_base64(up2)
                    conn.update(worksheet="maintenance_data", data=df[m_cols])
                    st.success("更新完了"); time.sleep(1); st.rerun()

# ================================================================
# 📦 2. 在庫管理
# ================================================================
elif selected_tab == "📦 在庫管理" and st.session_state["logged_in"]:
    st.header("📦 在庫管理")
    st.dataframe(stock_df, use_container_width=True)
    
    with st.expander("🛠️ 在庫修正・削除"):
        sel_part = st.selectbox("部品を選択", stock_df["部品名"].tolist())
        s_idx = stock_df[stock_df["部品名"] == sel_part].index[0]
        with st.form("s_edit"):
            sq = st.number_input("在庫数", value=int(stock_df.loc[s_idx, "在庫数"]))
            sp = st.number_input("単価", value=int(stock_df.loc[s_idx, "単価"]))
            if st.form_submit_button("更新"):
                stock_df.loc[s_idx, ["在庫数", "単価", "最終更新日"]] = [sq, sp, date.today().strftime('%Y-%m-%d')]
                conn.update(worksheet="stock_data", data=stock_df)
                st.success("在庫更新"); time.sleep(1); st.rerun()
        if st.button("🚨 部品を削除"):
            conn.update(worksheet="stock_data", data=stock_df.drop(s_idx))
            st.rerun()

    with st.expander("➕ 新規部品登録"):
        with st.form("s_new"):
            c1, c2 = st.columns(2)
            n_c, n_n = c1.selectbox("分類", categories), c1.text_input("部品名")
            n_q, n_p = c2.number_input("在庫", 0), c2.number_input("単価", 0)
            if st.form_submit_button("登録"):
                new_s = pd.DataFrame([{"分類": n_c, "部品名": n_n, "在庫数": n_q, "単価": n_p, "発注点": 5, "最終更新日": date.today().strftime('%Y-%m-%d')}])
                conn.update(worksheet="stock_data", data=pd.concat([stock_df, new_s], ignore_index=True))
                st.rerun()

# ================================================================
# 📝 3. メンテナンス登録
# ================================================================
elif selected_tab == "📝 メンテナンス登録" and st.session_state["logged_in"]:
    st.header("📝 記録入力")
    with st.form("reg", clear_on_submit=True):
        c1, c2 = st.columns(2)
        en, ed = c1.selectbox("分類", categories), c1.text_input("機番・名称")
        wt, wc = c2.date_input("作業日", date.today()), c2.number_input("費用", 0)
        wd, wn = st.text_area("内容"), st.text_area("備考")
        up1, up2 = st.file_uploader("修理前", type=['jpg','png']), st.file_uploader("修理後", type=['jpg','png'])
        
        if st.form_submit_button("保存"):
            new_r = pd.DataFrame([{
                "設備名": f"[{en}] {ed}", "最終点検日": wt.strftime('%Y-%m-%d'),
                "作業内容": wd, "費用": wc, "備考": wn,
                "画像": image_to_base64(up1), "画像2": image_to_base64(up2)
            }])
            # 修正後の df ではなく、読み込み時の生データ df_raw に追加して保存
            updated_df = pd.concat([df_raw, new_r], ignore_index=True)
            conn.update(worksheet="maintenance_data", data=updated_df)
            st.success(f"{wt.strftime('%Y-%m-%d')} で登録完了！"); time.sleep(1); st.rerun()
