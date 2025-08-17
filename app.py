import streamlit as st
import base64
import requests
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import pickle

# -------------------------
# Konfigurasi (secrets)
# -------------------------
# Contoh secrets.toml:
# [google]
# api_key = "GEMINI_API_KEY"
# client_id = "xxx.apps.googleusercontent.com"
# client_secret = "yyy"
# redirect_uri = "https://kenan-ai-generate-formulir.streamlit.app/"  # atau http://localhost:8501/
API_KEY = st.secrets["google"]["api_key"]
CLIENT_ID = st.secrets["google"]["client_id"]
CLIENT_SECRET = st.secrets["google"]["client_secret"]
REDIRECT_URI = st.secrets["google"]["redirect_uri"]

GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={API_KEY}"

PROMPT = """
Analisa formulir pada gambar ini dan berikan informasi dalam format yang PERSIS seperti ini:

NISN: [nomor nisn dari formulir]
NAMA LENGKAP: [Nama Lengkap]
TEMPAT LAHIR: [tempat lahir]
TANGGAL LAHIR: [tanggal lahir jika terlihat, atau 2025-06-19]
Program Keahlian 1: [singkatan jurusan]
Program Keahlian 2: [singkatan jurusan]

Contoh response yang benar:
NISN: 01230303
NAMA LENGKAP: IMAM AMIRULLOH
TEMPAT LAHIR: TASIKMALAYA
TANGGAL LAHIR: 12-03-1991
Program Keahlian 1: TJKT
Program Keahlian 2: PPLG

Jika formulir tidak jelas atau tidak bisa dibaca, berikan:
ERROR: formulir tidak dapat dibaca dengan jelas

PENTING: Hanya berikan response dalam format di atas!
"""

# -------------------------
# Session state
# -------------------------
if "sheet_client" not in st.session_state:
    st.session_state.sheet_client = None          # gspread client (Service Account / OAuth)
if "oauth_creds" not in st.session_state:
    st.session_state.oauth_creds = None           # pickle of google.oauth2.credentials.Credentials

# -------------------------
# Sidebar: Pilih Mode Autentikasi
# -------------------------
st.sidebar.header("🔑 Google Sheets Authentication")
auth_mode = st.sidebar.radio("Pilih metode login:", ["Service Account", "OAuth2 Login"])

SHEET = None
spreadsheet_id = st.sidebar.text_input("Spreadsheet ID", placeholder="Masukkan Spreadsheet ID di sini")

# ---------- SERVICE ACCOUNT ----------
if auth_mode == "Service Account":
    uploaded_cred = st.sidebar.file_uploader("Upload service_account.json", type=["json"])
    if uploaded_cred and spreadsheet_id:
        try:
            creds_json = json.load(uploaded_cred)
            scope = [
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive"
            ]
            sa_creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
            client = gspread.authorize(sa_creds)
            SHEET = client.open_by_key(spreadsheet_id).sheet1
            st.session_state.sheet_client = client
            st.sidebar.success("✅ Terhubung (Service Account)")
        except Exception as e:
            st.sidebar.error(f"❌ Gagal autentikasi: {e}")

