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
    df = conn.read(worksheet="maintenance_data", ttl="1s")
    stock = conn.read(worksheet="stock_data", ttl="1s")
    return df, stock

df, stock_df = load_data()

# 必須列の初期化（画像列を念のため空文字へ）
if '画像' not in df.columns:
    df['画像'] = ""
df['画像'] = df['画像'].fillna("").astype(str).replace(['0', '0.0', 'nan'], "")

# --- 画像処理関数（圧縮強化版） ---
def process_images(uploaded_files):
    """複数画像を圧縮して一つの文字列に結合する"""
    if not uploaded_files:
        return None
    
    encoded_list = []
    # 複数ファイルに対応（最大3枚程度を推奨）
    for uploaded_file in uploaded_files[:3]:
        img = Image.open(uploaded_file)
        # 制限回避のためサイズをさらに縮小 (400px)
        img.thumbnail((400, 400)) 
        # RGBに変換してファイルサイズ削減
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        buffered = io.BytesIO()
        # 画質(quality)を50に落としてファイルサイズを大幅カット
        img.save(buffered, format="JPEG", quality=50, optimize=True)
        encoded_str = base64.b64encode(buffered.getvalue()).decode()
        encoded_list.append(encoded_str)
    
    # 画像同士を '|||' で区切って一つの文字列にする
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
# 📁 2. 過去履歴（複数画像表示対応）
# ================================================================
with tabs[1]:
    set_tab(1)
    st.header("📁 過去履歴（複数写真対応）")
    
    for i, row in df.sort_values(by="最終点検日", ascending=False).iterrows():
        with st.expander(f"{row['最終点検日'].strftime('%Y-%m-%d')} | {row['設備名']}"):
            c1, c2 = st.columns([1, 1])
            with c1:
                st.write(f"**内容:** {row['作業内容']}")
                st.write(f"**費用:** {row['費用']:,} 円")
                st.write(f"**備考:** {row['備考']}")
            with c2:
                img_bundle = str(row.get('画像', ""))
                if len(img_bundle) > 50:
                    imgs = img_bundle.split("|||")
                    cols = st.columns(len(imgs))
                    for idx, img_data in enumerate(imgs):
                        try:
                            cols[idx].image(base64.b64decode(img_data), use_container_width=True)
                        except:
                            st.error("画像表示エラー")
                else:
                    st.info("写真なし")

    st.markdown("---")
    st.subheader("🛠️ 履歴の修正・写真の追加（最大3枚）")
    if not df.empty:
        df['label'] = df['最終点検日'].dt.strftime('%Y-%m-%d') + " | " + df['設備名']
        target_h = st.selectbox("修正対象を選択", df['label'].tolist())
        idx_h = df[df['label'] == target_h].index[0]
        curr_h = df.iloc[idx_h]
        
        with st.form("edit_h_new"):
            col_ea, col_eb = st.columns(2)
            with col_ea:
                new_date = st.date_input("作業日", curr_h["最終点検日"])
                new_equip = st.text_input("設備名", curr_h["設備名"])
                new_cost = st.number_input("費用", value=int(curr_h["費用"]))
            with col_eb:
                new_note = st.text_area("備考", curr_h["備考"])
                new_files = st.file_uploader("写真を入れ替える(最大3枚)", type=['jpg','jpeg','png'], accept_multiple_files=True)
            
            new_desc = st.text_area("作業内容", curr_h["作業内容"])
            
            if st.form_submit_button("修正保存"):
                img_b = process_images(new_files)
                if img_b:
                    df.loc[idx_h, "画像"] = img_b # 写真が選ばれた時のみ上書き
                
                df.loc[idx_h, ["最終点検日", "設備名", "作業内容", "備考", "費用"]] = [
                    pd.to_datetime(new_date), new_equip, new_desc, new_note, new_cost
                ]
                conn.update(worksheet="maintenance_data", data=df.drop(columns=['label'], errors='ignore'))
                st.rerun()

# ================================================================
# 📝 4. メンテナンス登録（複数写真アップロード）
# ================================================================
with tabs[3]:
    set_tab(3)
    st.header("📝 メンテナンス記録の入力")
    with st.form("reg_new", clear_on_submit=True):
        en, ed = st.selectbox("対象設備", categories[1:]), st.text_input("機番・詳細名称")
        wd, wt = st.text_area("作業内容"), st.date_input("作業日", datetime.today())
        wc, wn = st.number_input("費用", min_value=0), st.text_area("備考")
        # 複数ファイル選択を有効化
        up_files = st.file_uploader("現場写真 (最大3枚まで)", type=['jpg','jpeg','png'], accept_multiple_files=True)
        
        if st.form_submit_button("保存"):
            img_b = process_images(up_files) if up_files else ""
            new_r = pd.DataFrame([{"設備名": f"[{en}] {ed}", "最終点検日": wt.strftime('%Y-%m-%d'), "作業内容": wd, "費用": wc, "備考": wn, "画像": img_b}])
            conn.update(worksheet="maintenance_data", data=pd.concat([df.drop(columns=['label'], errors='ignore'), new_r], ignore_index=True))
            st.rerun()
