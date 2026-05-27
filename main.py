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

# --- 2. 権限管理システム ---
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if st.query_params.get("auth") == "success":
    st.session_state["logged_in"] = True

with st.sidebar:
    st.title("🔑 権限管理")
    if not st.session_state["logged_in"]:
        user = st.text_input("ユーザー名", key="user_input")
        pw = st.text_input("パスワード", type="password", key="pw_input")
        if st.button("編集モードでログイン"):
            if user == st.secrets["auth"]["username"] and pw == st.secrets["auth"]["password"]:
                st.session_state["logged_in"] = True
                st.query_params["auth"] = "success"
                st.rerun()
            else:
                st.error("認証に失敗しました。")
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
        st.error(f"Google Sheetsへの接続エラー: {e}")
        st.info("APIの利用制限に達している可能性があります。しばらく待ってからページを再読み込みしてください。")
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

# 型変換とデータ整理
for col in ['画像', '画像2']: df[col] = df[col].fillna("").astype(str)
df['最終点検日'] = pd.to_datetime(df['最終点検日'], errors='coerce')
df['費用'] = pd.to_numeric(df['費用'], errors='coerce').fillna(0).astype(int)
stock_df['在庫数'] = pd.to_numeric(stock_df['在庫数'], errors='coerce').fillna(0).astype(int)
stock_df['単価'] = pd.to_numeric(stock_df['単価'], errors='coerce').fillna(0).astype(int)

# 絞り込み用に「大分類」列をここで作成
df['大分類'] = df['設備名'].str.extract(r'\[(.*?)\]')[0].fillna("その他")
categories = ["ジョークラッシャ", "インパクトクラッシャー", "スクリーン", "ベルト", "その他"]


# --- 5. 画像圧縮関数 ---
def image_to_base64(uploaded_file):
    if uploaded_file:
        try:
            img = Image.open(uploaded_file)
            img.thumbnail((400, 400))
            if img.mode != 'RGB': img = img.convert('RGB')
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=60, optimize=True)
            return base64.b64encode(buf.getvalue()).decode()
        except: return None
    return None

# --- 6. メニュー（タブ）切り替え ---
if st.session_state["logged_in"]:
    tab_titles = ["📊 ダッシュボード", "📁 過去履歴", "📦 在庫管理", "📝 メンテナンス登録"]
else:
    tab_titles = ["📊 ダッシュボード", "📁 過去履歴"]

if "active_tab" not in st.session_state or st.session_state.active_tab not in tab_titles:
    st.session_state.active_tab = tab_titles[0]

def on_tab_change(): st.session_state.active_tab = st.session_state.menu_radio
st.radio("メニュー", tab_titles, horizontal=True, label_visibility="collapsed", key="menu_radio", index=tab_titles.index(st.session_state.active_tab), on_change=on_tab_change)

# --- 7. 各画面の表示ロジック ---

# 共通のフィルタリング対象となるDataFrameを作成 (日付がないものは除外)
df_main = df.dropna(subset=['最終点検日']).copy()

# フィルタリングUI関数
def get_filtered_data(df_to_filter):
    st.markdown("---")
    st.subheader("絞り込み条件")
    
    # データがない場合はフィルタリングUIを表示しない
    if df_to_filter.empty:
        st.info("フィルタリング対象のデータがありません。")
        return pd.DataFrame()

    f1, f2 = st.columns(2)
    
    # 期間指定
    min_date = df_to_filter['最終点検日'].min().date()
    max_date = df_to_filter['最終点検日'].max().date()
    
    start_date = f1.date_input('開始日', min_date, min_value=min_date, max_value=max_date, key="start_date")
    end_date = f1.date_input('終了日', max_date, min_value=min_date, max_value=max_date, key="end_date")

    # 分類指定
    unique_categories_in_data = sorted(df_to_filter['大分類'].unique().tolist())
    selected_categories = f2.multiselect('設備分類で絞り込み', options=unique_categories_in_data, default=unique_categories_in_data, key="cat_filter")

    if start_date > end_date:
        st.error('エラー: 終了日は開始日以降に設定してください。')
        return pd.DataFrame()

    # フィルタリング実行
    filtered = df_to_filter[
        (df_to_filter['最終点検日'].dt.date >= start_date) &
        (df_to_filter['最終点検日'].dt.date <= end_date) &
        (df_to_filter['大分類'].isin(selected_categories))
    ]
    st.markdown("---")
    return filtered


