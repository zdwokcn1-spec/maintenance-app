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
import re
import json

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

# --- 3. データ読み込み --- ### 修正箇所 ###

# まずConnectionオブジェクトを先に作成
conn = st.connection("gsheets", type=GSheetsConnection)

# キャッシュする関数はConnectionオブジェクトを引数にとり、DataFrameのみを返すようにする
@st.cache_data(ttl=1)
def load_data_from_sheets(_conn):
    try:
        df = _conn.read(worksheet="maintenance_data")
        stock = _conn.read(worksheet="stock_data")
        return df, stock
    except Exception as e:
        st.error(f"Google Sheetsへの接続エラー: {e}")
        st.info("APIの利用制限に達しているか、シート名が間違っている可能性があります。'maintenance_data' と 'stock_data' シートが存在するか確認してください。")
        return pd.DataFrame(), pd.DataFrame()

# 関数を呼び出してデータをロード
df_raw, stock_df_raw = load_data_from_sheets(conn)

if df_raw.empty and stock_df_raw.empty:
    st.warning("データの読み込みに失敗しました。アプリを続行できません。")
    st.stop()


# --- 4. 列名修復 & クリーニング ---
def fix_columns(df, target_cols):
    if df is None or df.empty: return pd.DataFrame(columns=target_cols)
    for col in target_cols:
        if col not in df.columns: df[col] = ""
    return df[target_cols]

m_cols = ['設備名', '最終点検日', '作業内容', '費用', '備考', '画像', '画像2', '使用部品']
df = fix_columns(df_raw, m_cols)
s_cols = ['分類', '部品名', '在庫数', '単価', '発注点', '最終更新日']
stock_df = fix_columns(stock_df_raw, s_cols)

# 型変換とデータ整理
for col in ['画像', '画像2']: df[col] = df[col].fillna("").astype(str)
df['使用部品'] = df['使用部品'].fillna('[]').astype(str)
df['最終点検日'] = pd.to_datetime(df['最終点検日'], errors='coerce')
df['費用'] = pd.to_numeric(df['費用'], errors='coerce').fillna(0).astype(int)
stock_df['在庫数'] = pd.to_numeric(stock_df['在庫数'], errors='coerce').fillna(0).astype(int)
stock_df['単価'] = pd.to_numeric(stock_df['単価'], errors='coerce').fillna(0).astype(int)
stock_df['発注点'] = pd.to_numeric(stock_df['発注点'], errors='coerce').fillna(0).astype(int)

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
tab_titles = ["📊 ダッシュボード", "📁 過去履歴"]
if st.session_state["logged_in"]:
    tab_titles.extend(["📦 在庫管理", "📝 メンテナンス登録"])

if "active_tab" not in st.session_state or st.session_state.active_tab not in tab_titles:
    st.session_state.active_tab = tab_titles[0]

def on_tab_change(): st.session_state.active_tab = st.session_state.menu_radio
st.radio("メニュー", tab_titles, horizontal=True, label_visibility="collapsed", key="menu_radio", index=tab_titles.index(st.session_state.active_tab), on_change=on_tab_change)

# --- 7. 各画面の表示ロジック ---
df_main = df.dropna(subset=['最終点検日']).copy()

def get_filtered_data(df_to_filter):
    st.markdown("---")
    st.subheader("絞り込み条件")
    if df_to_filter.empty:
        st.info("フィルタリング対象のデータがありません。")
        return pd.DataFrame()
    f1, f2 = st.columns(2)
    min_date = df_to_filter['最終点検日'].min().date()
    max_date = df_to_filter['最終点検日'].max().date()
    start_date = f1.date_input('開始日', min_date, min_value=min_date, max_value=max_date, key="start_date")
    end_date = f1.date_input('終了日', max_date, min_value=min_date, max_value=max_date, key="end_date")
    unique_categories_in_data = sorted(df_to_filter['大分類'].unique().tolist())
    selected_categories = f2.multiselect('設備分類で絞り込み', options=unique_categories_in_data, default=unique_categories_in_data, key="cat_filter")
    if start_date > end_date:
        st.error('エラー: 終了日は開始日以降に設定してください。')
        return pd.DataFrame()
    filtered = df_to_filter[(df_to_filter['最終点検日'].dt.date >= start_date) & (df_to_filter['最終点検日'].dt.date <= end_date) & (df_to_filter['大分類'].isin(selected_categories))]
    st.markdown("---")
    return filtered

