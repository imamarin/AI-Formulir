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
API_KEY = st.secrets["google"]["api_key"]
CLIENT_ID = st.secrets["google"]["client_id"]
CLIENT_SECRET = st.secrets["google"]["client_secret"]
REDIRECT_URI = st.secrets["google"]["redirect_uri"]

GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={API_KEY}"

PROMPT = """
Analisa formulir pada gambar ini dan berikan informasi dalam format yang PERSIS seperti ini:

Kolom1: [...]
Kolom2: [...]
Kolom3: [...]

Jika formulir tidak jelas atau tidak bisa dibaca, berikan:
ERROR: formulir tidak dapat dibaca dengan jelas

PENTING: Hanya berikan response dalam format di atas!
"""

# Buat prompt dinamis berdasarkan header
def build_dynamic_prompt(headers):
    prompt = "Analisa formulir pada gambar ini dan berikan informasi dalam format yang PERSIS seperti ini:\n\n"
    for h in headers:
        prompt += f"{h}: [{h.lower()} dari formulir]\n"
    prompt += """
Jika formulir tidak jelas atau tidak bisa dibaca, berikan:
ERROR: formulir tidak dapat dibaca dengan jelas

PENTING: Hanya berikan response dalam format di atas!
"""
    return prompt

# -------------------------
# Session state
# -------------------------
if "sheet_client" not in st.session_state:
    st.session_state.sheet_client = None
if "oauth_creds" not in st.session_state:
    st.session_state.oauth_creds = None
if "spreadsheet_list" not in st.session_state:
    st.session_state.spreadsheet_list = []
if "selected_spreadsheet" not in st.session_state:
    st.session_state.selected_spreadsheet = None
if "unique_column" not in st.session_state:
    st.session_state.unique_column = None

# -------------------------
# Sidebar: Pilih Mode Autentikasi
# -------------------------
st.sidebar.header("🔑 Google Sheets Authentication")
# auth_mode = st.sidebar.radio("Pilih metode login:", ["OAuth2 Login"])
auth_mode = "OAuth2 Login"

SHEET = None

# ---------- OAuth2 Login ----------

def get_credentials():
    if "oauth_creds" in st.session_state:
        return pickle.loads(st.session_state.oauth_creds)
    return None
    
if auth_mode == "OAuth2 Login":
    scopes = [
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.metadata.readonly"
    ]

    qp = st.query_params

    if "code" in qp and st.session_state.oauth_creds is None:
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": CLIENT_ID,
                    "project_id": "api-formulir",
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
        st.session_state.oauth_creds = pickle.dumps(creds)

        st.rerun()

    if st.session_state.oauth_creds is not None:
        creds: Credentials = pickle.loads(st.session_state.oauth_creds)
        st.sidebar.success("✅ Sudah login dengan Google")

        try:
            sheets_service = build("sheets", "v4", credentials=creds)
            drive_service = build("drive", "v3", credentials=creds)

            oauth_client = gspread.authorize(creds)
            st.session_state.sheet_client = oauth_client

            # Ambil daftar spreadsheet user
            if not st.session_state.spreadsheet_list:
                results = drive_service.files().list(
                    q="mimeType='application/vnd.google-apps.spreadsheet'",
                    fields="files(id, name)",
                    pageSize=50
                ).execute()
                files = results.get("files", [])
                st.session_state.spreadsheet_list = files

            # Pilihan selectbox spreadsheet
            if st.session_state.spreadsheet_list:
                spreadsheet_names = [f["name"] for f in st.session_state.spreadsheet_list]
                choice = st.sidebar.selectbox("Pilih Spreadsheet:", ["-- pilih spreadsheet --"] + spreadsheet_names)

                if choice != "-- pilih spreadsheet --":
                    chosen = next(f for f in st.session_state.spreadsheet_list if f["name"] == choice)
                    st.session_state.selected_spreadsheet = chosen

                    # Ambil header kolom
                    try:
                        client = st.session_state.sheet_client
                        sheet = client.open_by_key(chosen["id"]).sheet1
                        all_records = sheet.get_all_values()
                        headers = all_records[0] if all_records else []

                        if headers:
                            unique_column = st.sidebar.selectbox(
                                "Pilih Kolom Unik:",
                                headers,
                                index=headers.index("NISN") if "NISN" in headers else 0
                            )
                            st.session_state.unique_column = unique_column
                        else:
                            st.sidebar.warning("Spreadsheet kosong, tidak ada header kolom.")
                    except Exception as e:
                        st.sidebar.error(f"❌ Gagal mengambil header: {e}")

        except Exception as e:
            st.sidebar.error(f"❌ Gagal akses API: {e}")

        if st.sidebar.button("Logout"):
            st.session_state.clear()
            st.query_params.clear() 
            # st.session_state.oauth_creds = None
            # st.session_state.sheet_client = None
            # st.session_state.spreadsheet_list = []
            # st.session_state.selected_spreadsheet = None
            # st.session_state.unique_column = None
            st.rerun()

    else:
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": CLIENT_ID,
                    "project_id": "api-formulir",
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
        #st.sidebar.markdown(f"[🔐 Login dengan Google]({auth_url})")    
        st.sidebar.markdown(
            f"""
            <a href='{auth_url}'>
                <button style="background-color:#4285F4;color:white;border:none;
                padding:8px 16px;border-radius:5px;cursor:pointer;">
                    🔐 Login dengan Google
                </button>
            </a>
            """,
            unsafe_allow_html=True
        )

