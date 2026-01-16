import streamlit as st
from datetime import datetime
import pandas as pd
from PIL import Image
import os
import json
import re 
import time

# --- LIBRARY FIREBASE ---
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore

# --- KONFIGURASI HALAMAN ---
st.set_page_config(
    page_title="DompetKu", 
    page_icon="💸", 
    layout="centered",
    initial_sidebar_state="collapsed"
)

# --- CUSTOM CSS ---
st.markdown("""
<style>
    html, body, [class*="css"] {
        font-family: 'Sans-serif';
    }
    
    /* Tombol Utama */
    .stButton button {
        height: 55px;
        font-weight: bold;
        border-radius: 15px;
        transition: all 0.3s ease;
    }
    .stButton button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(0,0,0,0.2);
    }

    /* Kartu Metric */
    div[data-testid="stMetric"] {
        padding: 15px;
        border-radius: 10px;
        border: 1px solid rgba(128, 128, 128, 0.2);
        text-align: center;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    
    /* Judul */
    .main-title {
        font-size: 3rem;
        font-weight: 800;
        background: -webkit-linear-gradient(45deg, #FF4B4B, #FF914D);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        margin-bottom: 0px;
    }
    .sub-title {
        text-align: center;
        color: gray;
        margin-bottom: 30px;
        font-style: italic;
    }
</style>
""", unsafe_allow_html=True)

# --- KONEKSI KE FIREBASE ---
if not firebase_admin._apps:
    try:
        raw_key = st.secrets["firebase"]["textkey"]
        try:
            key_dict = json.loads(raw_key, strict=False)
        except json.JSONDecodeError:
            fixed_key = raw_key.replace('\n', ' ')
            key_dict = json.loads(fixed_key, strict=False)

        if "private_key" in key_dict:
            key_dict["private_key"] = key_dict["private_key"].replace("\\n", "\n")

        cred = credentials.Certificate(key_dict)
        firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error(f"Gagal login ke Firebase: {e}")
        st.stop()

db = firestore.client()

# --- FUNGSI CRUD ---
def load_data_firestore():
    try:
        docs = db.collection('transaksi').order_by('Tanggal', direction=firestore.Query.DESCENDING).stream()
        data = []
        for doc in docs:
            d = doc.to_dict()
            d['id'] = doc.id 
            data.append(d)
        return data
    except: return []

def tambah_data_firestore(data):
    db.collection('transaksi').add(data)

def hapus_data_firestore(doc_id):
    db.collection('transaksi').document(doc_id).delete()

def update_data_firestore(doc_id, data_baru):
    db.collection('transaksi').document(doc_id).update(data_baru)

# --- CEK OCR ---
OCR_AVAILABLE = False
try:
    import pytesseract
    OCR_AVAILABLE = True
except ImportError: pass

tesseract_found = False
if OCR_AVAILABLE and os.name == 'nt': 
    kemungkinan_path = [
        r'C:\Users\User\AppData\Local\Programs\Tesseract-OCR\tesseract.exe',
        os.path.expanduser(r'~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe'),
        r'C:\Program Files\Tesseract-OCR\tesseract.exe',               
        r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe', 
        os.path.join(os.getenv('LOCALAPPDATA', ''), r'Programs\Tesseract-OCR\tesseract.exe'),
        os.path.join(os.getenv('LOCALAPPDATA', ''), r'Tesseract-OCR\tesseract.exe')
    ]
    for path in kemungkinan_path:
        if os.path.exists(path):
            pytesseract.pytesseract.tesseract_cmd = path
            tesseract_found = True
            break

# --- INISIALISASI ---
if 'transaksi' not in st.session_state:
    st.session_state['transaksi'] = load_data_firestore()
    if not st.session_state['transaksi']: 
        st.session_state['transaksi'] = load_data_firestore()

if 'active_form' not in st.session_state:
    st.session_state['active_form'] = None 

