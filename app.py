import streamlit as st
import base64
import requests
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import os

# -------------------------
# Konfigurasi Gemini API
# -------------------------
API_KEY = "AIzaSyA0Gp87OAEDWyebqQCxdoawLcKBEKp_2tc"  # ganti dengan API key Gemini Anda
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
# Sidebar: Pilih Mode Autentikasi
# -------------------------
st.sidebar.header("🔑 Google Sheets Authentication1")
auth_mode = st.sidebar.radio("Pilih metode login:", ["Service Account", "OAuth2 Login"])

SHEET = None

if auth_mode == "Service Account":
    uploaded_cred = st.sidebar.file_uploader("Upload service_account.json", type=["json"])
    spreadsheet_id = st.sidebar.text_input("Spreadsheet ID", placeholder="Masukkan Spreadsheet ID di sini")

    if uploaded_cred and spreadsheet_id:
        try:
            creds_json = json.load(uploaded_cred)
            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
            client = gspread.authorize(creds)
            SHEET = client.open_by_key(spreadsheet_id).sheet1
            st.sidebar.success("✅ Terhubung ke Google Sheets (Service Account)")
        except Exception as e:
            st.sidebar.error(f"❌ Gagal autentikasi: {e}")

elif auth_mode == "OAuth2 Login":
    # client_id = st.sidebar.text_input("Client ID", placeholder="YOUR_CLIENT_ID.apps.googleusercontent.com")
    # client_secret = st.sidebar.text_input("Client Secret", placeholder="YOUR_CLIENT_SECRET", type="password")
    # spreadsheet_id = st.sidebar.text_input("Spreadsheet ID", placeholder="Masukkan Spreadsheet ID di sini")

    client_id = "476601797600-pnuqe4qs74gk9kibl817nedksbvv8njo.apps.googleusercontent.com"
    client_secret = "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"

    if client_id and client_secret:
        redirect_uri = "https://kenan-ai-generate-formulir.streamlit.app/"
        scopes = ["openid", "https://www.googleapis.com/auth/userinfo.email", "https://www.googleapis.com/auth/userinfo.profile","https://www.googleapis.com/auth/spreadsheets"]

        if "oauth_credentials" not in st.session_state:
            # Step 1: buat link login
            flow = Flow.from_client_config(
                {"web":{"client_id":"476601797600-pnuqe4qs74gk9kibl817nedksbvv8njo.apps.googleusercontent.com","project_id":"api-formulir","auth_uri":"https://accounts.google.com/o/oauth2/auth","token_uri":"https://oauth2.googleapis.com/token","auth_provider_x509_cert_url":"https://www.googleapis.com/oauth2/v1/certs","client_secret":"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","redirect_uris":["https://kenan-ai-generate-formulir.streamlit.app/"]}},
                scopes=scopes,
                redirect_uri=redirect_uri
            )
            auth_url, _ = flow.authorization_url(prompt="consent")

            if st.sidebar.button("🔐 Login dengan Google"):
                st.sidebar.write("Klik link di bawah untuk login:")
                st.sidebar.markdown(f"[Login disini]({auth_url})", unsafe_allow_html=True)

        else:
            st.sidebar.success("✅ Sudah login dengan Google")
            spreadsheet_id = st.sidebar.text_input("Spreadsheet ID", placeholder="Masukkan Spreadsheet ID di sini")

        # NOTE: di Streamlit, handle redirect masih manual (perlu deploy + query param parsing)

# -------------------------
# Main App
# -------------------------
st.title("📄 Formulir Analyzer dengan Gemini + Google Sheets")

uploaded_file = st.file_uploader("Upload gambar formulir (JPG/PNG)", type=["jpg", "jpeg", "png"])

if uploaded_file:
    st.image(uploaded_file, caption="Formulir yang diupload", use_column_width=True)

    bytes_data = uploaded_file.getvalue()
    base64_str = base64.b64encode(bytes_data).decode("utf-8")

    if st.button("🔍 Analisa Formulir"):
        with st.spinner("Mengirim ke Gemini API..."):
            payload = {
                "contents": [
                    {
                        "parts": [
                            {"text": PROMPT},
                            {"inlineData": {"mimeType": "image/jpeg", "data": base64_str}}
                        ]
                    }
                ]
            }

            headers = {"Content-Type": "application/json"}
            response = requests.post(GEMINI_URL, headers=headers, data=json.dumps(payload))

            if response.status_code == 200:
                result = response.json()
                try:
                    output_text = result["candidates"][0]["content"]["parts"][0]["text"]
                except:
                    output_text = "ERROR: Response tidak sesuai format."

                st.subheader("📌 Hasil Analisa")
                st.text(output_text)

                # Simpan ke Google Sheet jika tersedia
                if SHEET and "ERROR" not in output_text:
                    rows = output_text.split("\n")
                    data_dict = {}
                    for row in rows:
                        if ": " in row:
                            key, value = row.split(": ", 1)
                            data_dict[key.strip()] = value.strip()

                    SHEET.append_row([
                        data_dict.get("NISN", ""),
                        data_dict.get("NAMA LENGKAP", ""),
                        data_dict.get("TEMPAT LAHIR", ""),
                        data_dict.get("TANGGAL LAHIR", ""),
                        data_dict.get("Program Keahlian 1", ""),
                        data_dict.get("Program Keahlian 2", "")
                    ])
                    st.success("✅ Data berhasil disimpan ke Google Sheets!")
                elif not SHEET:
                    st.warning("⚠️ Google Sheet belum dikonfigurasi.")
                else:
                    st.warning("⚠️ Data tidak bisa disimpan karena error analisa.")
            else:
                st.error(f"❌ Gagal request ke Gemini API: {response.text}")








