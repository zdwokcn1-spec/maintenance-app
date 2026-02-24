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
        st.error(f"データ読み込み失敗: {e}")
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

# メンテナンスデータの日付補完（必ず表示させる）
df['最終点検日'] = pd.to_datetime(df['最終点検日'], errors='coerce')
df['最終点検日'] = df['最終点検日'].fillna(pd.Timestamp(date.today()))
df['費用'] = pd.to_numeric(df['費用'], errors='coerce').fillna(0).astype(int)

# 在庫データの型変換
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
    return None

# --- 5. メニュー ---
tab_titles = ["📊 ダッシュボード", "📁 過去履歴"]
if st.session_state["logged_in"]:
    tab_titles += ["📦 在庫管理", "📝 メンテナンス登録"]

if "active_tab" not in st.session_state: st.session_state.active_tab = tab_titles[0]
def on_tab_change(): st.session_state.active_tab = st.session_state.menu_radio

selected_tab = st.radio("メニュー", tab_titles, horizontal=True, label_visibility="collapsed", key="menu_radio", index=tab_titles.index(st.session_state.active_tab) if st.session_state.active_tab in tab_titles else 0, on_change=on_tab_change)
categories = ["ジョークラッシャ", "インパクトクラッシャー", "スクリーン", "ベルト", "その他"]

# ================================================================
# 📊 0. ダッシュボード（省略せずそのまま）
# ================================================================
if st.session_state.active_tab == "📊 ダッシュボード":
    st.header("📊 メンテナンス集計分析")
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

# ================================================================
# 📁 1. 過去履歴 (修正・削除)
# ================================================================
elif st.session_state.active_tab == "📁 過去履歴":
    st.header("📁 履歴表示・編集・削除")
    if not df.empty:
        s_df = df.sort_values(by="最終点検日", ascending=False)
        for i, row in s_df.iterrows():
            d_str = row['最終点検日'].strftime('%Y-%m-%d')
            with st.expander(f"{d_str} | {row['設備名']}"):
                v1, v2 = st.columns([2, 1])
                v1.write(f"**内容:** {row['作業内容']}\n**費用:** {row['費用']:,} 円\n**備考:** {row['備考']}")
                with v2:
                    i1, i2 = st.columns(2)
                    if len(str(row['画像'])) > 20: i1.image(base64.b64decode(row['画像']), caption="修理前")
                    if len(str(row['画像2'])) > 20: i2.image(base64.b64decode(row['画像2']), caption="修理後")
        
        if st.session_state["logged_in"]:
            st.markdown("---")
            st.subheader("🛠️ 履歴の修正・削除")
            df['label'] = [r['最終点検日'].strftime('%Y-%m-%d') + " | " + str(r['設備名']) for _, r in df.iterrows()]
            target = st.selectbox("修正対象を選択", df['label'].tolist())
            idx = df[df['label'] == target].index[0]
            
            with st.form("edit_h"):
                c1, c2 = st.columns(2)
                u_date = c1.date_input("作業日", df.loc[idx, "最終点検日"])
                u_equip = c1.text_input("設備名", df.loc[idx, "設備名"])
                u_cost = c1.number_input("費用", value=int(df.loc[idx, "費用"]))
                u_desc = st.text_area("内容", df.loc[idx, "作業内容"])
                u_note = st.text_area("備考", df.loc[idx, "備考"])
                new_up1 = st.file_uploader("新しい修理前写真", type=['jpg','png','jpeg'])
                new_up2 = st.file_uploader("新しい修理後写真", type=['jpg','png','jpeg'])

                if st.form_submit_button("修正を保存"):
                    df.loc[idx, ["最終点検日", "設備名", "作業内容", "備考", "費用"]] = [pd.to_datetime(u_date), u_equip, u_desc, u_note, u_cost]
                    if new_up1: df.loc[idx, "画像"] = image_to_base64(new_up1)
                    if new_up2: df.loc[idx, "画像2"] = image_to_base64(new_up2)
                    df_to_save = df.drop(columns=['label']).copy()
                    df_to_save['最終点検日'] = df_to_save['最終点検日'].dt.strftime('%Y-%m-%d')
                    conn.update(worksheet="maintenance_data", data=df_to_save)
                    st.success("保存完了"); time.sleep(1); st.rerun()

            if st.button("🚨 この履歴を削除"):
                df_to_save = df.drop(idx).drop(columns=['label']).copy()
                df_to_save['最終点検日'] = df_to_save['最終点検日'].dt.strftime('%Y-%m-%d')
                conn.update(worksheet="maintenance_data", data=df_to_save)
                st.warning("削除完了"); time.sleep(1); st.rerun()