# --- FUNGSI OCR (SMART KEYWORD SEARCH) ---
def proses_ocr(gambar):
    if not OCR_AVAILABLE: return 0
    if os.name == 'nt' and not tesseract_found: return 0
    try:
        # 1. Ambil semua teks dari gambar
        text = pytesseract.image_to_string(gambar)
        text_lower = text.lower()
        
        # 2. DEFINISI KATA KUNCI (Prioritas Utama)
        keywords = ['total', 'jumlah', 'bayar', 'grand total', 'amount', 'tagihan']
        
        for kw in keywords:
            if kw in text_lower:
                start_index = text_lower.find(kw)
                relevant_text = text_lower[start_index:]
                
                text_bersih = relevant_text.replace('.', '').replace(',', '')
                angka_ditemukan = re.findall(r'\d+', text_bersih)
                
                for n in angka_ditemukan:
                    if n.isdigit():
                        val = int(n)
                        if 1000 <= val <= 50000000:
                            return val

        # 3. STRATEGI CADANGAN (Fallback)
        text_bersih = text.replace('.', '').replace(',', '')
        angka_ditemukan = re.findall(r'\d+', text_bersih)
        
        valid_numbers = []
        for n in angka_ditemukan:
            if n.isdigit():
                if len(n) > 8: 
                    continue
                val = int(n)
                if 1000 <= val <= 20000000:
                    valid_numbers.append(val)
        
        if valid_numbers:
            return max(valid_numbers)
            
    except: pass
    return 0

# --- FUNGSI HITUNG SALDO ---
def hitung_statistik():
    if not st.session_state['transaksi']: return 0, 0, 0
    masuk = sum(t['Nominal'] for t in st.session_state['transaksi'] if t['Jenis'] == 'Pemasukan')
    keluar = sum(t['Nominal'] for t in st.session_state['transaksi'] if t['Jenis'] == 'Pengeluaran')
    return masuk, keluar, masuk - keluar

# ==========================================
# UI DASHBOARD
# ==========================================

st.markdown('<h1 class="main-title">💸 DompetKu</h1>', unsafe_allow_html=True)
st.markdown('<p class="sub-title">Kelola keuanganmu dengan mudah & aman di Cloud</p>', unsafe_allow_html=True)

# 1. METRICS CARD
masuk, keluar, saldo = hitung_statistik()

col_m1, col_m2, col_m3 = st.columns(3)
col_m1.metric("💰 Sisa Saldo", f"Rp {saldo:,}")
col_m2.metric("📈 Pemasukan", f"Rp {masuk:,}")
col_m3.metric("📉 Pengeluaran", f"Rp {keluar:,}")

st.write("") 

# 2. TOMBOL AKSI UTAMA
c_btn1, c_btn2 = st.columns(2)
with c_btn1:
    if st.button("➕ PEMASUKAN", use_container_width=True, type="primary"):
        st.session_state['active_form'] = 'Pemasukan'
with c_btn2:
    if st.button("➖ PENGELUARAN", use_container_width=True):
        st.session_state['active_form'] = 'Pengeluaran'

# 3. FORM INPUT
if st.session_state['active_form']:
    jenis = st.session_state['active_form']
    header_color = "🟢" if jenis == "Pemasukan" else "🔴"
    
    st.markdown(f"### {header_color} Tambah {jenis}")
    
    with st.container(border=True):
        nom_awal = 0
        if jenis == "Pengeluaran" and OCR_AVAILABLE:
            # Checkbox Utama: Apakah mau pakai fitur scan?
            use_ocr_feature = st.checkbox("📸 Gunakan Scan Struk (Otomatis)")
            
            if use_ocr_feature:
                # Pilihan metode input gambar
                metode_scan = st.radio("Metode Scan:", ["📸 Kamera Langsung", "📂 Upload File"], horizontal=True)
                
                img_file = None
                
                if metode_scan == "📸 Kamera Langsung":
                    img_file = st.camera_input("Ambil Foto Struk")
                else:
                    img_file = st.file_uploader("Upload Foto Struk", type=['png', 'jpg', 'jpeg'])
                
                # Proses gambar jika ada file
                if img_file:
                    with st.spinner("Menganalisis gambar..."):
                        image_data = Image.open(img_file)
                        
                        if metode_scan == "📂 Upload File":
                            st.image(image_data, caption="Preview Struk", width=200)
                            
                        res = proses_ocr(image_data)
                    
                    if res > 0: 
                        st.success(f"Harga terdeteksi: Rp {res:,}")
                        nom_awal = res
                    else: 
                        st.warning("Gagal membaca harga otomatis. Silakan input manual.")

        with st.form("form_utama", border=False):
            c_in1, c_in2 = st.columns(2)
            nom = c_in1.number_input("Nominal (Rp)", min_value=0, value=nom_awal, step=5000)
            ket = c_in2.text_input("Keterangan", placeholder="Contoh: Beli Kopi")
            
            c_submit, c_space = st.columns([1, 2])
            
            if c_submit.form_submit_button("💾 SIMPAN DATA", use_container_width=True):
                if nom > 0:
                    baru = {
                        'Tanggal': datetime.now().strftime("%Y-%m-%d %H:%M"),
                        'Jenis': jenis,
                        'Nominal': nom,
                        'Keterangan': ket if ket else "-"
                    }
                    tambah_data_firestore(baru) 
                    
                    st.toast('✅ Data berhasil disimpan ke Cloud!', icon='☁️')
                    time.sleep(1)
                    st.session_state['transaksi'] = load_data_firestore()
                    st.session_state['active_form'] = None
                    st.rerun()
                else: st.error("Nominal tidak boleh nol!")
    
    if st.button("Batal / Tutup Form", use_container_width=True):
        st.session_state['active_form'] = None
        st.rerun()