# --- 在庫操作関数 ---
def update_stock(stock_df, parts_list, operation='subtract'):
    """在庫を増減させる汎用関数"""
    temp_stock = stock_df.copy()
    for part in parts_list:
        part_name = part.get('部品名')
        qty = part.get('個数', 0)
        stock_idx_list = temp_stock[temp_stock['部品名'] == part_name].index
        if not stock_idx_list.empty:
            stock_idx = stock_idx_list[0]
            if operation == 'subtract':
                temp_stock.loc[stock_idx, '在庫数'] -= qty
            elif operation == 'add':
                temp_stock.loc[stock_idx, '在庫数'] += qty
            temp_stock.loc[stock_idx, '最終更新日'] = datetime.now().strftime('%Y-%m-%d')
    return temp_stock

# 📊 ダッシュボード (変更なし)
if st.session_state.active_tab == "📊 ダッシュボード":
    st.header("📊 メンテナンス状況概況")
    filtered_df = get_filtered_data(df_main)
    if not filtered_df.empty:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("💰 設備別・累計費用"); cost_by_equip = filtered_df.groupby('大分類')['費用'].sum(); fig1, ax1 = plt.subplots(); cost_by_equip.plot(kind='bar', ax=ax1, color='#2ecc71', edgecolor='black'); ax1.set_ylabel("費用 (円)"); ax1.set_xlabel("設備大分類"); ax1.grid(axis='y', linestyle='--', alpha=0.7); plt.xticks(rotation=45); plt.tight_layout(); st.pyplot(fig1)
        with c2:
            st.subheader("🔧 設備別・メンテナンス回数"); count_by_equip = filtered_df.groupby('大分類')['設備名'].count(); fig2, ax2 = plt.subplots(); count_by_equip.plot(kind='line', marker='o', ax=ax2, linewidth=2, color='#e74c3c', markersize=8); ax2.yaxis.set_major_locator(plt.MaxNLocator(integer=True)); ax2.set_ylabel("メンテナンス回数 (回)"); ax2.set_xlabel("設備大分類"); ax2.grid(True, linestyle='--', alpha=0.7); plt.xticks(rotation=45); plt.tight_layout(); st.pyplot(fig2)
    else: st.info("指定された条件に合致するデータがありません。")

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
                details = f"**作業内容:**\n\n{row['作業内容']}\n\n**備考:**\n\n{row['備考']}\n\n**費用:** {row['費用']:,} 円"
                v1.write(details)
                if row['使用部品'] and row['使用部品'] != '[]':
                    try:
                        parts_list = json.loads(row['使用部品'])
                        if parts_list:
                            parts_df = pd.DataFrame(parts_list); v1.write("**使用部品:**"); v1.dataframe(parts_df.style.format({"個数": "{:,}"}), use_container_width=True)
                    except (json.JSONDecodeError, TypeError): v1.write(f"**使用部品データエラー:** {row['使用部品']}")
                with v2:
                    i1, i2 = st.columns(2)
                    if len(str(row['画像'])) > 20: i1.image(base64.b64decode(row['画像']), caption="修理前")
                    if len(str(row['画像2'])) > 20: i2.image(base64.b64decode(row['画像2']), caption="修理後")
        
        if st.session_state["logged_in"]:
            st.markdown("---")
            st.subheader("🛠️ 履歴の修正・削除")
            label_to_index_map = {f"{row['最終点検日'].strftime('%Y-%m-%d')} | {row['設備名']} (記録ID: {index})": index for index, row in filtered_df.iterrows()}
            target_label = st.selectbox("修正・削除対象を選択", list(label_to_index_map.keys()), index=None, placeholder="修正したい履歴を選択してください")
            
            if target_label:
                idx_h = label_to_index_map[target_label]
                curr_h = df.loc[idx_h]

                with st.form("edit_h_form"):
                    st.write("#### メンテナンス記録の修正")
                    ca, cb = st.columns(2)
                    new_date = ca.date_input("作業日", curr_h["最終点検日"], key=f"edit_date_{idx_h}")
                    new_equip = ca.text_input("設備名", curr_h["設備名"], key=f"edit_equip_{idx_h}")
                    new_cost = ca.number_input("費用", value=int(curr_h["費用"]), key=f"edit_cost_{idx_h}")
                    new_note = cb.text_area("備考", curr_h["備考"], height=100, key=f"edit_note_{idx_h}")
                    new_desc = st.text_area("作業内容", curr_h["作業内容"], height=150, key=f"edit_desc_{idx_h}")
                    
                    st.write("#### 使用部品の修正")
                    try:
                        current_used_parts = json.loads(curr_h['使用部品']) if curr_h['使用部品'] and curr_h['使用部品'] != '[]' else []
                    except (json.JSONDecodeError, TypeError):
                        current_used_parts = []
                    
                    if f"edited_parts_{idx_h}" not in st.session_state:
                        st.session_state[f"edited_parts_{idx_h}"] = current_used_parts.copy()

                    edited_parts_list = st.session_state[f"edited_parts_{idx_h}"]
                    
                    for i, part in enumerate(edited_parts_list):
                        p_col1, p_col2, p_col3 = st.columns([3, 1, 1])
                        p_col1.text(f"部品: {part['部品名']}")
                        
                        original_qty = next((p['個数'] for p in current_used_parts if p['部品名'] == part['部品名']), 0)
                        current_stock = int(stock_df.loc[stock_df['部品名'] == part['部品名'], '在庫数'].iloc[0])
                        max_val = current_stock + original_qty
                        
                        new_qty = p_col2.number_input(f"個数 (現在庫: {current_stock})", value=part['個数'], min_value=1, max_value=max_val, step=1, key=f"edit_qty_{idx_h}_{i}")
                        edited_parts_list[i]['個数'] = new_qty
                        if p_col3.button(f"削除", key=f"del_part_{idx_h}_{i}"):
                            edited_parts_list.pop(i)
                            st.rerun()

                    st.write("##### 新しい部品を追加")
                    all_parts = stock_df['部品名'].tolist()
                    part_to_add = st.selectbox("在庫から部品を選択", ["-"] + all_parts, key=f"add_part_select_{idx_h}")
                    if st.button("部品を追加", key=f"add_part_btn_{idx_h}") and part_to_add != "-":
                        if not any(p['部品名'] == part_to_add for p in edited_parts_list):
                            edited_parts_list.append({'部品名': part_to_add, '個数': 1})
                            st.rerun()
                    
                    st.markdown("---")
                    up_f1 = st.file_uploader("修理前を更新", type=['jpg','jpeg','png'], key=f"up_f1_{idx_h}")
                    up_f2 = st.file_uploader("修理後を更新", type=['jpg','jpeg','png'], key=f"up_f2_{idx_h}")

                    if st.form_submit_button("✔️ 修正を保存"):
                        with st.spinner("データを更新しています..."):
                            temp_stock = update_stock(stock_df, current_used_parts, operation='add')
                            final_stock = update_stock(temp_stock, edited_parts_list, operation='subtract')

                            img_b1, img_b2 = image_to_base64(up_f1), image_to_base64(up_f2)
                            if img_b1: df.loc[idx_h, "画像"] = img_b1
                            if img_b2: df.loc[idx_h, "画像2"] = img_b2
                            match = re.search(r'\[(.*?)\]', new_equip)
                            new_category = match.group(1) if match else "その他"
                            df.loc[idx_h, ["最終点検日", "設備名", "作業内容", "備考", "費用", "大分類", "使用部品"]] = \
                                [pd.to_datetime(new_date), new_equip, new_desc, new_note, new_cost, new_category, json.dumps(edited_parts_list, ensure_ascii=False)]
                            
                            conn.update(worksheet="maintenance_data", data=df)
                            conn.update(worksheet="stock_data", data=final_stock)

                        del st.session_state[f"edited_parts_{idx_h}"]
                        st.toast("✅ 修正が完了しました。"); time.sleep(1); st.rerun()

                if st.button("🚨 この履歴を削除", key=f"delete_button_{idx_h}"):
                    with st.spinner("データを削除し、在庫を更新中..."):
                        record_to_delete = df.loc[idx_h]
                        try:
                            used_parts = json.loads(record_to_delete['使用部品']) if record_to_delete['使用部品'] and record_to_delete['使用部品'] != '[]' else []
                            final_stock = update_stock(stock_df, used_parts, operation='add')
                            conn.update(worksheet="stock_data", data=final_stock)
                            conn.update(worksheet="maintenance_data", data=df.drop(idx_h))
                            st.toast("🗑️ 削除と在庫の更新が完了しました。")
                        except Exception as e:
                            st.error(f"削除処理中にエラーが発生しました: {e}")
                    time.sleep(1); st.rerun()

    else:
        st.info("指定された条件に合致する履歴データがありません。")

