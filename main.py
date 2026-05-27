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
                st.session_state["logged_in"] = True; st.query_params["auth"] = "success"; st.rerun()
            else: st.error("認証に失敗しました。")
    else:
        st.success("✅ 編集モード：有効")
        if st.button("ログアウト"):
            for key in list(st.session_state.keys()): del st.session_state[key]
            st.query_params.clear(); st.rerun()

# --- 3. データ読み込み ---
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=5)
def load_data_from_sheets(_conn):
    try:
        df = _conn.read(worksheet="maintenance_data"); stock = _conn.read(worksheet="stock_data")
        return df, stock
    except Exception as e:
        st.error(f"Google Sheetsへの接続エラー: {e}")
        st.info("APIの利用制限に達しているか、シート名が間違っている可能性があります。")
        return pd.DataFrame(), pd.DataFrame()

df_raw, stock_df_raw = load_data_from_sheets(conn)

if df_raw.empty and stock_df_raw.empty:
    st.warning("データの読み込みに失敗しました。設定を確認後、ページを再読み込みしてください。"); st.stop()

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

for col in ['画像', '画像2']: df[col] = df[col].fillna("").astype(str)
df['使用部品'] = df['使用部品'].fillna('[]').astype(str)
df['最終点検日'] = pd.to_datetime(df['最終点検日'], errors='coerce')
df['費用'] = pd.to_numeric(df['費用'], errors='coerce').fillna(0).astype(int)
for col in ['在庫数', '単価', '発注点']:
    stock_df[col] = pd.to_numeric(stock_df[col], errors='coerce').fillna(0).astype(int)

df['大分類'] = df['設備名'].str.extract(r'\[(.*?)\]')[0].fillna("その他")
categories = ["ジョークラッシャ", "インパクトクラッシャー", "スクリーン", "ベルト", "その他"]

# --- 5. 画像圧縮関数 ---
def image_to_base64(uploaded_file):
    if uploaded_file:
        try:
            img = Image.open(uploaded_file); img.thumbnail((400, 400))
            if img.mode != 'RGB': img = img.convert('RGB')
            buf = io.BytesIO(); img.save(buf, format="JPEG", quality=60, optimize=True)
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
    # (変更なし)
    st.markdown("---"); st.subheader("絞り込み条件")
    if df_to_filter.empty: st.info("フィルタリング対象のデータがありません。"); return pd.DataFrame()
    f1, f2 = st.columns(2)
    min_date = df_to_filter['最終点検日'].min().date(); max_date = df_to_filter['最終点検日'].max().date()
    start_date = f1.date_input('開始日', min_date, min_value=min_date, max_value=max_date, key="start_date")
    end_date = f1.date_input('終了日', max_date, min_value=min_date, max_value=max_date, key="end_date")
    unique_categories_in_data = sorted(df_to_filter['大分類'].unique().tolist())
    selected_categories = f2.multiselect('設備分類で絞り込み', options=unique_categories_in_data, default=unique_categories_in_data, key="cat_filter")
    if start_date > end_date: st.error('エラー: 終了日は開始日以降に設定してください。'); return pd.DataFrame()
    filtered = df_to_filter[(df_to_filter['最終点検日'].dt.date >= start_date) & (df_to_filter['最終点検日'].dt.date <= end_date) & (df_to_filter['大分類'].isin(selected_categories))]
    st.markdown("---")
    return filtered

def update_stock(stock_df, parts_list, operation='subtract'):
    # (変更なし)
    temp_stock = stock_df.copy()
    for part in parts_list:
        part_name = part.get('部品名'); qty = part.get('個数', 0)
        stock_idx_list = temp_stock[temp_stock['部品名'] == part_name].index
        if not stock_idx_list.empty:
            stock_idx = stock_idx_list[0]
            if operation == 'subtract': temp_stock.loc[stock_idx, '在庫数'] -= qty
            elif operation == 'add': temp_stock.loc[stock_idx, '在庫数'] += qty
            temp_stock.loc[stock_idx, '最終更新日'] = datetime.now().strftime('%Y-%m-%d')
    return temp_stock

# 📊 ダッシュボード (変更なし)
if st.session_state.active_tab == "📊 ダッシュボード":
    # ...