# ---------- OAUTH2 LOGIN ----------
else:
    scopes = [
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
        "https://www.googleapis.com/auth/spreadsheets"
    ]

    # 1) Jika ada code di URL -> tukar token & simpan ke session
    qp = st.query_params
    if "code" in qp and st.session_state.oauth_creds is None:
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": CLIENT_ID,
                    "project_id": "streamlit-oauth",
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                    "client_secret": CLIENT_SECRET,
                    "redirect_uris": [REDIRECT_URI],
                }
            },
            scopes=scopes,
            redirect_uri=REDIRECT_URI,
        )
        flow.fetch_token(code=qp["code"])
        creds = flow.credentials
        # simpan ke session secara aman (pickle)
        st.session_state.oauth_creds = pickle.dumps(creds)
        st.experimental_rerun()

    # 2) Jika sudah login (punya creds), buat gspread client via googleapiclient
    if st.session_state.oauth_creds is not None:
        creds: Credentials = pickle.loads(st.session_state.oauth_creds)
        st.sidebar.success("✅ Sudah login dengan Google")
        try:
            # Buat Sheets API client untuk cek akses
            sheets_service = build("sheets", "v4", credentials=creds)
            # Atau pakai gspread dengan oauth creds
            oauth_client = gspread.authorize(creds)
            st.session_state.sheet_client = oauth_client
            if spreadsheet_id:
                SHEET = oauth_client.open_by_key(spreadsheet_id).sheet1
        except Exception as e:
            st.sidebar.error(f"❌ Gagal membuat client Sheets: {e}")

        if st.sidebar.button("Logout"):
            st.session_state.oauth_creds = None
            st.session_state.sheet_client = None
            st.experimental_rerun()
    else:
        # 3) Belum login -> tampilkan tombol login
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": CLIENT_ID,
                    "project_id": "streamlit-oauth",
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                    "client_secret": CLIENT_SECRET,
                    "redirect_uris": [REDIRECT_URI],
                }
            },
            scopes=scopes,
            redirect_uri=REDIRECT_URI,
        )
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
        # Link langsung (Streamlit akan membuka di tab baru)
        st.sidebar.markdown(f"[🔐 Login dengan Google]({auth_url})")

# -------------------------
# Main App
# -------------------------
st.title("📄 Formulir Analyzer dengan Gemini + Google Sheets")

uploaded_file = st.file_uploader("Upload gambar formulir (JPG/PNG)", type=["jpg", "jpeg", "png"])
if uploaded_file:
    st.image(uploaded_file, caption="Formulir yang diupload", use_column_width=True)

if uploaded_file and st.button("🔍 Analisa Formulir"):
    # deteksi mime dari file yang diupload
    mime = "image/jpeg" if uploaded_file.type in ["image/jpg", "image/jpeg"] else "image/png"
    base64_str = base64.b64encode(uploaded_file.getvalue()).decode("utf-8")

    with st.spinner("Mengirim ke Gemini API..."):
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": PROMPT},
                        {"inlineData": {"mimeType": mime, "data": base64_str}},
                    ]
                }
            ]
        }

        headers = {"Content-Type": "application/json"}
        resp = requests.post(GEMINI_URL, headers=headers, data=json.dumps(payload))

    if resp.status_code != 200:
        st.error(f"❌ Gagal request ke Gemini API: {resp.text}")
    else:
        try:
            result = resp.json()
            output_text = result["candidates"][0]["content"]["parts"][0]["text"]
        except Exception:
            output_text = "ERROR: Response tidak sesuai format."

        st.subheader("📌 Hasil Analisa")
        st.text(output_text)

        # Simpan ke Google Sheet jika tersedia
        if "ERROR" in output_text:
            st.warning("⚠️ Data tidak bisa disimpan karena error analisa.")
        else:
            if spreadsheet_id and st.session_state.sheet_client:
                try:
                    rows = output_text.split("\n")
                    data_dict = {}
                    for row in rows:
                        if ": " in row:
                            key, value = row.split(": ", 1)
                            data_dict[key.strip()] = value.strip()

                    client = st.session_state.sheet_client
                    sheet = client.open_by_key(spreadsheet_id).sheet1
                    sheet.append_row([
                        data_dict.get("NISN", ""),
                        data_dict.get("NAMA LENGKAP", ""),
                        data_dict.get("TEMPAT LAHIR", ""),
                        data_dict.get("TANGGAL LAHIR", ""),
                        data_dict.get("Program Keahlian 1", ""),
                        data_dict.get("Program Keahlian 2", ""),
                    ])
                    st.success("✅ Data berhasil disimpan ke Google Sheets!")
                except Exception as e:
                    st.error(f"❌ Gagal menyimpan ke Google Sheet: {e}")
            else:
                st.warning("⚠️ Google Sheet belum dikonfigurasi atau belum login.")
