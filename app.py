import streamlit as st
from datetime import datetime
import pandas as pd
from PIL import Image
import os

# --- KONFIGURASI HALAMAN ---
st.set_page_config(page_title="DompetKu Dashboard", page_icon="💰", layout="wide")

# --- CSS ---
st.markdown("""
<style>
    .stButton button {
        height: 60px;
        font-weight: bold;
        border-radius: 12px;
    }
</style>
""", unsafe_allow_html=True)

# --- CEK LIBRARY OCR ---
OCR_AVAILABLE = False
try:
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:
    st.error("⚠️ Library 'pytesseract' belum terinstall. Fitur Scan Struk dimatikan.")

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
    st.session_state['transaksi'] = []
if 'active_form' not in st.session_state:
    st.session_state['active_form'] = None 

# --- FUNGSI OCR ---
def proses_ocr(gambar):
    if not OCR_AVAILABLE:
        return 0
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
            if angka_int:
                return max(angka_int)
    except Exception as e:
        st.error(f"Gagal memproses gambar: {e}")
    return 0

# --- FUNGSI HITUNG SALDO ---
def hitung_statistik():
    masuk = sum(t['Nominal'] for t in st.session_state['transaksi'] if t['Jenis'] == 'Pemasukan')
    keluar = sum(t['Nominal'] for t in st.session_state['transaksi'] if t['Jenis'] == 'Pengeluaran')
    saldo = masuk - keluar
    return masuk, keluar, saldo

# ==========================================
# TAMPILAN UTAMA (DASHBOARD)
# ==========================================

st.title("💰 DompetKu")
st.markdown("### Ringkasan Keuangan")

# 1. BAGIAN METRICS
masuk, keluar, saldo = hitung_statistik()
col1, col2, col3 = st.columns(3)
col1.metric("Sisa Saldo", f"Rp {saldo:,}", delta=f"{saldo}", delta_color="normal")
col2.metric("Total Pemasukan", f"Rp {masuk:,}", delta="+", delta_color="inverse")
col3.metric("Total Pengeluaran", f"Rp {keluar:,}", delta="-", delta_color="inverse")

st.markdown("---")

# 2. TOMBOL AKSI CEPAT
col_btn1, col_btn2 = st.columns(2)

with col_btn1:
    if st.button("➕ TAMBAH PEMASUKAN", use_container_width=True, type="primary"):
        st.session_state['active_form'] = 'Pemasukan'

with col_btn2:
    if st.button("➖ TAMBAH PENGELUARAN", use_container_width=True):
        st.session_state['active_form'] = 'Pengeluaran'

# 3. BAGIAN FORM INPUT
if st.session_state['active_form'] is not None:
    jenis_transaksi = st.session_state['active_form']
    container_color = "green" if jenis_transaksi == "Pemasukan" else "red"
    st.markdown(f"#### Form Input: :{container_color}[{jenis_transaksi}]")
    
    with st.container(border=True):
        nominal_awal = 0
        
        # Fitur Kamera
        if jenis_transaksi == "Pengeluaran" and OCR_AVAILABLE:
            use_camera = st.checkbox("📸 Scan Struk Belanja")
            if use_camera:
                if not tesseract_found and os.name == 'nt':
                    st.warning("⚠️ Tesseract belum terinstall.")
                img_file = st.camera_input("Ambil Foto")
                if img_file:
                    image = Image.open(img_file)
                    st.image(image, width=200)
                    if st.button("🔍 Baca Harga Otomatis"):
                        with st.spinner('Membaca...'):
                            hasil = proses_ocr(image)
                        if hasil > 0:
                            st.success(f"Ditemukan: Rp {hasil:,}")
                            nominal_awal = hasil
                        else:
                            st.warning("Angka tidak terbaca.")

        # Form Isian
        with st.form("form_dinamis"):
            col_in1, col_in2 = st.columns(2)
            with col_in1:
                nominal = st.number_input("Nominal (Rp)", min_value=0, value=nominal_awal, step=1000)
            with col_in2:
                keterangan = st.text_input("Keterangan", placeholder="Contoh: Makan Siang")
            
            col_submit, col_cancel = st.columns([1, 4])
            with col_submit:
                submitted = st.form_submit_button("💾 SIMPAN")
            
            if submitted:
                if nominal > 0:
                    baru = {
                        'Tanggal': datetime.now().strftime("%Y-%m-%d %H:%M"),
                        'Jenis': jenis_transaksi,
                        'Nominal': nominal,
                        'Keterangan': keterangan if keterangan else "-"
                    }
                    st.session_state['transaksi'].insert(0, baru)
                    st.session_state['active_form'] = None
                    st.rerun()
                else:
                    st.error("Nominal harus > 0")

    if st.button("❌ Tutup Form"):
        st.session_state['active_form'] = None
        st.rerun()

