import streamlit as st
from datetime import datetime
import pandas as pd
from PIL import Image
import os

# --- KONFIGURASI HALAMAN ---
st.set_page_config(page_title="DompetKu Permanen", page_icon="💰", layout="wide")
st.markdown("""<style>.stButton button {height: 60px; font-weight: bold; border-radius: 12px;}</style>""", unsafe_allow_html=True)

# --- NAMA FILE DATABASE ---
FILE_DB = 'data_keuangan.csv'

# --- FUNGSI LOAD & SAVE DATA (INI RAHASIANYA) ---
def load_data():
    """Membaca data dari file CSV saat aplikasi dibuka"""
    if os.path.exists(FILE_DB):
        try:
            df = pd.read_csv(FILE_DB)
            # Kembalikan dalam bentuk List of Dictionary
            return df.to_dict('records')
        except Exception as e:
            st.error(f"Gagal membaca database: {e}")
            return []
    return []

def save_data():
    """Menyimpan data ke file CSV setiap ada perubahan"""
    if 'transaksi' in st.session_state:
        df = pd.DataFrame(st.session_state['transaksi'])
        df.to_csv(FILE_DB, index=False)

# --- CEK LIBRARY OCR ---
OCR_AVAILABLE = False
try:
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:
    pass

# --- KONFIGURASI TESSERACT OTOMATIS (WINDOWS) ---
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

# --- INISIALISASI SESSION STATE ---
if 'transaksi' not in st.session_state:
    # Load data dari CSV saat pertama kali buka
    st.session_state['transaksi'] = load_data()

if 'active_form' not in st.session_state:
    st.session_state['active_form'] = None 

# --- FUNGSI OCR ---
def proses_ocr(gambar):
    if not OCR_AVAILABLE: return 0
    if os.name == 'nt' and not tesseract_found:
        st.error("⚠️ Software Tesseract-OCR tidak ditemukan.")
        return 0
    try:
        text = pytesseract.image_to_string(gambar)
        import re
        text_bersih = text.replace('.', '').replace(',', '')
        angka_ditemukan = re.findall(r'\d+', text_bersih)
        if angka_ditemukan:
            angka_int = [int(n) for n in angka_ditemukan if n.isdigit()]
            if angka_int: return max(angka_int)
    except Exception as e:
        st.error(f"Gagal memproses gambar: {e}")
    return 0

# --- FUNGSI HITUNG SALDO ---
def hitung_statistik():
    if not st.session_state['transaksi']:
        return 0, 0, 0
    masuk = sum(t['Nominal'] for t in st.session_state['transaksi'] if t['Jenis'] == 'Pemasukan')
    keluar = sum(t['Nominal'] for t in st.session_state['transaksi'] if t['Jenis'] == 'Pengeluaran')
    saldo = masuk - keluar
    return masuk, keluar, saldo

# ==========================================
# UI DASHBOARD
# ==========================================
st.title("💰 DompetKu (Versi Permanen)")
st.markdown("### Ringkasan Keuangan")

masuk, keluar, saldo = hitung_statistik()
c1, c2, c3 = st.columns(3)
c1.metric("Sisa Saldo", f"Rp {saldo:,}")
c2.metric("Total Pemasukan", f"Rp {masuk:,}", delta="+")
c3.metric("Total Pengeluaran", f"Rp {keluar:,}", delta="-")

st.markdown("---")

# TOMBOL AKSI
b1, b2 = st.columns(2)
with b1:
    if st.button("➕ TAMBAH PEMASUKAN", use_container_width=True, type="primary"):
        st.session_state['active_form'] = 'Pemasukan'
with b2:
    if st.button("➖ TAMBAH PENGELUARAN", use_container_width=True):
        st.session_state['active_form'] = 'Pengeluaran'

# FORM INPUT
if st.session_state['active_form']:
    jenis = st.session_state['active_form']
    color = "green" if jenis == "Pemasukan" else "red"
    st.markdown(f"#### Form: :{color}[{jenis}]")
    
    with st.container(border=True):
        nom_awal = 0
        if jenis == "Pengeluaran" and OCR_AVAILABLE:
            use_cam = st.checkbox("📸 Scan Struk")
            if use_cam:
                img = st.camera_input("Foto")
                if img:
                    res = proses_ocr(Image.open(img))
                    if res > 0: 
                        st.success(f"Ketemu: {res}")
                        nom_awal = res
                    else: st.warning("Gagal baca.")

        with st.form("f1"):
            c_in1, c_in2 = st.columns(2)
            nom = c_in1.number_input("Nominal", min_value=0, value=nom_awal, step=1000)
            ket = c_in2.text_input("Keterangan", placeholder="Cth: Bayar Listrik")
            
            if st.form_submit_button("💾 SIMPAN DATA"):
                if nom > 0:
                    baru = {
                        'Tanggal': datetime.now().strftime("%Y-%m-%d %H:%M"),
                        'Jenis': jenis,
                        'Nominal': nom,
                        'Keterangan': ket if ket else "-"
                    }
                    st.session_state['transaksi'].insert(0, baru)
                    save_data() # <--- SIMPAN PERMANEN
                    st.session_state['active_form'] = None
                    st.rerun()
                else: st.error("Nominal 0")
    
    if st.button("Tutup"):
        st.session_state['active_form'] = None
        st.rerun()

st.markdown("---")
st.subheader("📋 Riwayat Transaksi")

if st.session_state['transaksi']:
    df = pd.DataFrame(st.session_state['transaksi'])
    if "Hapus" not in df.columns: df["Hapus"] = False
    
    # Editor Tabel
    edited_df = st.data_editor(
        df[["Hapus", "Tanggal", "Jenis", "Nominal", "Keterangan"]],
        use_container_width=True,
        column_config={
            "Hapus": st.column_config.CheckboxColumn("Hapus?", default=False),
            "Nominal": st.column_config.NumberColumn("Rp", format="Rp %d"),
            "Jenis": st.column_config.SelectboxColumn("Tipe", options=["Pemasukan", "Pengeluaran"])
        },
        hide_index=True, num_rows="fixed"
    )

    # LOGIKA SIMPAN PERUBAHAN
    perubahan_terjadi = False
    
    # 1. Cek Hapus
    if edited_df["Hapus"].any():
        df_baru = edited_df[edited_df["Hapus"] == False].drop(columns=["Hapus"])
        st.session_state['transaksi'] = df_baru.to_dict('records')
        perubahan_terjadi = True
    
    # 2. Cek Edit
    elif not edited_df.drop(columns=["Hapus"]).equals(pd.DataFrame(st.session_state['transaksi'])):
        st.session_state['transaksi'] = edited_df.drop(columns=["Hapus"]).to_dict('records')
        perubahan_terjadi = True
    
    # Jika ada perubahan, simpan ke CSV
    if perubahan_terjadi:
        save_data() # <--- SIMPAN PERMANEN
        st.rerun()

    if st.button("🗑️ Reset Semua Data"):
        st.session_state['transaksi'] = []
        save_data() # <--- SIMPAN PERMANEN
        st.rerun()
else:
    st.info("Data kosong.")