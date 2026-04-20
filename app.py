import os
import re
import time

import markdown
import streamlit as st
from dotenv import load_dotenv
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.proxies import WebshareProxyConfig
import google.generativeai as genai


st.set_page_config(
    page_title="YouTube Summarizer GenAI",
    page_icon="🎥",
    layout="wide"
)

load_dotenv()

GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")
PROXY_USERNAME = st.secrets.get("PROXY_USERNAME") or os.getenv("PROXY_USERNAME")
PROXY_PASSWORD = st.secrets.get("PROXY_PASSWORD") or os.getenv("PROXY_PASSWORD")

if not GEMINI_API_KEY:
    st.error("GEMINI_API_KEY not found. Add it in Streamlit Secrets.")
    st.stop()

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

DEFAULT_STATE = {
    "video_id": "",
    "transcript": "",
    "summary": "",
    "article_md": "",
    "article_html": "",
    "generated": False,
    "processing": False,
    "fetch_error": "",
}

for key, value in DEFAULT_STATE.items():
    if key not in st.session_state:
        st.session_state[key] = value


def extract_video_id(url: str) -> str:
    patterns = [
        r"(?:v=|/)([0-9A-Za-z_-]{11}).*",
        r"youtu\.be/([0-9A-Za-z_-]{11})",
        r"youtube\.com/shorts/([0-9A-Za-z_-]{11})"
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
                    proxy_password=PROXY_PASSWORD
                )
            )
        else:
            api = YouTubeTranscriptApi()

        transcript = api.fetch(video_id)
        transcript_text = " ".join(
            item.text if hasattr(item, "text") else item["text"]
            for item in transcript
        )
        return transcript_text

    except Exception as e:
        raise RuntimeError(
            "Automatic transcript fetch failed.\n\n"
            "Possible reasons:\n"
            "1. YouTube blocked the current server/proxy IP.\n"
            "2. The video has no accessible captions.\n"
            "3. The video is restricted or unavailable.\n\n"
            "Paste the transcript manually below and continue.\n\n"
            f"Details: {e}"
        )


def clean_transcript(text: str) -> str:
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def markdown_to_html(markdown_text: str) -> str:
    return markdown.markdown(markdown_text)


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
                    wait_time = 20
                    st.warning(f"Quota reached. Waiting {wait_time} seconds before retry...")
                    time.sleep(wait_time)
                    continue

                raise RuntimeError("Free Gemini quota reached. Please wait and try again.")

            raise RuntimeError(f"LLM Error: {e}")


def generate_summary_and_article(transcript: str) -> tuple[str, str]:
    shortened_transcript = transcript[:6000]

    prompt = f"""
You are an expert content writer and summarizer.

From the transcript below, do the following:

1. Write a short summary in 5 to 7 lines.
2. Write 5 key takeaways.
3. Write a clear beginner-friendly article in markdown.

Return exactly in this format:

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
Article here

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


def process_transcript_input(transcript_text: str) -> None:
    cleaned_transcript = clean_transcript(transcript_text)

    if not cleaned_transcript:
        raise RuntimeError("Transcript is empty after cleaning.")

    st.session_state.transcript = cleaned_transcript

    summary, article_md = generate_summary_and_article(cleaned_transcript)
    article_html = markdown_to_html(article_md)

    st.session_state.summary = summary
    st.session_state.article_md = article_md
    st.session_state.article_html = article_html
    st.session_state.generated = True


st.title("🎥 YouTube Summarizer GenAI")
st.write("Paste a YouTube link to generate transcript, summary, and article.")

st.info(
    "If automatic transcript fetching fails because YouTube blocks the server IP, "
    "you can paste the transcript manually and still generate the output."
)

with st.sidebar:
    st.subheader("Configuration")
    st.write("Proxy configured:", bool(PROXY_USERNAME and PROXY_PASSWORD))
    st.write("Gemini key loaded:", bool(GEMINI_API_KEY))

youtube_url = st.text_input("Paste YouTube Video URL")
manual_transcript = st.text_area(
    "Manual Transcript Fallback",
    height=220,
    placeholder="If automatic transcript fetch fails, paste the transcript here and click Generate Content."
)

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
    st.session_state.fetch_error = ""

    try:
        with st.spinner("Processing..."):
            transcript_text = ""

            if youtube_url.strip():
                try:
                    video_id = extract_video_id(youtube_url)
                    st.session_state.video_id = video_id
                    transcript_text = fetch_transcript(video_id)
                    st.success("Transcript fetched automatically.")
                except Exception as e:
                    st.session_state.fetch_error = str(e)
                    st.warning("Automatic transcript fetch failed.")

            if not transcript_text:
                if manual_transcript.strip():
                    transcript_text = manual_transcript
                    st.info("Using manually pasted transcript.")
                else:
                    if st.session_state.fetch_error:
                        raise RuntimeError(st.session_state.fetch_error)
                    raise RuntimeError("Please enter a YouTube URL or paste a transcript manually.")

            process_transcript_input(transcript_text)
            st.success("Content generated successfully.")

    except Exception as e:
        st.error(str(e))

    finally:
        st.session_state.processing = False

if st.session_state.fetch_error:
    with st.expander("Show transcript fetch error"):
        st.code(st.session_state.fetch_error)

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
