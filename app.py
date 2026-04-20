import os
import re
import time
from pathlib import Path

import markdown
import streamlit as st
from dotenv import load_dotenv
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.proxies import WebshareProxyConfig
import google.generativeai as genai


# -------------------------------------------------
# Page config
# -------------------------------------------------
st.set_page_config(
    page_title="YouTube Summarizer GenAI",
    page_icon="🎥",
    layout="wide"
)


# -------------------------------------------------
# Load secrets / env
# -------------------------------------------------
load_dotenv()

GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", None) or os.getenv("GEMINI_API_KEY")
PROXY_USERNAME = st.secrets.get("PROXY_USERNAME", None) or os.getenv("PROXY_USERNAME")
PROXY_PASSWORD = st.secrets.get("PROXY_PASSWORD", None) or os.getenv("PROXY_PASSWORD")

if not GEMINI_API_KEY:
    st.error("GEMINI_API_KEY not found. Add it in Streamlit App Settings -> Secrets.")
    st.stop()

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")


# -------------------------------------------------
# Session state
# -------------------------------------------------
DEFAULT_STATE = {
    "video_id": "",
    "transcript": "",
    "summary": "",
    "article_md": "",
    "article_html": "",
    "generated": False,
    "processing": False,
}

for key, value in DEFAULT_STATE.items():
    if key not in st.session_state:
        st.session_state[key] = value


# -------------------------------------------------
# Helper functions
# -------------------------------------------------
def extract_video_id(url: str) -> str:
    patterns = [
        r"(?:v=|\/)([0-9A-Za-z_-]{11}).*",
        r"youtu\.be\/([0-9A-Za-z_-]{11})",
        r"youtube\.com\/shorts\/([0-9A-Za-z_-]{11})"
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)

    raise ValueError("Invalid YouTube URL or unable to extract video ID.")


@st.cache_data(show_spinner=False)
def fetch_transcript(video_id: str) -> str:
    try:
        if PROXY_USERNAME and PROXY_PASSWORD:
            api = YouTubeTranscriptApi(
                proxy_config=WebshareProxyConfig(
                    proxy_username=PROXY_USERNAME,
                    proxy_password=PROXY_PASSWORD,
                    filter_ip_locations=["in", "sg", "us"]
                )
            )
        else:
            api = YouTubeTranscriptApi()

        transcript = api.fetch(video_id, languages=["en"])
        transcript_text = " ".join(
            item.text if hasattr(item, "text") else item["text"]
            for item in transcript
        )
        return transcript_text

    except Exception as e:
        raise RuntimeError(
            "Failed to fetch transcript. "
            "Possible reasons:\n"
            "1. The video has no accessible English captions.\n"
            "2. YouTube blocked the current server/proxy IP.\n"
            "3. The video is restricted or unavailable.\n\n"
            f"Details: {e}"
        )


def clean_transcript(text: str) -> str:
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def markdown_to_html(markdown_text: str) -> str:
    return markdown.markdown(markdown_text)


def save_outputs(transcript: str, summary: str, article_md: str, article_html: str) -> None:
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    (output_dir / "transcript.txt").write_text(transcript, encoding="utf-8")
    (output_dir / "summary.txt").write_text(summary, encoding="utf-8")
    (output_dir / "article.md").write_text(article_md, encoding="utf-8")
    (output_dir / "article.html").write_text(article_html, encoding="utf-8")


def call_llm(prompt: str) -> str:
    max_retries = 2

    for attempt in range(max_retries):
        try:
            response = model.generate_content(prompt)

            if not hasattr(response, "text") or not response.text:
                raise RuntimeError("Gemini returned an empty response.")

            return response.text.strip()

        except Exception as e:
            error_message = str(e).lower()

            if "429" in error_message or "quota" in error_message or "resource_exhausted" in error_message:
                if attempt < max_retries - 1:
                    wait_time = 35
                    st.warning(f"Quota reached. Waiting {wait_time} seconds before retry...")
                    time.sleep(wait_time)
                    continue

                raise RuntimeError(
                    "Free Gemini quota reached. Please wait 1 minute and try again."
                )

            raise RuntimeError(f"LLM Error: {e}")