# 📁 過去履歴
elif st.session_state.active_tab == "📁 過去履歴":
    st.header("📁 メンテナンス過去履歴"); filtered_df = get_filtered_data(df_main)
    if not filtered_df.empty:
        sorted_df = filtered_df.sort_values(by="最終点検日", ascending=False)
        for i, row in sorted_df.iterrows():
            # ... (表示部分は変更なし) ...
            expander_title = f"{row['最終点検日'].strftime('%Y-%m-%d')} | {row['設備名']}"
            with st.expander(expander_title):
                v1, v2 = st.columns([2, 1]); details = f"**作業内容:**\n\n{row['作業内容']}\n\n**備考:**\n\n{str(row['備考'])}\n\n**費用:** {row['費用']:,} 円"; v1.write(details)
                if row['使用部品'] and row['使用部品'] != '[]':
                    try:
                        parts_list = json.loads(row['使用部品'])
                        if parts_list: parts_df = pd.DataFrame(parts_list); v1.write("**使用部品:**"); v1.dataframe(parts_df.style.format({"個数": "{:,}"}), use_container_width=True)
                    except (json.JSONDecodeError, TypeError): v1.write(f"**使用部品データエラー:** {row['使用部品']}")
                with v2:
                    i1, i2 = st.columns(2)
                    if len(str(row['画像'])) > 20: i1.image(base64.b64decode(row['画像']), caption="修理前")
                    if len(str(row['画像2'])) > 20: i2.image(base64.b64decode(row['画像2']), caption="修理後")
        
        if st.session_state.get("logged_in"):
            st.markdown("---"); st.subheader("🛠️ 履歴の修正・削除")
            label_to_index_map = {f"{row['最終点検日'].strftime('%Y-%m-%d')} | {row['設備名']} (記録ID: {index})": index for index, row in filtered_df.iterrows()}
            
            # 選択されたレコードのインデックスを管理
            if 'selected_idx_for_edit' not in st.session_state: st.session_state.selected_idx_for_edit = None
            
            def clear_edit_state():
                st.session_state.selected_idx_for_edit = None
                # 他の編集関連のsession_stateもクリア
                for key in [k for k in st.session_state if 'edited_parts_' in k]:
                    del st.session_state[key]
            
            selected_label = st.selectbox("修正・削除対象を選択", list(label_to_index_map.keys()), index=None, placeholder="修正したい履歴を選択してください", on_change=clear_edit_state, key='edit_selectbox')
            
            if selected_label:
                st.session_state.selected_idx_for_edit = label_to_index_map.get(selected_label)

            idx_h = st.session_state.selected_idx_for_edit
            
            if idx_h is not None:
                curr_h = df.loc[idx_h]
                
                # --- ### 修正箇所 START (過去履歴) ### ---
                try:
                    original_used_parts = json.loads(curr_h['使用部品']) if curr_h['使用部品'] and curr_h['使用部品'] != '[]' else []
                except (json.JSONDecodeError, TypeError):
                    original_used_parts = []
                
                # 部品編集リストをセッションで管理
                session_key_parts = f"edited_parts_{idx_h}"
                if session_key_parts not in st.session_state:
                    st.session_state[session_key_parts] = original_used_parts.copy()
                
                st.write("#### 使用部品の修正")
                # 部品追加UI
                add_col1, add_col2 = st.columns([3, 1])
                all_parts = stock_df['部品名'].tolist()
                part_to_add = add_col1.selectbox("新しい部品を追加", ["-"] + all_parts, key=f"add_part_select_{idx_h}")
                if add_col2.button("部品を追加", key=f"add_part_btn_{idx_h}"):
                    if part_to_add != "-" and not any(p['部品名'] == part_to_add for p in st.session_state[session_key_parts]):
                        st.session_state[session_key_parts].append({'部品名': part_to_add, '個数': 1})
                        st.rerun()
                
                # フォーム開始
                with st.form("edit_h_form"):
                    st.write("#### メンテナンス記録の修正")
                    ca, cb = st.columns(2)
                    new_date = ca.date_input("作業日", curr_h["最終点検日"])
                    new_equip = ca.text_input("設備名", curr_h["設備名"])
                    new_cost = ca.number_input("費用", value=int(curr_h["費用"]))
                    new_note = cb.text_area("備考", str(curr_h["備考"]), height=100)
                    new_desc = st.text_area("作業内容", curr_h["作業内容"], height=150)
                    
                    st.markdown("---")
                    st.write("登録されている部品リスト")
                    
                    # フォーム内で個数を入力
                    final_parts_list = []
                    for i, part in enumerate(st.session_state[session_key_parts]):
                        p_col1, p_col2 = st.columns([3, 1])
                        p_col1.text(f"部品: {part['部品名']}")
                        qty = p_col2.number_input("個数", value=part['個数'], min_value=1, step=1, key=f"form_edit_qty_{idx_h}_{i}")
                        final_parts_list.append({'部品名': part['部品名'], '個数': qty})
                    
                    up_f1 = st.file_uploader("修理前を更新", type=['jpg','jpeg','png'], key=f"up_f1_{idx_h}")
                    up_f2 = st.file_uploader("修理後を更新", type=['jpg','jpeg','png'], key=f"up_f2_{idx_h}")

                    submitted = st.form_submit_button("✔️ 修正を保存")
                    if submitted:
                        with st.spinner("データを更新しています..."):
                            # 1. 在庫を元に戻す
                            temp_stock = update_stock(stock_df, original_used_parts, operation='add')
                            # 2. フォームから収集した最新の部品リストで在庫を再度引き落とす
                            final_stock = update_stock(temp_stock, final_parts_list, operation='subtract')
                            
                            img_b1, img_b2 = image_to_base64(up_f1), image_to_base64(up_f2)
                            if img_b1: df.loc[idx_h, "画像"] = img_b1
                            if img_b2: df.loc[idx_h, "画像2"] = img_b2
                            match = re.search(r'\[(.*?)\]', new_equip)
                            new_category = match.group(1) if match else "その他"
                            df.loc[idx_h, ["最終点検日", "設備名", "作業内容", "備考", "費用", "大分類", "使用部品"]] = \
                                [pd.to_datetime(new_date), new_equip, new_desc, new_note, new_cost, new_category, json.dumps(final_parts_list, ensure_ascii=False)]
                            
                            conn.update(worksheet="maintenance_data", data=df); conn.update(worksheet="stock_data", data=final_stock)
                        
                        clear_edit_state()
                        st.toast("✅ 修正が完了しました。"); time.sleep(1); st.rerun()

                if st.button("🚨 この履歴を削除", key=f"delete_button_{idx_h}"):
                    # ... 削除ロジック (変更なし) ...
            # --- ### 修正箇所 END (過去履歴) ### ---