st.markdown("---")

# 4. TABEL RIWAYAT (EDITABLE / BISA DIEDIT LANGSUNG)
st.subheader("📋 Riwayat Transaksi (Edit Langsung di Tabel)")

if len(st.session_state['transaksi']) > 0:
    # Siapkan Data
    df = pd.DataFrame(st.session_state['transaksi'])
    
    # Tambahkan kolom 'Hapus' default False untuk checkbox
    if "Hapus" not in df.columns:
        df["Hapus"] = False
        
    # Atur ulang urutan kolom agar 'Hapus' ada di paling kiri atau kanan
    cols = ["Hapus", "Tanggal", "Jenis", "Nominal", "Keterangan"]
    df = df[cols]

    # Tampilkan Data Editor (Tabel yang bisa diedit)
    edited_df = st.data_editor(
        df,
        use_container_width=True,
        column_config={
            "Hapus": st.column_config.CheckboxColumn(
                "Hapus?",
                help="Centang untuk menghapus data ini",
                default=False,
            ),
            "Tanggal": st.column_config.TextColumn(
                "Waktu",
                disabled=True # Tanggal tidak usah diedit biar aman
            ),
            "Jenis": st.column_config.SelectboxColumn(
                "Tipe",
                options=["Pemasukan", "Pengeluaran"], # Bisa ganti tipe lewat dropdown di tabel
                width="medium",
                required=True
            ),
            "Nominal": st.column_config.NumberColumn(
                "Nominal (Rp)",
                format="Rp %d",
                min_value=0,
                required=True
            ),
            "Keterangan": st.column_config.TextColumn(
                "Keterangan",
                width="large",
                required=True
            )
        },
        hide_index=True,
        num_rows="fixed" # Jumlah baris tetap, hapus lewat checkbox
    )

    # LOGIKA UPDATE DATA
    # Cek apakah ada perubahan di tabel (edited_df beda dengan session_state)
    
    # 1. Cek Hapus Data
    if edited_df["Hapus"].any():
        # Ambil data yang TIDAK dicentang hapus
        data_baru = edited_df[edited_df["Hapus"] == False].drop(columns=["Hapus"])
        # Update session state
        st.session_state['transaksi'] = data_baru.to_dict('records')
        st.rerun() # Refresh agar baris yang dihapus hilang
    
    # 2. Cek Edit Data (Jika nominal/ket berubah)
    # Kita bandingkan data saat ini dengan data hasil edit (tanpa kolom Hapus)
    data_edit_bersih = edited_df.drop(columns=["Hapus"]).to_dict('records')
    
    # Jika ada perbedaan isi data, simpan ke session state
    if data_edit_bersih != st.session_state['transaksi']:
        st.session_state['transaksi'] = data_edit_bersih
        # Kita rerun agar perhitungan saldo di atas langsung berubah
        st.rerun()

else:
    st.info("Belum ada transaksi. Tekan tombol di atas untuk mulai mencatat!")