# 📦 在庫管理 (変更なし)
elif st.session_state.active_tab == "📦 在庫管理" and st.session_state["logged_in"]:
    st.header("📦 部品在庫管理")
    if not stock_df.empty:
        low_stock_parts = stock_df[stock_df['在庫数'] <= stock_df['発注点']]; 
        if not low_stock_parts.empty: st.warning("以下の部品の在庫が発注点を下回っています。"); st.dataframe(low_stock_parts[['分類', '部品名', '在庫数', '発注点']], use_container_width=True)
        all_stock_cats = sorted(stock_df["分類"].unique().tolist()); selected_stock_cats = st.multiselect("分類で絞り込み", options=all_stock_cats, default=all_stock_cats)
        if selected_stock_cats: st.dataframe(stock_df[stock_df["分類"].isin(selected_stock_cats)].reset_index(drop=True), use_container_width=True)
        else: st.info("分類を選択してください。")
    else: st.info("在庫データがありません。")
    with st.expander("➕ 新しい部品を登録する"):
        with st.form("new_stock", clear_on_submit=True):
            n_cat = st.selectbox("分類", categories, key="new_s_cat"); n_name = st.text_input("部品名"); n_qty = st.number_input("在庫数", min_value=0, step=1); n_price = st.number_input("単価", min_value=0, step=1); n_order_point = st.number_input("発注点", min_value=0, step=1, value=5)
            if st.form_submit_button("登録"):
                with st.spinner("データを登録中..."):
                    new_row = pd.DataFrame([{"分類": n_cat, "部品名": n_name, "在庫数": n_qty, "単価": n_price, "発注点": n_order_point, "最終更新日": datetime.now().strftime('%Y-%m-%d')}]); updated_stock_df = pd.concat([stock_df, new_row], ignore_index=True); conn.update(worksheet="stock_data", data=updated_stock_df)
                st.toast("✅ 登録が完了しました。"); time.sleep(1); st.rerun()
    st.markdown("---")
    st.subheader("🛠️ 在庫の修正・削除")
    if not stock_df.empty:
        s_cat_sel = st.selectbox("分類を選択", sorted(stock_df["分類"].unique().tolist()), key="s_cat_edit"); f_items = stock_df[stock_df["分類"] == s_cat_sel]
        if not f_items.empty:
            t_item = st.selectbox("部品を選択", f_items["部品名"].tolist());
            if t_item:
                s_idx = stock_df[(stock_df["部品名"] == t_item) & (stock_df["分類"] == s_cat_sel)].index[0]
                with st.form("edit_stk"):
                    eq = st.number_input("在庫数", value=int(stock_df.loc[s_idx, "在庫数"]), min_value=0, step=1); ep = st.number_input("単価", value=int(stock_df.loc[s_idx, "単価"]), min_value=0, step=1); eo = st.number_input("発注点", value=int(stock_df.loc[s_idx, "発注点"]), min_value=0, step=1)
                    if st.form_submit_button("在庫情報を更新"):
                        with st.spinner("データを更新中..."): stock_df.loc[s_idx, ["在庫数", "単価", "発注点", "最終更新日"]] = [eq, ep, eo, datetime.now().strftime('%Y-%m-%d')]; conn.update(worksheet="stock_data", data=stock_df)
                        st.toast("✅ 更新が完了しました。"); time.sleep(1); st.rerun()
                if st.button(f"🗑️ 「{t_item}」を削除"):
                    with st.spinner("データを削除中..."): conn.update(worksheet="stock_data", data=stock_df.drop(s_idx))
                    st.toast("🗑️ 削除が完了しました。"); time.sleep(1); st.rerun()
    else: st.info("修正・削除対象の在庫データがありません。")

