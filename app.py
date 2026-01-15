import streamlit as st
from datetime import datetime
import pandas as pd
from PIL import Image
import os
import json

# --- LIBRARY FIREBASE ---
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore

# --- KONFIGURASI HALAMAN ---
st.set_page_config(page_title="DompetKu Cloud", page_icon="🔥", layout="wide")
st.markdown("""<style>.stButton button {height: 60px; font-weight: bold; border-radius: 12px;}</style>""", unsafe_allow_html=True)

# --- KONEKSI KE FIREBASE (RAHASIA) ---
# Cek apakah Firebase sudah terhubung biar tidak error saat refresh
if not firebase_admin._apps:
    try:
        # Mengambil kunci dari Streamlit Secrets
        key_dict = json.loads(st.secrets["firebase"]["textkey"])
        cred = credentials.Certificate(key_dict)
        firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error(f"Gagal login ke Firebase: {e}. Pastikan Secrets sudah diisi.")
        st.stop()

db = firestore.client()

# --- FUNGSI CRUD FIREBASE ---
def load_data_firestore():
    """Mengambil semua data dari Cloud"""
    try:
        # Ambil koleksi 'transaksi', urutkan berdasarkan Tanggal terbaru
        docs = db.collection('transaksi').order_by('Tanggal', direction=firestore.Query.DESCENDING).stream()
        data = []
        for doc in docs:
            d = doc.to_dict()
            d['id'] = doc.id # Simpan ID dokumen biar bisa diedit/hapus nanti
            data.append(d)
        return data
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return []

def tambah_data_firestore(data):
    """Mengirim data baru ke Cloud"""
    db.collection('transaksi').add(data)

def hapus_data_firestore(doc_id):
    """Menghapus data di Cloud berdasarkan ID"""
    db.collection('transaksi').document(doc_id).delete()

def update_data_firestore(doc_id, data_baru):
    """Update data di Cloud"""
    db.collection('transaksi').document(doc_id).update(data_baru)

# --- CEK LIBRARY OCR ---
OCR_AVAILABLE = False
try:
    import pytesseract
    OCR_AVAILABLE = True
except ImportError: pass

# --- KONFIGURASI TESSERACT OTOMATIS (WINDOWS - JIKA DI LOCAL) ---
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
# Kita load data setiap kali halaman direfresh untuk memastikan data sinkron
st.session_state['transaksi'] = load_data_firestore()

if 'active_form' not in st.session_state:
    st.session_state['active_form'] = None 

# --- FUNGSI OCR ---
def proses_ocr(gambar):
    if not OCR_AVAILABLE: return 0
    if os.name == 'nt' and not tesseract_found:
        st.warning("Tesseract tidak ditemukan di Windows ini.")
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
        st.error(f"Error OCR: {e}")
    return 0

# --- FUNGSI HITUNG SALDO ---
def hitung_statistik():
    if not st.session_state['transaksi']: return 0, 0, 0
    masuk = sum(t['Nominal'] for t in st.session_state['transaksi'] if t['Jenis'] == 'Pemasukan')
    keluar = sum(t['Nominal'] for t in st.session_state['transaksi'] if t['Jenis'] == 'Pengeluaran')
    return masuk, keluar, masuk - keluar

# UI DASHBOARD
st.title("🔥 DompetKu (Cloud Connected)")
st.caption("Data tersimpan aman di Google Firestore")

masuk, keluar, saldo = hitung_statistik()
c1, c2, c3 = st.columns(3)
c1.metric("Sisa Saldo", f"Rp {saldo:,}")
c2.metric("Pemasukan", f"Rp {masuk:,}", delta="+")
c3.metric("Pengeluaran", f"Rp {keluar:,}", delta="-")

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
            c1, c2 = st.columns(2)
            nom = c1.number_input("Nominal", min_value=0, value=nom_awal, step=1000)
            ket = c2.text_input("Keterangan", placeholder="Cth: Bayar Listrik")
            
            if st.form_submit_button("💾 SIMPAN KE CLOUD"):
                if nom > 0:
                    baru = {
                        'Tanggal': datetime.now().strftime("%Y-%m-%d %H:%M"),
                        'Jenis': jenis,
                        'Nominal': nom,
                        'Keterangan': ket if ket else "-"
                    }
                    tambah_data_firestore(baru) # <--- KIRIM KE CLOUD
                    st.success("Tersimpan di Cloud!")
                    st.session_state['active_form'] = None
                    st.rerun()
                else: st.error("Nominal 0")
    
    if st.button("Tutup"):
        st.session_state['active_form'] = None
        st.rerun()