# 📦 在庫管理
elif st.session_state.active_tab == "📦 在庫管理" and st.session_state.get("logged_in"):
    # (変更なし)

# 📝 メンテナンス登録
elif st.session_state.active_tab == "📝 メンテナンス登録" and st.session_state.get("logged_in"):
    st.header("📝 メンテナンス記録の入力")
    
    # --- ### 修正箇所 START (メンテナンス登録) ### ---
    if 'reg_parts_list' not in st.session_state:
        st.session_state.reg_parts_list = []

    st.subheader("🔩 使用部品の登録")
    part_col1, part_col2 = st.columns([3,1])
    available_parts_reg = stock_df[stock_df['在庫数'] > 0]['部品名'].tolist()
    part_to_add_reg = part_col1.selectbox("在庫から使用した部品を選択", ["-"] + available_parts_reg, key="reg_part_select")
    
    if part_col2.button("部品を追加", use_container_width=True):
        if part_to_add_reg != "-" and not any(p['部品名'] == part_to_add_reg for p in st.session_state.reg_parts_list):
            st.session_state.reg_parts_list.append({'部品名': part_to_add_reg, '個数': 1})
            st.rerun()
    
    with st.form("main_reg"):
        st.write("#### 基本情報")
        c1, c2 = st.columns(2)
        en = c1.selectbox("分類", categories, key="reg_cat")
        ed = c1.text_input("機番・名称")
        wt = c2.date_input("作業日", datetime.today())
        wc = c2.number_input("費用", min_value=0, step=1)
        wd = st.text_area("作業内容", height=150)
        wn = st.text_area("備考", height=100)
        
        st.markdown("---")
        st.write("#### 登録する部品リスト")
        
        final_reg_parts = []
        for i, part in enumerate(st.session_state.reg_parts_list):
            up_c1, up_c2, up_c3 = st.columns([2,1,1])
            up_c1.text(f"部品: {part['部品名']}")
            current_stock = int(stock_df.loc[stock_df['部品名'] == part['部品名'], '在庫数'].iloc[0])
            qty = up_c2.number_input(f"使用個数 (在庫:{current_stock})", min_value=1, max_value=current_stock, step=1, key=f"reg_qty_{i}")
            # ここでは削除ボタンを置かず、リストの管理はフォームの外で行う
            final_reg_parts.append({"部品名": part['部品名'], "個数": qty})

        st.markdown("---")
        up1 = st.file_uploader("修理前をアップロード", type=['jpg','jpeg','png'])
        up2 = st.file_uploader("修理後をアップロード", type=['jpg','jpeg','png'])
        
        if st.form_submit_button("記録を保存"):
            with st.spinner("データと在庫を更新中..."):
                # フォーム送信時に収集した最新のリストで在庫を更新
                final_stock = update_stock(stock_df, final_reg_parts, operation='subtract')
                conn.update(worksheet="stock_data", data=final_stock)
                
                b1, b2 = image_to_base64(up1), image_to_base64(up2)
                used_parts_json = json.dumps(final_reg_parts, ensure_ascii=False) if final_reg_parts else '[]'
                
                new_record = pd.DataFrame([{"設備名": f"[{en}] {ed}", "最終点検日": pd.to_datetime(wt), "作業内容": wd, "費用": wc, "備考": wn, "画像": b1 or "", "画像2": b2 or "", "使用部品": used_parts_json}])
                df_to_save = df.drop(columns=['大分類'], errors='ignore')
                updated_df = pd.concat([df_to_save, new_record], ignore_index=True)
                conn.update(worksheet="maintenance_data", data=updated_df)
                
            del st.session_state.reg_parts_list
            st.success("✅ 保存と在庫の更新が完了しました！")
            time.sleep(1); st.rerun()
    # --- ### 修正箇所 END (メンテナンス登録) ### ---
