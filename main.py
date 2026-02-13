import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import japanize_matplotlib
from streamlit_gsheets import GSheetsConnection
import base64
from PIL import Image
import io

# --- ページ設定 ---
st.set_page_config(page_title="設備メンテナンス管理", layout="wide")

# ---------- データ読み込み ----------
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    # スプレッドシートからデータを強制的に最新で読み込む
    df = conn.read(worksheet="maintenance_data", ttl="0")
    stock = conn.read(worksheet="stock_data", ttl="0")
    return df, stock

df, stock_df = load_data()

# --- 列名の安全確認と自動修復 ---
# 期待する列名リスト
required_columns = ['設備名', '最終点検日', '作業内容', '費用', '備考', '画像']

# もし読み込んだデータの列名が足りない、またはズレている場合の対策
if not df.empty:
    # 読み込んだデータの列名が意図したものと違う場合、1行目を列名として再設定を試みる
    if '最終点検日' not in df.columns:
        st.error("スプレッドシートの列名『最終点検日』が見つかりません。列名を自動調整します。")
        # 列名がズレている可能性を考慮し、空のデータフレームで列だけ作成
        for col in required_columns:
            if col not in df.columns:
                df[col] = ""

# 必須列の初期化（画像列と日付列を特にケア）
if '画像' not in df.columns: df['画像'] = ""
df['画像'] = df['画像'].fillna("").astype(str).replace(['0', '0.0', 'nan'], "")

if '最終点検日' not in df.columns:
    df['最終点検日'] = datetime.today().strftime('%Y-%m-%d')

# 日付型に変換（エラーが出ても止まらないようにする）
df['最終点検日'] = pd.to_datetime(df['最終点検日'], errors='coerce')
# NaT (日付変換エラー) を今日の日付で埋める
df['最終点検日'] = df['最終点検日'].fillna(pd.Timestamp(datetime.today()))

# --- 画像処理関数（圧縮） ---
def process_images(uploaded_files):
    if not uploaded_files: return None
    encoded_list = []
    for uploaded_file in uploaded_files[:3]:
        img = Image.open(uploaded_file)
        img.thumbnail((400, 400)) 
        if img.mode != 'RGB': img = img.convert('RGB')
        buffered = io.BytesIO()
        img.save(buffered, format="JPEG", quality=50, optimize=True)
        encoded_list.append(base64.b64encode(buffered.getvalue()).decode())
    return "|||".join(encoded_list)

# --- タブ状態管理 ---
query_params = st.query_params
default_tab = int(query_params.get("tab", 1))
tab_titles = ["📊 ダッシュボード", "📁 過去履歴", "📦 在庫管理", "📝 メンテナンス登録"]
tabs = st.tabs(tab_titles)

def set_tab(index):
    st.query_params["tab"] = index

categories = ["すべて", "ジョークラッシャ", "インパクトクラッシャー", "スクリーン", "ベルト", "その他"]

# ================================================================
# 📁 2. 過去履歴 (KeyError対策済み)
# ================================================================
with tabs[1]:
    set_tab(1)
    st.header("📁 過去履歴")
    
    if not df.empty:
        # sort_valuesでエラーが出ないよう、確実に存在する列でソート
        display_df = df.copy()
        try:
            display_df = display_df.sort_values(by="最終点検日", ascending=False)
        except:
            pass # ソートに失敗しても表示は続ける

        for i, row in display_df.iterrows():
            # 表示名が空の場合の対策
            equip_name = row['設備名'] if pd.notnull(row['設備名']) else "不明な設備"
            date_str = row['最終点検日'].strftime('%Y-%m-%d') if pd.notnull(row['最終点検日']) else "日付不明"
            
            with st.expander(f"{date_str} | {equip_name}"):
                c1, c2 = st.columns([1, 1])
                with c1:
                    st.write(f"**内容:** {row.get('作業内容', '')}")
                    st.write(f"**費用:** {row.get('費用', 0):,} 円")
                    st.write(f"**備考:** {row.get('備考', '')}")
                with c2:
                    img_bundle = str(row.get('画像', ""))
                    if len(img_bundle) > 50:
                        imgs = img_bundle.split("|||")
                        cols = st.columns(len(imgs))
                        for idx, img_data in enumerate(imgs):
                            try:
                                cols[idx].image(base64.b64decode(img_data), use_container_width=True)
                            except:
                                pass
                    else:
                        st.info("写真なし")
    else:
        st.info("履歴がありません。")

    # --- 修正・削除フォーム (ここでも列チェック) ---
    st.markdown("---")
    st.subheader("🛠️ 履歴の修正・削除")
    if not df.empty and '最終点検日' in df.columns:
        df['label'] = df['最終点検日'].dt.strftime('%Y-%m-%d') + " | " + df['設備名'].astype(str)
        target_h = st.selectbox("修正対象を選択", df['label'].tolist())
        idx_h = df[df['label'] == target_h].index[0]
        curr_h = df.iloc[idx_h]
        
        with st.form("edit_h_safe"):
            col_ea, col_eb = st.columns(2)
            with col_ea:
                new_date = st.date_input("作業日", curr_h["最終点検日"])
                new_equip = st.text_input("設備名", curr_h["設備名"])
                new_cost = st.number_input("費用", value=int(curr_h["費用"]) if pd.notnull(curr_h["費用"]) else 0)
            with col_eb:
                new_note = st.text_area("備考", curr_h["備考"])
                new_files = st.file_uploader("写真を入れ替える(最大3枚)", type=['jpg','jpeg','png'], accept_multiple_files=True)
            
            new_desc = st.text_area("作業内容", curr_h["作業内容"])
            
            if st.form_submit_button("修正保存"):
                img_b = process_images(new_files)
                if img_b: df.loc[idx_h, "画像"] = img_b
                
                df.loc[idx_h, ["最終点検日", "設備名", "作業内容", "備考", "費用"]] = [
                    pd.to_datetime(new_date), new_equip, new_desc, new_note, new_cost
                ]
                conn.update(worksheet="maintenance_data", data=df.drop(columns=['label'], errors='ignore'))
                st.rerun()