st.markdown("---")

# 4. TABEL RIWAYAT
st.subheader("📝 Riwayat Transaksi")

if st.session_state['transaksi']:
    df = pd.DataFrame(st.session_state['transaksi'])
    if "Hapus" not in df.columns: df["Hapus"] = False
    
    cols_to_show = ["Hapus", "Tanggal", "Jenis", "Nominal", "Keterangan", "id"]
    for col in cols_to_show:
        if col not in df.columns: df[col] = ""

    edited_df = st.data_editor(
        df[cols_to_show], 
        use_container_width=True,
        column_config={
            "id": None, 
            "Hapus": st.column_config.CheckboxColumn("🗑️", width="small", default=False),
            "Nominal": st.column_config.NumberColumn("Nominal", format="Rp %d"),
            "Jenis": st.column_config.SelectboxColumn("Tipe", options=["Pemasukan", "Pengeluaran"], width="small"),
            "Tanggal": st.column_config.TextColumn("Waktu", disabled=True),
            "Keterangan": st.column_config.TextColumn("Keterangan", width="large")
        },
        hide_index=True, 
        num_rows="fixed"
    )

    # LOGIKA SIMPAN PERUBAHAN
    if edited_df["Hapus"].any():
        with st.spinner("Menghapus data..."):
            to_delete = edited_df[edited_df["Hapus"] == True]
            for index, row in to_delete.iterrows():
                hapus_data_firestore(row['id'])
            st.toast('Data berhasil dihapus!', icon='🗑️')
            time.sleep(0.5)
            st.session_state['transaksi'] = load_data_firestore()
            st.rerun()
    
    elif not edited_df["Hapus"].any():
        if st.button("⚠️ Simpan Perubahan Edit"):
            with st.spinner("Mengupdate data..."):
                for index, row in edited_df.iterrows():
                    update_data_firestore(row['id'], {
                        'Nominal': row['Nominal'],
                        'Keterangan': row['Keterangan'],
                        'Jenis': row['Jenis']
                    })
                st.toast('Perubahan berhasil disimpan!', icon='💾')
                time.sleep(0.5)
                st.session_state['transaksi'] = load_data_firestore()
                st.rerun()

else:
    st.info("👋 Belum ada data. Yuk mulai catat keuanganmu!")

# --- FOOTER ---
st.write("")
st.write("")
st.write("")

# Membuat kolom agar tombol reset mojok di kanan
col_spacer, col_reset = st.columns([3, 1])

with col_reset:
    with st.expander("💀 Reset Database"):
        st.warning("Semua data akan dihapus permanen!")
        konfirmasi_reset = st.checkbox("Saya Yakin")
        
        if st.button("HAPUS SEMUA", type="primary", use_container_width=True, disabled=not konfirmasi_reset):
            with st.spinner("Membersihkan database..."):
                for t in st.session_state['transaksi']:
                    hapus_data_firestore(t['id'])
                st.toast("Database bersih!", icon='✨')
                time.sleep(1)
                st.session_state['transaksi'] = []
                st.rerun()