# ================================================================
# 📦 2. 在庫管理（修正・削除機能を完全復旧）
# ================================================================
elif st.session_state.active_tab == "📦 在庫管理" and st.session_state["logged_in"]:
    st.header("📦 在庫管理・修正")
    
    # 1. 在庫一覧の表示
    st.dataframe(stock_df, use_container_width=True)
    
    # 2. 新規追加フォーム
    with st.expander("➕ 新規部品を登録する"):
        with st.form("new_stock_form"):
            c1, c2 = st.columns(2)
            new_cat = c1.selectbox("分類", categories)
            new_name = c1.text_input("部品名")
            new_qty = c2.number_input("初期在庫数", min_value=0, value=0)
            new_price = c2.number_input("単価", min_value=0, value=0)
            new_alert = c2.number_input("発注点（この数を下回ると警告）", min_value=0, value=5)
            
            if st.form_submit_button("新規登録"):
                if new_name:
                    new_row = pd.DataFrame([{
                        "分類": new_cat, "部品名": new_name, "在庫数": new_qty, 
                        "単価": new_price, "発注点": new_alert, 
                        "最終更新日": date.today().strftime('%Y-%m-%d')
                    }])
                    updated_stock = pd.concat([stock_df, new_row], ignore_index=True)
                    conn.update(worksheet="stock_data", data=updated_stock)
                    st.success(f"{new_name} を登録しました"); time.sleep(1); st.rerun()
                else:
                    st.error("部品名を入力してください")

    st.markdown("---")
    
    # 3. 在庫の修正・削除フォーム
    st.subheader("🛠️ 在庫データの修正・削除")
    if not stock_df.empty:
        selected_stock_name = st.selectbox("修正する部品を選択", stock_df["部品名"].tolist())
        s_idx = stock_df[stock_df["部品名"] == selected_stock_name].index[0]
        
        with st.form("edit_stock_form"):
            st.write(f"対象: **{selected_stock_name}**")
            c1, c2 = st.columns(2)
            u_stock_qty = c1.number_input("現在の在庫数", value=int(stock_df.loc[s_idx, "在庫数"]))
            u_stock_price = c1.number_input("単価", value=int(stock_df.loc[s_idx, "単価"]))
            u_stock_alert = c2.number_input("発注点", value=int(stock_df.loc[s_idx, "発注点"]))
            u_stock_cat = c2.selectbox("分類を変更", categories, index=categories.index(stock_df.loc[s_idx, "分類"]) if stock_df.loc[s_idx, "分類"] in categories else 0)
            
            if st.form_submit_button("在庫データを更新"):
                stock_df.loc[s_idx, ["分類", "在庫数", "単価", "発注点", "最終更新日"]] = [
                    u_stock_cat, u_stock_qty, u_stock_price, u_stock_alert, date.today().strftime('%Y-%m-%d')
                ]
                conn.update(worksheet="stock_data", data=stock_df)
                st.success("在庫情報を更新しました"); time.sleep(1); st.rerun()
        
        if st.button(f"🗑️ {selected_stock_name} をリストから完全に削除"):
            new_stock_df = stock_df.drop(s_idx)
            conn.update(worksheet="stock_data", data=new_stock_df)
            st.warning("削除しました"); time.sleep(1); st.rerun()

# ================================================================
# 📝 3. メンテナンス登録（省略せずそのまま）
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
            new_r = pd.DataFrame([{
                "設備名": f"[{en}] {ed}", "最終点検日": wt.strftime('%Y-%m-%d'), 
                "作業内容": wd, "費用": wc, "備考": wn, "画像": b1 or "", "画像2": b2 or ""
            }])
            df_for_save = df.copy()
            if 'label' in df_for_save.columns: df_for_save = df_for_save.drop(columns=['label'])
            df_for_save['最終点検日'] = df_for_save['最終点検日'].dt.strftime('%Y-%m-%d')
            updated_df = pd.concat([df_for_save, new_r], ignore_index=True)
            conn.update(worksheet="maintenance_data", data=updated_df)
            st.success("登録完了"); time.sleep(1); st.rerun()