# 📊 ダッシュボード
if st.session_state.active_tab == "📊 ダッシュボード":
    st.header("📊 メンテナンス状況概況")
    
    filtered_df = get_filtered_data(df_main)

    if not filtered_df.empty:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("💰 設備別・累計費用")
            cost_by_equip = filtered_df.groupby('大分類')['費用'].sum()
            fig1, ax1 = plt.subplots()
            cost_by_equip.plot(kind='bar', ax=ax1, color='#2ecc71', edgecolor='black')
            ax1.set_ylabel("費用 (円)")
            ax1.set_xlabel("設備大分類")
            ax1.grid(axis='y', linestyle='--', alpha=0.7)
            plt.xticks(rotation=45)
            plt.tight_layout()
            st.pyplot(fig1)

        with c2:
            st.subheader("🔧 設備別・メンテナンス回数")
            count_by_equip = filtered_df.groupby('大分類')['設備名'].count()
            fig2, ax2 = plt.subplots()
            count_by_equip.plot(kind='line', marker='o', ax=ax2, linewidth=2, color='#e74c3c', markersize=8)
            ax2.yaxis.set_major_locator(plt.MaxNLocator(integer=True))
            ax2.set_ylabel("メンテナンス回数 (回)")
            ax2.set_xlabel("設備大分類")
            ax2.grid(True, linestyle='--', alpha=0.7)
            plt.xticks(rotation=45)
            plt.tight_layout()
            st.pyplot(fig2)
    else:
        st.info("指定された条件に合致するデータがありません。")

# 📁 過去履歴
elif st.session_state.active_tab == "📁 過去履歴":
    st.header("📁 メンテナンス過去履歴")
    
    filtered_df = get_filtered_data(df_main)

    if not filtered_df.empty:
        sorted_df = filtered_df.sort_values(by="最終点検日", ascending=False)
        for i, row in sorted_df.iterrows():
            expander_title = f"{row['最終点検日'].strftime('%Y-%m-%d')} | {row['設備名']}"
            with st.expander(expander_title):
                v1, v2 = st.columns([2, 1])
                v1.write(f"**作業内容:**\n\n{row['作業内容']}\n\n**備考:**\n\n{row['備考']}\n\n**費用:** {row['費用']:,} 円")
                with v2:
                    i1, i2 = st.columns(2)
                    if len(str(row['画像'])) > 20: i1.image(base64.b64decode(row['画像']), caption="修理前")
                    if len(str(row['画像2'])) > 20: i2.image(base64.b64decode(row['画像2']), caption="修理後")
        
        if st.session_state["logged_in"]:
            st.markdown("---")
            st.subheader("🛠️ 履歴の修正・削除 (上記で絞り込まれた結果から選択)")
            # 絞り込まれたデータからラベルを作成
            filtered_df['label'] = filtered_df.apply(lambda row: f"{row['最終点検日'].strftime('%Y-%m-%d')} | {row['設備名']}", axis=1)
            target_h = st.selectbox("修正対象を選択", filtered_df['label'].tolist())
            
            if target_h:
                idx_h = filtered_df[filtered_df['label'] == target_h].index[0]
                curr_h = df.loc[idx_h] # 元のdfからインデックスで取得

                with st.form("edit_h_form"):
                    ca, cb = st.columns(2)
                    new_date = ca.date_input("作業日", curr_h["最終点検日"])
                    new_equip = ca.text_input("設備名", curr_h["設備名"])
                    new_cost = ca.number_input("費用", value=int(curr_h["費用"]))
                    new_note = cb.text_area("備考", curr_h["備考"], height=100)
                    new_desc = st.text_area("作業内容", curr_h["作業内容"], height=100)
                    up_f1 = st.file_uploader("修理前を更新", type=['jpg','jpeg','png'], key="up_f1")
                    up_f2 = st.file_uploader("修理後を更新", type=['jpg','jpeg','png'], key="up_f2")

                    if st.form_submit_button("修正を保存"):
                        # 元のデータフレーム'df'の該当行を更新
                        img_b1, img_b2 = image_to_base64(up_f1), image_to_base64(up_f2)
                        if img_b1: df.loc[idx_h, "画像"] = img_b1
                        if img_b2: df.loc[idx_h, "画像2"] = img_b2
                        df.loc[idx_h, ["最終点検日", "設備名", "作業内容", "備考", "費用", "大分類"]] = [pd.to_datetime(new_date), new_equip, new_desc, new_note, new_cost, new_equip.split(']')[0][1:] if ']' in new_equip else "その他"]
                        
                        conn.update(worksheet="maintenance_data", data=df.drop(columns=['label'], errors='ignore'))
                        st.toast("✅ 保存が完了しました。")
                        time.sleep(1); st.rerun()

                if st.button("🚨 この履歴を削除"):
                    conn.update(worksheet="maintenance_data", data=df.drop(idx_h).drop(columns=['label'], errors='ignore'))
                    st.toast("🗑️ 削除が完了しました。")
                    time.sleep(1); st.rerun()
    else:
        st.info("指定された条件に合致する履歴データがありません。")

