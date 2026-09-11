import streamlit as st
import os
import sys
import uuid

# Ensure the app can import from shorts_generator
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit.components.v1 as components

from shorts_generator import generate_shorts
from shorts_generator.config import LOCAL_OUTPUT_DIR, GCS_OUTPUT_BUCKET

st.set_page_config(
    page_title="AI YouTube Shorts Generator",
    page_icon="🎬",
    layout="wide"
)

st.title("🎬 AI YouTube Shorts Generator")
st.markdown("Transform long YouTube videos into viral-ready 9:16 shorts instantly.")

# Sidebar Configuration
with st.sidebar:
    st.header("⚙️ Configuration")
    
    mode = st.radio(
        "Processing Mode",
        ["local", "api"],
        index=0,
        help="'local' runs entirely on your machine. 'api' uses MuAPI cloud."
    )
    
    num_clips = st.number_input(
        "Number of Clips",
        min_value=1,
        max_value=10,
        value=3,
        help="How many shorts to generate."
    )
    
    aspect_ratio = st.selectbox(
        "Aspect Ratio",
        ["9:16", "1:1", "16:9"],
        index=0,
        help="9:16 for TikTok/Reels, 1:1 for square."
    )
    
    download_format = st.selectbox(
        "Source Resolution",
        ["360", "480", "720", "1080"],
        index=2,
        help="Quality of the downloaded video before cropping."
    )
    
    language = st.text_input(
        "Language Override (Optional)",
        value="",
        placeholder="e.g. 'en', 'pt'",
        help="Force Whisper language code. Leave empty for auto-detect."
    )

st.divider()

source_kind = st.radio(
    "Fonte do vídeo",
    ["🔗 URL do YouTube", "📤 Enviar arquivo"],
    index=0,
    horizontal=True,
    help="Na nuvem, prefira 'Enviar arquivo' — baixar por URL pode ser bloqueado pelo YouTube (detecção de bot em IPs de datacenter). Baixe localmente e envie o arquivo aqui.",
)

url = None
uploaded_file = None
gcs_upload_blob = None
upload_confirmed = False

if source_kind == "🔗 URL do YouTube":
    url = st.text_input("🔗 Paste YouTube URL or local file path here", placeholder="https://www.youtube.com/watch?v=...")
elif GCS_OUTPUT_BUCKET:
    # Cloud Run caps request bodies at ~32MB, so a real source video can't go
    # through st.file_uploader (which POSTs through the same Cloud Run
    # request path). Instead the browser uploads straight to GCS with a
    # signed PUT URL, bypassing Cloud Run entirely for the file bytes.
    from shorts_generator.local.storage import generate_upload_url

    if "upload_blob_name" not in st.session_state:
        st.session_state.upload_blob_name = f"uploads/{uuid.uuid4().hex}.mp4"
    gcs_upload_blob = st.session_state.upload_blob_name
    upload_url = generate_upload_url(gcs_upload_blob)

    components.html(
        f"""
        <div style="font-family: sans-serif;">
          <input type="file" id="videoFile" accept="video/*" style="margin-bottom:8px;">
          <button id="uploadBtn" style="padding:6px 16px; cursor:pointer;">📤 Enviar pro bucket</button>
          <p id="uploadStatus" style="margin-top:8px;"></p>
        </div>
        <script>
        document.getElementById('uploadBtn').onclick = async () => {{
          const file = document.getElementById('videoFile').files[0];
          const status = document.getElementById('uploadStatus');
          if (!file) {{ status.innerText = "Selecione um arquivo primeiro."; return; }}
          status.innerText = "Enviando... pode levar alguns minutos para arquivos grandes.";
          try {{
            const resp = await fetch("{upload_url}", {{ method: 'PUT', body: file }});
            if (resp.ok) {{
              status.innerText = "✅ Upload completo! Marque a confirmação abaixo e clique em Generate Shorts.";
            }} else {{
              status.innerText = "❌ Erro no upload: " + resp.status + " " + await resp.text();
            }}
          }} catch (e) {{
            status.innerText = "❌ Erro no upload: " + e;
          }}
        }};
        </script>
        """,
        height=150,
    )
    upload_confirmed = st.checkbox("✅ Já terminei o upload acima (vi a mensagem de sucesso)")