# -------------------------
# Main App
# -------------------------
st.title("📄 Kenan AI - Formulir Analyzer")

uploaded_file = st.file_uploader("Upload gambar formulir (JPG/PNG)", type=["jpg", "jpeg", "png"])
if uploaded_file:
    st.image(uploaded_file, caption="Formulir yang diupload", use_column_width=True)

if uploaded_file and st.button("🔍 Analisa Formulir"):
    mime = "image/jpeg" if uploaded_file.type in ["image/jpg", "image/jpeg"] else "image/png"
    base64_str = base64.b64encode(uploaded_file.getvalue()).decode("utf-8")

    with st.spinner("Melakukan Analisa..."):
        # kalau ada header dari spreadsheet, pakai prompt dinamis
        if st.session_state.selected_spreadsheet and st.session_state.sheet_client:
            client = st.session_state.sheet_client
            sheet = client.open_by_key(st.session_state.selected_spreadsheet["id"]).sheet1
            all_records = sheet.get_all_values()
            headers = all_records[0] if all_records else []
            if headers:
                prompt_to_use = build_dynamic_prompt(headers)
            else:
                prompt_to_use = PROMPT  # fallback ke prompt default
        else:
            prompt_to_use = PROMPT  # kalau belum pilih spreadsheet
            
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt_to_use},
                        {"inlineData": {"mimeType": mime, "data": base64_str}},
                    ]
                }
            ]
        }
        headers_req = {"Content-Type": "application/json"}
        resp = requests.post(GEMINI_URL, headers=headers_req, data=json.dumps(payload))

    if resp.status_code != 200:
        st.error(f"❌ Gagal Analisa: {resp.text}")
    else:
        try:
            result = resp.json()
            output_text = result["candidates"][0]["content"]["parts"][0]["text"]
        except Exception:
            output_text = "ERROR: Response tidak sesuai format."

        # -------------------------
        # Analisa berdasarkan header kolom
        # -------------------------
        rows = output_text.split("\n")
        data_dict = {}
        for row in rows:
            if ": " in row:
                key, value = row.split(": ", 1)
                data_dict[key.strip()] = value.strip()

        if st.session_state.selected_spreadsheet and st.session_state.sheet_client:
            try:
                client = st.session_state.sheet_client
                sheet = client.open_by_key(st.session_state.selected_spreadsheet["id"]).sheet1
                all_records = sheet.get_all_values()
                headers = all_records[0] if all_records else []

                if headers:
                    analyzed_text = "\n".join([f"{h}: {data_dict.get(h, '')}" for h in headers])
                else:
                    analyzed_text = output_text
            except Exception as e:
                analyzed_text = output_text + f"\n\n(⚠️ Gagal membaca header: {e})"
        else:
            analyzed_text = output_text

        st.subheader("📌 Hasil Analisa")
        st.text(analyzed_text)

        # -------------------------
        # Simpan ke Google Sheets
        # -------------------------
        if "ERROR" in output_text:
            st.warning("⚠️ Data tidak bisa disimpan karena error analisa.")
        else:
            if st.session_state.selected_spreadsheet and st.session_state.sheet_client:
                try:
                    client = st.session_state.sheet_client
                    sheet = client.open_by_key(st.session_state.selected_spreadsheet["id"]).sheet1
                    all_records = sheet.get_all_values()
                    headers = all_records[0] if all_records else []
                    unique_column = st.session_state.get("unique_column", None)

                    if not headers:
                        st.error("❌ Spreadsheet tidak memiliki header.")
                    elif not unique_column or unique_column not in headers:
                        st.error(f"❌ Kolom unik '{unique_column}' tidak ditemukan di spreadsheet!")
                    else:
                        col_index = headers.index(unique_column)
                        values = [r[col_index] for r in all_records[1:]] if len(all_records) > 1 else []

                        # Buat row baru sesuai urutan header
                        new_row = [data_dict.get(h, "") for h in headers]

                        key_value = data_dict.get(unique_column, "")

                        if key_value in values:
                            row_index = values.index(key_value) + 2  # +2 karena ada header
                            sheet.update(f"A{row_index}:{chr(64+len(headers))}{row_index}", [new_row])
                            st.success(f"✅ Data dengan {unique_column} '{key_value}' berhasil DIUPDATE!")
                        else:
                            sheet.append_row(new_row)
                            st.success(f"✅ Data baru berhasil ditambahkan (kolom unik: {unique_column}).")

                except Exception as e:
                    st.error(f"❌ Gagal menyimpan ke Google Sheet: {e}")

















