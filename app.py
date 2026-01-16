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
    div[data-testid="stMetric"] {
        padding: 15px;
        border-radius: 10px;
        border: 1px solid rgba(128, 128, 128, 0.2);
        text-align: center;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
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

# --- FUNGSI OCR (VERSI "LOOKBEHIND") ---
def proses_ocr_lengkap(gambar):
    if not OCR_AVAILABLE: return 0, ""
    if os.name == 'nt' and not tesseract_found: return 0, ""
    
    total_found = 0
    items_found = []
    
    try:
        text = pytesseract.image_to_string(gambar)
        lines = text.split('\n')
        text_lower = text.lower()

        # 1. CARI TOTAL HARGA
        keywords_total = ['total', 'jumlah', 'bayar', 'tagihan', 'amount', 'grand']
        for kw in keywords_total:
            if kw in text_lower:
                idx = text_lower.find(kw)
                subtext = text_lower[idx:]
                nums = re.findall(r'\d+', subtext.replace('.', '').replace(',', ''))
                for n in nums:
                    val = int(n)
                    if 1000 <= val <= 50000000:
                        total_found = val
                        break
                if total_found: break
        
        if total_found == 0:
            nums = re.findall(r'\d+', text.replace('.', '').replace(',', ''))
            valid_nums = [int(n) for n in nums if n.isdigit() and 1000 <= int(n) <= 20000000 and len(n) <= 8]
            if valid_nums:
                total_found = max(valid_nums)

        # 2. CARI DETAIL ITEM (Logika Baru: Cek Baris Atasnya)
        ignore_words = ['total', 'tunai', 'kembali', 'change', 'cash', 'pajak', 'tax', 'diskon', 'telp', 'jl.', 'tanggal', 'date', 'subtotal', 'bayar', 'jumlah', 'no.', 'inv', 'pos', 'pembayaran']
        
        for i, line in enumerate(lines):
            line_clean = line.strip()
            line_lower = line_clean.lower()
            
            # Skip baris sampah
            if len(line_clean) < 3: continue
            if any(ign in line_lower for ign in ignore_words): continue
            
            # Cek apakah baris ini berakhiran ANGKA (Harga)
            match_price = re.search(r'((?:Rp\.?|Rp)?\s*[\d,.]+)$', line_clean)
            
            if match_price:
                # Ambil string harganya saja
                price_str = match_price.group(1).strip()
                # Cek validitas harga (harus ada digit)
                if not any(c.isdigit() for c in price_str): continue
                
                # AMBIL TEKS SEBELAH KIRI HARGA (Calon Nama)
                # Kita potong string berdasarkan posisi harga
                end_idx = line_clean.rfind(price_str)
                left_text = line_clean[:end_idx].strip()
                
                # Bersihkan simbol aneh di awal/akhir
                left_text = re.sub(r'^[^\w]+|[^\w]+$', '', left_text)
                
                final_name = ""
                qty_str = ""
                
                # CEK KASUS: Apakah teks kirinya CUMA angka/qty? (Misal: "1" atau "1 x")
                # Jika iya, berarti nama menunya ada di BARIS SEBELUMNYA (i-1)
                is_only_qty = re.match(r'^[\d\s\txX]+$', left_text)
                
                if is_only_qty or len(left_text) < 2:
                    if i > 0:
                        prev_line = lines[i-1].strip()
                        # Pastikan baris atasnya valid (bukan header/kosong)
                        if len(prev_line) > 3 and not any(ign in prev_line.lower() for ign in ignore_words):
                            # Pastikan baris atasnya TIDAK punya harga (biar ga double)
                            if not re.search(r'[\d,.]+$', prev_line):
                                final_name = prev_line
                                qty_str = left_text # Anggap left text skrg adalah Qty
                else:
                    # Nama menu ada di baris yang sama
                    final_name = left_text
                
                # FORMATTING HASIL
                if final_name:
                    # Bersihkan nama dari karakter non-huruf berlebih
                    final_name = re.sub(r'[^\w\s-]', '', final_name).strip()
                    
                    # Cek Qty "2x" di dalam nama
                    match_qty = re.match(r'^(\d+)\s*[xX]?\s+(.+)', final_name)
                    if match_qty:
                        qty_str = match_qty.group(1) + "x"
                        final_name = match_qty.group(2)
                    elif qty_str:
                         # Bersihkan qty_str jadi angka saja + "x"
                         q_nums = re.findall(r'\d+', qty_str)
                         if q_nums: qty_str = q_nums[0] + "x"
                    
                    full_item = f"{qty_str} {final_name}".strip()
                    
                    # Validasi: Harus ada huruf (bukan angka doang) & panjang cukup
                    if re.search(r'[a-zA-Z]', full_item) and len(full_item) > 3:
                         if not items_found or items_found[-1] != full_item:
                             items_found.append(full_item)

    except Exception as e:
        print(f"OCR Error: {e}")

    keterangan_otomatis = ", ".join(items_found[:5]) if items_found else ""
    
    return total_found, keterangan_otomatis

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
        ket_awal = ""
        
        if jenis == "Pengeluaran" and OCR_AVAILABLE:
            use_ocr_feature = st.checkbox("📸 Gunakan Scan Struk (Otomatis)")
            
            if use_ocr_feature:
                metode_scan = st.radio("Metode Scan:", ["📸 Kamera Langsung", "📂 Upload File"], horizontal=True)
                img_file = None
                
                if metode_scan == "📸 Kamera Langsung":
                    img_file = st.camera_input("Ambil Foto Struk")
                else:
                    img_file = st.file_uploader("Upload Foto Struk", type=['png', 'jpg', 'jpeg'])
                
                if img_file:
                    with st.spinner("Menganalisis item belanja..."):
                        image_data = Image.open(img_file)
                        if metode_scan == "📂 Upload File":
                            st.image(image_data, caption="Preview Struk", width=200)
                            
                        res_total, res_ket = proses_ocr_lengkap(image_data)
                    
                    if res_total > 0: 
                        st.success(f"Terdeteksi: Rp {res_total:,}")
                        if res_ket:
                            st.info(f"Item ditemukan: {res_ket}")
                        nom_awal = res_total
                        ket_awal = res_ket 
                    else: 
                        st.warning("Gagal membaca harga. Pastikan foto terang & jelas.")

        with st.form("form_utama", border=False):
            c_in1, c_in2 = st.columns(2)
            # Input Nominal
            nom = c_in1.number_input("Nominal (Rp)", min_value=0, value=nom_awal, step=5000)
            
            # Input Keterangan
            if ket_awal:
                ket = c_in2.text_input("Keterangan", value=ket_awal)
            else:
                ket = c_in2.text_input("Keterangan", placeholder="Contoh: Ayam Goreng, Nasi")
            
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
                    st.toast('✅ Data berhasil disimpan!', icon='☁️')
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