st.markdown("---")
st.subheader("📋 Riwayat Transaksi (Live Sync)")

if st.session_state['transaksi']:
    df = pd.DataFrame(st.session_state['transaksi'])
    if "Hapus" not in df.columns: df["Hapus"] = False
    
    # Editor Tabel
    edited_df = st.data_editor(
        df[["Hapus", "Tanggal", "Jenis", "Nominal", "Keterangan", "id"]], # ID ikut ditampilkan tapi hidden nanti
        use_container_width=True,
        column_config={
            "id": None, # Sembunyikan kolom ID
            "Hapus": st.column_config.CheckboxColumn("Hapus?", default=False),
            "Nominal": st.column_config.NumberColumn("Rp", format="Rp %d"),
            "Jenis": st.column_config.SelectboxColumn("Tipe", options=["Pemasukan", "Pengeluaran"])
        },
        hide_index=True, num_rows="fixed"
    )

    # LOGIKA SIMPAN PERUBAHAN KE CLOUD
    # 1. Cek Hapus
    if edited_df["Hapus"].any():
        to_delete = edited_df[edited_df["Hapus"] == True]
        for index, row in to_delete.iterrows():
            hapus_data_firestore(row['id']) # Hapus di Cloud berdasarkan ID unik
        st.rerun()
    
    # 2. Cek Edit (Agak kompleks karena harus bandingkan per baris)
    # Kita bandingkan dataframe asli (dari session) dengan hasil edit
    # Karena pandas compare agak ribet, kita pakai loop sederhana untuk mendeteksi perubahan
    # (Hanya berjalan jika tombol Hapus tidak dicentang)
    elif not edited_df["Hapus"].any():
        original_data = pd.DataFrame(st.session_state['transaksi'])
        # Pastikan kolom sama
        cols = ["Tanggal", "Jenis", "Nominal", "Keterangan", "id"]
        
        # Jika user mengubah sesuatu, data editor akan mengembalikan nilai baru
        # Kita perlu mencari baris mana yang berubah
        # Cara termudah: Loop dan update jika beda (ini agak boros operasi tapi paling mudah dipahami)
        
        # Note: Streamlit data_editor tidak memberikan event "on_change" per baris secara langsung
        # Jadi kita harus membandingkan manual atau menggunakan tombol "Simpan Perubahan"
        # Untuk kemudahan di sini, kita pakai tombol Update Manual agar tidak spamming database
        
        if not edited_df[cols].equals(original_data[cols]):
            if st.button("⚠️ Deteksi Perubahan: Simpan ke Cloud?"):
                # Cari baris yang beda
                for index, row in edited_df.iterrows():
                    orig_row = original_data.iloc[index]
                    # Bandingkan nilai penting
                    if (row['Nominal'] != orig_row['Nominal'] or 
                        row['Keterangan'] != orig_row['Keterangan'] or 
                        row['Jenis'] != orig_row['Jenis']):
                        
                        update_data_firestore(row['id'], {
                            'Nominal': row['Nominal'],
                            'Keterangan': row['Keterangan'],
                            'Jenis': row['Jenis']
                        })
                st.success("Database Cloud Diperbarui!")
                st.rerun()

    # Tombol Reset
    if st.button("🗑️ Reset Semua (Hati-hati!)"):
        for t in st.session_state['transaksi']:
            hapus_data_firestore(t['id'])
        st.rerun()
else:
    st.info("Data kosong. Silakan tambah data, nanti otomatis masuk ke Google Firebase.")