# 📝 メンテナンス登録
elif st.session_state.active_tab == "📝 メンテナンス登録" and st.session_state["logged_in"]:
    st.header("📝 メンテナンス記録の入力")
    
    # 部品追加・削除のロジック (フォームの外側)
    if 'temp_used_parts' not in st.session_state: st.session_state.temp_used_parts = []
    
    st.subheader("🔩 使用部品の登録")
    part_col1, part_col2 = st.columns([3,1])
    available_parts_reg = stock_df[stock_df['在庫数'] > 0]['部品名'].tolist()
    part_to_add_reg = part_col1.selectbox("在庫から使用した部品を選択", ["-"] + available_parts_reg, key="reg_part_select")
    if part_col2.button("部品を追加", use_container_width=True):
        if part_to_add_reg != "-" and not any(p['部品名'] == part_to_add_reg for p in st.session_state.temp_used_parts):
            st.session_state.temp_used_parts.append({'部品名': part_to_add_reg, '個数': 1})
            st.rerun()

    # フォーム
    with st.form("main_reg", clear_on_submit=True):
        c1, c2 = st.columns(2)
        en = c1.selectbox("分類", categories, key="reg_cat"); ed = c1.text_input("機番・名称"); wt = c2.date_input("作業日", datetime.today()); wc = c2.number_input("費用", min_value=0, step=1); wd = st.text_area("作業内容", height=150); wn = st.text_area("備考", height=100)
        
        st.markdown("---")
        if st.session_state.temp_used_parts:
            st.write("登録する部品リスト:")
        
        used_parts_details_input = []
        for i, part in enumerate(st.session_state.temp_used_parts):
            up_c1, up_c2, up_c3 = st.columns([2,1,1])
            up_c1.text(f"部品: {part['部品名']}")
            current_stock = int(stock_df.loc[stock_df['部品名'] == part['部品名'], '在庫数'].iloc[0])
            qty = up_c2.number_input(f"使用個数 (在庫:{current_stock})", min_value=1, max_value=current_stock, step=1, key=f"reg_qty_{i}")
            # フォーム内なので削除ボタンはここには置けない
            used_parts_details_input.append({"部品名": part['部品名'], "個数": qty})

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