else:
    uploaded_file = st.file_uploader(
        "📤 Selecione o vídeo",
        type=["mp4", "mov", "mkv", "webm", "m4v"],
    )

if st.button("🚀 Generate Shorts", type="primary", use_container_width=True):
    if source_kind == "🔗 URL do YouTube" and not url:
        st.warning("Please enter a valid URL or path.")
    elif source_kind == "📤 Enviar arquivo" and GCS_OUTPUT_BUCKET and not upload_confirmed:
        st.warning("Envie o arquivo acima e marque a confirmação antes de continuar.")
    elif source_kind == "📤 Enviar arquivo" and not GCS_OUTPUT_BUCKET and not uploaded_file:
        st.warning("Selecione um arquivo de vídeo para continuar.")
    else:
        if uploaded_file is not None:
            os.makedirs(LOCAL_OUTPUT_DIR, exist_ok=True)
            ext = os.path.splitext(uploaded_file.name)[1] or ".mp4"
            url = os.path.join(LOCAL_OUTPUT_DIR, f"upload_{uuid.uuid4().hex}{ext}")
            with open(url, "wb") as f:
                f.write(uploaded_file.getbuffer())
        elif gcs_upload_blob is not None:
            from shorts_generator.local.storage import download_to_file

            os.makedirs(LOCAL_OUTPUT_DIR, exist_ok=True)
            url = os.path.join(LOCAL_OUTPUT_DIR, f"upload_{uuid.uuid4().hex}.mp4")
            download_status = st.empty()
            download_status.info("Baixando o arquivo enviado...")
            download_to_file(gcs_upload_blob, url)
            del st.session_state["upload_blob_name"]
        # Provide feedback
        status_text = st.empty()
        status_text.info("Downloading and processing... this may take a few minutes. Check the terminal for detailed logs.")
        
        try:
            # We must configure env properly since streamlit doesn't load .profile
            if mode == "local":
                # Ensure ffmpeg from brew is found
                if "/opt/homebrew/bin" not in os.environ.get("PATH", ""):
                    os.environ["PATH"] = f"/opt/homebrew/bin:{os.environ.get('PATH', '')}"
            
            lang_param = language.strip() if language.strip() else None
            
            with st.spinner("Analyzing audio and searching for viral hooks..."):
                result = generate_shorts(
                    youtube_url=url,
                    num_clips=int(num_clips),
                    aspect_ratio=aspect_ratio,
                    download_format=download_format,
                    language=lang_param,
                    mode=mode,
                )
                
            status_text.success("Generation complete!")
            
            st.header("✨ Your Viral Shorts")
            
            if not result.get("shorts"):
                st.warning("No shorts were generated. Check the logs for errors.")
            else:
                # Display shorts in columns
                cols = st.columns(min(len(result["shorts"]), 3))
                
                for i, short in enumerate(result["shorts"]):
                    col_idx = i % 3
                    with cols[col_idx]:
                        st.subheader(f"#{i+1} - Score: {short.get('score', 'N/A')}")
                        st.markdown(f"**Title:** {short.get('title')}")
                        st.markdown(f"**Hook:** _{short.get('hook_sentence')}_")
                        
                        clip_url = short.get("clip_url")
                        if clip_url:
                            # Render video
                            try:
                                st.video(clip_url)
                            except Exception as e:
                                st.error(f"Could not load video: {e}")
                                st.code(clip_url)
                        else:
                            st.error(f"Failed to clip: {short.get('error', 'Unknown Error')}")
                            
        except Exception as e:
            status_text.error(f"An error occurred: {e}")
            st.exception(e)