def generate_summary_and_article(transcript: str) -> tuple[str, str]:
    shortened_transcript = transcript[:2000]

    prompt = f"""
You are an expert content writer.

From the transcript below:

1. Write a short summary in 5 lines
2. Write 5 key takeaways
3. Write a short article in markdown

Keep it concise and beginner-friendly.

Return in this format:

===SUMMARY===
<summary>

===KEY TAKEAWAYS===
- point 1
- point 2
- point 3
- point 4
- point 5

===ARTICLE===
# Title
Short article here

Transcript:
{shortened_transcript}
"""

    result = call_llm(prompt)

    summary = ""
    article_md = ""

    if "===ARTICLE===" in result:
        parts = result.split("===ARTICLE===", 1)
        before_article = parts[0].strip()
        article_md = parts[1].strip()

        if "===SUMMARY===" in before_article:
            summary = before_article.replace("===SUMMARY===", "").strip()
            summary = summary.replace("===KEY TAKEAWAYS===", "\n\nKey Takeaways:\n").strip()
        else:
            summary = before_article.strip()
    else:
        summary = result.strip()
        article_md = "# Generated Article\n\nArticle could not be separated properly."

    return summary, article_md


def clear_app() -> None:
    for key, value in DEFAULT_STATE.items():
        st.session_state[key] = value
    st.cache_data.clear()


# -------------------------------------------------
# UI
# -------------------------------------------------
st.title("YouTube Summarizer GenAI")
st.write("Paste a YouTube link to generate transcript, summary, and article.")

st.info(
    "This deployed version uses proxy-based transcript fetching. "
    "If a video still fails, it may not have captions, or YouTube may be blocking the current proxy/server IP."
)

youtube_url = st.text_input("Paste YouTube Video URL")

col1, col2 = st.columns(2)

with col1:
    generate_btn = st.button(
        "Generate Content",
        use_container_width=True,
        disabled=st.session_state.processing
    )

with col2:
    clear_btn = st.button(
        "Clear",
        use_container_width=True,
        disabled=st.session_state.processing
    )

if clear_btn:
    clear_app()
    st.rerun()

if generate_btn:
    st.session_state.processing = True

    try:
        with st.spinner("Processing..."):
            if not youtube_url.strip():
                st.warning("Please enter a YouTube URL.")
                st.stop()

            # Step 1: Extract video ID
            video_id = extract_video_id(youtube_url)
            st.session_state.video_id = video_id

            # Step 2: Fetch transcript
            transcript = fetch_transcript(video_id)

            # Step 3: Clean transcript
            cleaned_transcript = clean_transcript(transcript)
            if not cleaned_transcript:
                raise RuntimeError("Transcript is empty after cleaning.")

            st.session_state.transcript = cleaned_transcript

            # Step 4: Generate summary + article
            summary, article_md = generate_summary_and_article(cleaned_transcript)
            article_html = markdown_to_html(article_md)

            st.session_state.summary = summary
            st.session_state.article_md = article_md
            st.session_state.article_html = article_html
            st.session_state.generated = True

            # Step 5: Save output files
            save_outputs(
                st.session_state.transcript,
                st.session_state.summary,
                st.session_state.article_md,
                st.session_state.article_html
            )

        st.success("Content generated successfully.")

    except Exception as e:
        st.error(str(e))

    finally:
        st.session_state.processing = False


# -------------------------------------------------
# Output section
# -------------------------------------------------
if st.session_state.generated:
    tab1, tab2, tab3, tab4 = st.tabs([
        "Summary",
        "Article (Markdown)",
        "Article Preview",
        "Transcript"
    ])

    with tab1:
        st.text_area("Generated Summary", st.session_state.summary, height=300)

    with tab2:
        st.text_area("Generated Markdown Article", st.session_state.article_md, height=400)

    with tab3:
        st.markdown(st.session_state.article_md)

    with tab4:
        st.text_area("Transcript", st.session_state.transcript, height=400)

    st.subheader("Download Files")
    d1, d2, d3 = st.columns(3)

    with d1:
        st.download_button(
            label="Download Summary",
            data=st.session_state.summary,
            file_name="summary.txt",
            mime="text/plain",
            use_container_width=True
        )

    with d2:
        st.download_button(
            label="Download Markdown",
            data=st.session_state.article_md,
            file_name="article.md",
            mime="text/markdown",
            use_container_width=True
        )

    with d3:
        st.download_button(
            label="Download HTML",
            data=st.session_state.article_html,
            file_name="article.html",
            mime="text/html",
            use_container_width=True
        )
