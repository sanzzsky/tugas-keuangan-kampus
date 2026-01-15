import streamlit as st
from datetime import datetime
import pandas as pd
from PIL import Image
import os
import json
import re 

# --- LIBRARY FIREBASE ---
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore

# --- KONFIGURASI HALAMAN ---
st.set_page_config(page_title="DompetKu Cloud", page_icon="🔥", layout="wide")
st.markdown("""<style>.stButton button {height: 60px; font-weight: bold; border-radius: 12px;}</style>""", unsafe_allow_html=True)

# --- KONEKSI KE FIREBASE (VERSI ANTI ERROR) ---
if not firebase_admin._apps:
    try:
        # Ambil teks mentah dari Secrets
        raw_key = st.secrets["firebase"]["textkey"]
        
        # 1. Coba load normal dengan mode santai (strict=False)
        try:
            key_dict = json.loads(raw_key, strict=False)
        except json.JSONDecodeError:
            # 2. Jika gagal, kita coba bersihkan manual karakter 'Enter' yang nyasar
            # Kita ganti baris baru (\n) menjadi spasi, tapi hati-hati
            # Trik paling aman: Hapus control character (ASCII 0-31) kecuali struktur JSON
            # Namun untuk pemula, kita coba parsing paksa:
            fixed_key = raw_key.replace('\n', ' ')
            key_dict = json.loads(fixed_key, strict=False)

        # 3. Perbaiki format Private Key agar bisa dibaca Firebase
        # Kadang private key jadi satu baris panjang, kita harus pastikan formatnya benar
        if "private_key" in key_dict:
            key_dict["private_key"] = key_dict["private_key"].replace("\\n", "\n")

        # Login ke Firebase
        cred = credentials.Certificate(key_dict)
        firebase_admin.initialize_app(cred)
        
    except Exception as e:
        st.error(f"Gagal login ke Firebase. Coba cek Secrets lagi. Error detail: {e}")
        st.stop()

db = firestore.client()

# --- FUNGSI CRUD FIREBASE ---
def load_data_firestore():
    try:
        docs = db.collection('transaksi').order_by('Tanggal', direction=firestore.Query.DESCENDING).stream()
        data = []
        for doc in docs:
            d = doc.to_dict()
            d['id'] = doc.id 
            data.append(d)
        return data
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return []

def tambah_data_firestore(data):
    db.collection('transaksi').add(data)

def hapus_data_firestore(doc_id):
    db.collection('transaksi').document(doc_id).delete()

def update_data_firestore(doc_id, data_baru):
    db.collection('transaksi').document(doc_id).update(data_baru)

# --- CEK LIBRARY OCR ---
OCR_AVAILABLE = False
try:
    import pytesseract
    OCR_AVAILABLE = True
except ImportError: pass

# --- KONFIGURASI TESSERACT (Windows Only) ---
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
    st.session_state['transaksi'] = load_data_firestore()
    # Paksakan reload jika kosong agar sinkron
    if not st.session_state['transaksi']:
        st.session_state['transaksi'] = load_data_firestore()

if 'active_form' not in st.session_state:
    st.session_state['active_form'] = None 

# --- FUNGSI OCR ---
def proses_ocr(gambar):
    if not OCR_AVAILABLE: return 0
    if os.name == 'nt' and not tesseract_found:
        st.warning("Tesseract tidak ditemukan.")
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

# ==========================================
# UI DASHBOARD
# ==========================================
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
                    tambah_data_firestore(baru) 
                    st.success("Tersimpan!")
                    st.session_state['transaksi'] = load_data_firestore() # Reload data terbaru
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
    
    # Pastikan kolom ada sebelum ditampilkan
    cols_to_show = ["Hapus", "Tanggal", "Jenis", "Nominal", "Keterangan", "id"]
    for col in cols_to_show:
        if col not in df.columns:
            df[col] = "" # Isi dummy jika kolom hilang

    edited_df = st.data_editor(
        df[cols_to_show], 
        use_container_width=True,
        column_config={
            "id": None, 
            "Hapus": st.column_config.CheckboxColumn("Hapus?", default=False),
            "Nominal": st.column_config.NumberColumn("Rp", format="Rp %d"),
            "Jenis": st.column_config.SelectboxColumn("Tipe", options=["Pemasukan", "Pengeluaran"])
        },
        hide_index=True, num_rows="fixed"
    )

    if edited_df["Hapus"].any():
        to_delete = edited_df[edited_df["Hapus"] == True]
        for index, row in to_delete.iterrows():
            hapus_data_firestore(row['id'])
        st.session_state['transaksi'] = load_data_firestore()
        st.rerun()
    
    elif not edited_df["Hapus"].any():
        # Tombol manual update untuk keamanan dan performa
        if st.button("⚠️ Simpan Perubahan Data"):
            original_data = pd.DataFrame(st.session_state['transaksi'])
            # Pastikan index reset agar iterasi sama
            # (Simplifikasi: kita loop saja edited_df dan update semuanya yang ID-nya cocok)
            for index, row in edited_df.iterrows():
                update_data_firestore(row['id'], {
                    'Nominal': row['Nominal'],
                    'Keterangan': row['Keterangan'],
                    'Jenis': row['Jenis']
                })
            st.success("Data diupdate!")
            st.session_state['transaksi'] = load_data_firestore()
            st.rerun()

    if st.button("🗑️ Reset Semua (Hati-hati!)"):
        for t in st.session_state['transaksi']:
            hapus_data_firestore(t['id'])
        st.session_state['transaksi'] = []
        st.rerun()
else:
    st.info("Data kosong. Silakan tambah data.")