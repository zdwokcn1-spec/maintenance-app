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
m_cols = ['設備 name', '最終点検日', '作業内容', '費用', '備考', '画像', '画像2'] # 列名はシートに合わせる
# シートの列名を補正
df = df_raw.copy()
# 確実に必要な列が存在するようにする
for col in ['設備名', '最終点検日', '作業内容', '費用', '備考', '画像', '画像2']:
    if col not in df.columns: df[col] = ""

# エラー対策：画像列と日付列の文字列化
df['画像'] = df['画像'].fillna("").astype(str)
df['画像2'] = df['画像2'].fillna("").astype(str)
df['最終点検日'] = df['最終点検日'].fillna("").astype(str)

# ★【最重要】表示・ソート用に日付型へ変換した作業列を作成
df['sort_date'] = pd.to_datetime(df['最終点検日'], errors='coerce')
# 日付が壊れているものは非常に古い日付にして最後に回す
df['sort_date'] = df['sort_date'].fillna(pd.Timestamp('1900-01-01'))

# 在庫データの整形
stock_df = stock_df_raw.copy()
for col in ['分類', '部品名', '在庫数', '単価', '発注点', '最終更新日']:
    if col not in stock_df.columns: stock_df[col] = ""

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
    # ... (前回のグラフコードを維持)
    f_df = df[df['sort_date'] > '1900-01-01'].copy()
    if not f_df.empty:
        f_df['年月'] = f_df['sort_date'].dt.strftime('%Y-%m')
        st.subheader("💰 月別費用")
        st.bar_chart(f_df.groupby('年月')['費用'].sum())
        st.subheader("📈 設備別回数（折れ線）")
        st.line_chart(f_df['設備名'].value_counts())

# ================================================================
# 📁 1. 過去履歴（新しい順に並び替え）
# ================================================================
elif selected_tab == "📁 過去履歴":
    st.header("📁 履歴表示（新しい順）")
    if not df.empty:
        # ★ここで新しい順にソートして表示
        display_df = df.sort_values(by="sort_date", ascending=False)
        
        for i, row in display_df.iterrows():
            d_label = row['最終点検日'] if row['最終点検日'] != "" else "日付未設定"
            with st.expander(f"{d_label} | {row['設備名']}"):
                c1, c2 = st.columns([2, 1])
                c1.write(f"**内容:** {row['作業内容']}\n**費用:** {int(float(row['費用'] or 0)):,} 円\n**備考:** {row['備考']}")
                with c2:
                    if len(row['画像']) > 20: st.image(base64.b64decode(row['画像']), caption="修理前")
                    if len(row['画像2']) > 20: st.image(base64.b64decode(row['画像2']), caption="修理後")
        
        if st.session_state["logged_in"]:
            st.markdown("---")
            st.subheader("🛠️ 履歴の修正・削除")
            # 選択肢も新しい順
            df_sorted = df.sort_values(by="sort_date", ascending=False)
            df_sorted['select_label'] = df_sorted['最終点検日'] + " | " + df_sorted['設備名']
            target = st.selectbox("修正対象を選択", df_sorted['select_label'].tolist())
            # 選択したラベルから元のIndexを特定
            idx = df_sorted[df_sorted['select_label'] == target].index[0]
            
            with st.form("edit_history"):
                u_date = st.date_input("作業日", df.loc[idx, 'sort_date'])
                u_equip = st.text_input("設備名", df.loc[idx, '設備名'])
                u_content = st.text_area("内容", df.loc[idx, '作業内容'])
                if st.form_submit_button("修正を保存"):
                    df.loc[idx, '最終点検日'] = u_date.strftime('%Y-%m-%d')
                    df.loc[idx, '設備名'] = u_equip
                    df.loc[idx, '作業内容'] = u_content
                    # 保存時はソート用列を除いて保存
                    save_data = df[['設備名', '最終点検日', '作業内容', '費用', '備考', '画像', '画像2']]
                    conn.update(worksheet="maintenance_data", data=save_data)
                    st.success("更新しました"); time.sleep(1); st.rerun()

# ================================================================
# 📦 2. 在庫管理（省略なし）
# ================================================================
elif selected_tab == "📦 在庫管理" and st.session_state["logged_in"]:
    st.header("📦 在庫管理")
    st.dataframe(stock_df, use_container_width=True)
    col1, col2 = st.columns(2)
    with col1.expander("🛠️ 在庫修正"):
        sel = st.selectbox("部品名", stock_df['部品名'].tolist())
        s_idx = stock_df[stock_df['部品名'] == sel].index[0]
        new_q = st.number_input("在庫数", value=int(float(stock_df.loc[s_idx, '在庫数'] or 0)))
        if st.button("更新"):
            stock_df.loc[s_idx, '在庫数'] = new_q
            stock_df.loc[s_idx, '最終更新日'] = date.today().strftime('%Y-%m-%d')
            conn.update(worksheet="stock_data", data=stock_df)
            st.success("更新完了"); st.rerun()
    with col2.expander("➕ 新規部品"):
        with st.form("new_part"):
            n_c = st.selectbox("分類", categories)
            n_n = st.text_input("部品名")
            if st.form_submit_button("登録"):
                new_row = pd.DataFrame([{"分類": n_c, "部品名": n_n, "在庫数": 0, "単価": 0, "発注点": 5, "最終更新日": date.today().strftime('%Y-%m-%d')}])
                conn.update(worksheet="stock_data", data=pd.concat([stock_df_raw, new_row], ignore_index=True))
                st.rerun()

# ================================================================
# 📝 3. メンテナンス登録（日付問題を解決）
# ================================================================
elif selected_tab == "📝 メンテナンス登録" and st.session_state["logged_in"]:
    st.header("📝 記録入力")
    with st.form("input_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        f_cat = c1.selectbox("分類", categories)
        f_name = c1.text_input("機番・名称")
        f_date = c2.date_input("作業日（ここに入れた日付が保存されます）", date.today())
        f_cost = c2.number_input("費用", 0)
        f_desc = st.text_area("作業内容")
        f_note = st.text_area("備考")
        up1 = st.file_uploader("前写真", type=['jpg','png'])
        up2 = st.file_uploader("後写真", type=['jpg','png'])
        
        if st.form_submit_button("保存"):
            # 1. 新しい行を作成（日付を文字列に固定）
            new_entry = pd.DataFrame([{
                "設備名": f"[{f_cat}] {f_name}",
                "最終点検日": f_date.strftime('%Y-%m-%d'),
                "作業内容": f_desc,
                "費用": f_cost,
                "備考": f_note,
                "画像": image_to_base64(up1),
                "画像2": image_to_base64(up2)
            }])
            
            # 2. 既存の生データと結合
            # ここで一度日付順に並び替えてから保存することで、シート上も綺麗になります
            updated_df = pd.concat([df_raw, new_entry], ignore_index=True)
            
            # 日付順（新しい順）に並び替えてからシートを更新
            # これにより、次にアプリを開いた時も最初から並んでいます
            updated_df['temp_sort'] = pd.to_datetime(updated_df['最終点検日'], errors='coerce')
            updated_df = updated_df.sort_values(by='temp_sort', ascending=False).drop(columns=['temp_sort'])
            
            conn.update(worksheet="maintenance_data", data=updated_df)
            st.success(f"{f_date} の記録を保存し、リストを更新しました。")
            time.sleep(1)
            st.rerun()