# 📝 メンテナンス登録
elif st.session_state.active_tab == "📝 メンテナンス登録" and st.session_state["logged_in"]:
    st.header("📝 メンテナンス記録の入力")
    with st.form("main_reg", clear_on_submit=True):
        c1, c2 = st.columns(2)
        en = c1.selectbox("分類", categories, key="reg_cat"); ed = c1.text_input("機番・名称"); wt = c2.date_input("作業日", datetime.today()); wc = c2.number_input("費用", min_value=0, step=1); wd = st.text_area("作業内容", height=150); wn = st.text_area("備考", height=100)
        st.markdown("---")
        st.subheader("🔩 使用部品の登録")
        if not stock_df.empty:
            if 'temp_used_parts' not in st.session_state: st.session_state.temp_used_parts = []
            
            part_col1, part_col2 = st.columns([2,1])
            available_parts_reg = stock_df[stock_df['在庫数'] > 0]['部品名'].tolist()
            part_to_add_reg = part_col1.selectbox("在庫から使用した部品を選択", ["-"] + available_parts_reg, key="reg_part_select")
            if part_col2.button("部品を追加", use_container_width=True) and part_to_add_reg != "-":
                if not any(p['部品名'] == part_to_add_reg for p in st.session_state.temp_used_parts):
                    st.session_state.temp_used_parts.append({'部品名': part_to_add_reg, '個数': 1})
                st.rerun()
            
            used_parts_details_input = []
            for i, part in enumerate(st.session_state.temp_used_parts):
                up_c1, up_c2, up_c3 = st.columns([2,1,1])
                up_c1.text(f"部品: {part['部品名']}")
                current_stock = int(stock_df.loc[stock_df['部品名'] == part['部品名'], '在庫数'].iloc[0])
                qty = up_c2.number_input(f"使用個数 (在庫:{current_stock})", min_value=1, max_value=current_stock, step=1, key=f"reg_qty_{i}")
                if up_c3.button(f"削除", key=f"reg_del_{i}", use_container_width=True):
                    st.session_state.temp_used_parts.pop(i)
                    st.rerun()
                used_parts_details_input.append({"部品名": part['部品名'], "個数": qty})

        else: st.info("登録されている在庫部品がありません。"); used_parts_details_input = []
        st.markdown("---")
        up1 = st.file_uploader("修理前をアップロード", type=['jpg','jpeg','png']); up2 = st.file_uploader("修理後をアップロード", type=['jpg','jpeg','png'])
        if st.form_submit_button("記録を保存"):
            with st.spinner("データと在庫を更新中..."):
                final_stock = update_stock(stock_df, used_parts_details_input, operation='subtract')
                conn.update(worksheet="stock_data", data=final_stock)
                b1, b2 = image_to_base64(up1), image_to_base64(up2); used_parts_json = json.dumps(used_parts_details_input, ensure_ascii=False) if used_parts_details_input else '[]'
                new_record = pd.DataFrame([{"設備名": f"[{en}] {ed}", "最終点検日": pd.to_datetime(wt), "作業内容": wd, "費用": wc, "備考": wn, "画像": b1 or "", "画像2": b2 or "", "使用部品": used_parts_json}])
                df_to_save = df.drop(columns=['大分類'], errors='ignore'); updated_df = pd.concat([df_to_save, new_record], ignore_index=True); conn.update(worksheet="maintenance_data", data=updated_df)
            del st.session_state.temp_used_parts
            st.success("✅ 保存と在庫の更新が完了しました！"); time.sleep(1); st.rerun()
