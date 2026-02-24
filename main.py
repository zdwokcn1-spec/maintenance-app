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
    except Exception as e:
        st.error(f"データ読み込み失敗。詳細: {e}")
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

# 画像データの欠損埋め
for col in ['画像', '画像2']: df[col] = df[col].fillna("").astype(str)

# ★重要：日付の読み込みを徹底強化
# 一旦日付に変換し、エラー（空欄や不正な文字）はNaT（欠損値）にする
df['最終点検日'] = pd.to_datetime(df['最終点検日'], errors='coerce')
# 数値変換
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

# ================================================================
# 📊 0. ダッシュボード
# ================================================================
if st.session_state.active_tab == "📊 ダッシュボード":
    st.header("📊 メンテナンス集計分析")
    valid_df = df.dropna(subset=['最終点検日'])
    if not valid_df.empty:
        st.subheader("📅 集計期間指定")
        col_d1, col_d2 = st.columns(2)
        start_date = col_d1.date_input("開始日", valid_df['最終点検日'].min().date())
        end_date = col_d2.date_input("終了日", valid_df['最終点検日'].max().date())
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
                fig2, ax2 = plt.subplots(); ax2.plot(e_counts.index, e_counts.values, marker='o', color='#e67e22')
                ax2.yaxis.set_major_locator(MultipleLocator(1))
                st.pyplot(fig2)
            st.metric("期間内合計費用", f"{int(f_df['費用'].sum()):,} 円")
    else:
        st.warning("表示できるデータがありません。")

# ================================================================
# 📁 1. 過去履歴 (修正・削除)
# ================================================================
elif st.session_state.active_tab == "📁 過去履歴":
    st.header("📁 履歴表示・編集・削除")
    if not df.empty:
        # 日付順に並び替え
        s_df = df.sort_values(by="最終点検日", ascending=False)
        for i, row in s_df.iterrows():
            # ★表示用：日付が正常ならYYYY-MM-DD、壊れていたら「(日付未設定)」とする
            d_display = row['最終点検日'].strftime('%Y-%m-%d') if pd.notnull(row['最終点検日']) else "(日付未設定)"
            
            with st.expander(f"{d_display} | {row['設備名']}"):
                v1, v2 = st.columns([2, 1])
                v1.write(f"**内容:** {row['作業内容']}\n**費用:** {row['費用']:,} 円\n**備考:** {row['備考']}")
                with v2:
                    i1, i2 = st.columns(2)
                    if len(str(row['画像'])) > 20: i1.image(base64.b64decode(row['画像']), caption="修理前")
                    if len(str(row['画像2'])) > 20: i2.image(base64.b64decode(row['画像2']), caption="修理後")
        
        if st.session_state["logged_in"]:
            st.markdown("---")
            st.subheader("🛠️ 履歴の修正・削除")
            # セレクトボックス用ラベル：ここでも日付をチェック
            df['label'] = [(r['最終点検日'].strftime('%Y-%m-%d') if pd.notnull(r['最終点検日']) else "日付不正") + " | " + str(r['設備名']) for _, r in df.iterrows()]
            target = st.selectbox("修正対象を選択", df['label'].tolist())
            idx = df[df['label'] == target].index[0]
            
            with st.form("edit_h"):
                c1, c2 = st.columns(2)
                # 不正な日付の場合は今日をデフォルトにする
                init_val = df.loc[idx, "最終点検日"] if pd.notnull(df.loc[idx, "最終点検日"]) else date.today()
                u_date = c1.date_input("作業日", init_val)
                u_equip = c1.text_input("設備名", df.loc[idx, "設備名"])
                u_cost = c1.number_input("費用", value=int(df.loc[idx, "費用"]))
                u_desc = st.text_area("内容", df.loc[idx, "作業内容"])
                u_note = st.text_area("備考", df.loc[idx, "備考"])
                
                col_img1, col_img2 = st.columns(2)
                new_up1 = col_img1.file_uploader("新しい修理前写真", type=['jpg','png','jpeg'])
                new_up2 = col_img2.file_uploader("新しい修理後写真", type=['jpg','png','jpeg'])

                if st.form_submit_button("修正を保存"):
                    df.loc[idx, ["最終点検日", "設備名", "作業内容", "備考", "費用"]] = [pd.to_datetime(u_date), u_equip, u_desc, u_note, u_cost]
                    if new_up1: df.loc[idx, "画像"] = image_to_base64(new_up1)
                    if new_up2: df.loc[idx, "画像2"] = image_to_base64(new_up2)

                    # 保存前に全データの日付を文字列化
                    df_to_save = df.drop(columns=['label']).copy()
                    df_to_save['最終点検日'] = df_to_save['最終点検日'].dt.strftime('%Y-%m-%d')
                    conn.update(worksheet="maintenance_data", data=df_to_save)
                    st.success("更新完了しました"); time.sleep(1); st.rerun()

# ================================================================
# 📦 2. 在庫管理 (修正・削除)
# ================================================================
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

# ================================================================
# 📝 3. メンテナンス登録
# ================================================================
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
            
            # 新規データ
            new_r = pd.DataFrame([{
                "設備名": f"[{en}] {ed}", 
                "最終点検日": wt.strftime('%Y-%m-%d'), 
                "作業内容": wd, 
                "費用": wc, 
                "備考": wn, 
                "画像": b1 or "", 
                "画像2": b2 or ""
            }])
            
            # 保存処理：既存データも安全に文字列化して結合
            df_for_concat = df.copy()
            # labelなどの一時的な列があれば削除
            if 'label' in df_for_concat.columns: df_for_concat = df_for_concat.drop(columns=['label'])
            # 全ての日付を文字列に変換
            df_for_concat['最終点検日'] = df_for_concat['最終点検日'].dt.strftime('%Y-%m-%d')
            
            updated_df = pd.concat([df_for_concat, new_r], ignore_index=True)
            conn.update(worksheet="maintenance_data", data=updated_df)
            st.success("登録完了！履歴を確認してください。"); time.sleep(1); st.rerun()