# 📦 在庫管理
elif st.session_state.active_tab == "📦 在庫管理" and st.session_state["logged_in"]:
    st.header("📦 部品在庫管理")
    
    if not stock_df.empty:
        all_stock_cats = sorted(stock_df["分類"].unique().tolist())
        selected_stock_cats = st.multiselect("分類で絞り込み", options=all_stock_cats, default=all_stock_cats)
        
        if selected_stock_cats:
            d_stock = stock_df[stock_df["分類"].isin(selected_stock_cats)]
            st.dataframe(d_stock.reset_index(drop=True), use_container_width=True)
        else:
            st.info("分類を選択してください。")
    else:
        st.info("在庫データがありません。")

    with st.expander("➕ 新しい部品を登録する"):
        with st.form("new_stock", clear_on_submit=True):
            n_cat = st.selectbox("分類", categories, key="new_s_cat")
            n_name = st.text_input("部品名")
            n_qty = st.number_input("在庫数", min_value=0, step=1)
            n_price = st.number_input("単価", min_value=0, step=1)
            if st.form_submit_button("登録"):
                new_row = pd.DataFrame([{"分類": n_cat, "部品名": n_name, "在庫数": n_qty, "単価": n_price, "発注点": 5, "最終更新日": datetime.now().strftime('%Y-%m-%d')}])
                updated_stock_df = pd.concat([stock_df, new_row], ignore_index=True)
                conn.update(worksheet="stock_data", data=updated_stock_df)
                st.toast("✅ 登録が完了しました。")
                time.sleep(1); st.rerun()

    st.markdown("---")
    st.subheader("🛠️ 在庫の修正・削除")
    if not stock_df.empty:
        s_cat_sel = st.selectbox("分類を選択", sorted(stock_df["分類"].unique().tolist()), key="s_cat_edit")
        f_items = stock_df[stock_df["分類"] == s_cat_sel]
        if not f_items.empty:
            t_item = st.selectbox("部品を選択", f_items["部品名"].tolist())
            if t_item:
                s_idx = stock_df[stock_df["部品名"] == t_item].index[0]
                with st.form("edit_stk"):
                    eq = st.number_input("在庫数", value=int(stock_df.loc[s_idx, "在庫数"]), min_value=0, step=1)
                    ep = st.number_input("単価", value=int(stock_df.loc[s_idx, "単価"]), min_value=0, step=1)
                    if st.form_submit_button("在庫情報を更新"):
                        stock_df.loc[s_idx, ["在庫数", "単価", "最終更新日"]] = [eq, ep, datetime.now().strftime('%Y-%m-%d')]
                        conn.update(worksheet="stock_data", data=stock_df)
                        st.toast("✅ 更新が完了しました。")
                        time.sleep(1); st.rerun()

                if st.button(f"🗑️ 「{t_item}」を削除"):
                    conn.update(worksheet="stock_data", data=stock_df.drop(s_idx))
                    st.toast("🗑️ 削除が完了しました。")
                    time.sleep(1); st.rerun()
    else:
        st.info("修正・削除対象の在庫データがありません。")

# 📝 メンテナンス登録
elif st.session_state.active_tab == "📝 メンテナンス登録" and st.session_state["logged_in"]:
    st.header("📝 メンテナンス記録の入力")
    with st.form("main_reg", clear_on_submit=True):
        c1, c2 = st.columns(2)
        en = c1.selectbox("分類", categories, key="reg_cat")
        ed = c1.text_input("機番・名称")
        wt = c2.date_input("作業日", datetime.today())
        wc = c2.number_input("費用", min_value=0, step=1)
        wd = st.text_area("作業内容", height=150)
        wn = st.text_area("備考", height=100)
        up1 = st.file_uploader("修理前をアップロード", type=['jpg','jpeg','png'])
        up2 = st.file_uploader("修理後をアップロード", type=['jpg','jpeg','png'])

        if st.form_submit_button("記録を保存"):
            b1, b2 = image_to_base64(up1), image_to_base64(up2)
            new_record = pd.DataFrame([{"設備名": f"[{en}] {ed}", "最終点検日": pd.to_datetime(wt), "作業内容": wd, "費用": wc, "備考": wn, "画像": b1 or "", "画像2": b2 or ""}])
            # labelや大分類列は読み込み時に再生成されるので、保存時は元の列構成のみを維持
            df_to_save = df.drop(columns=['大分類', 'label'], errors='ignore')
            updated_df = pd.concat([df_to_save, new_record], ignore_index=True)
            conn.update(worksheet="maintenance_data", data=updated_df)
            st.toast("✅ 保存が完了しました！")
            time.sleep(1); st.rerun()
