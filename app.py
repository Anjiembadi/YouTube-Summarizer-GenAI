import os
import re
from pathlib import Path

import markdown
import streamlit as st
from dotenv import load_dotenv
from youtube_transcript_api import YouTubeTranscriptApi
import google.generativeai as genai



st.set_page_config(
    page_title="YouTube Summarizer GenAI",
    page_icon="🎥",
    layout="wide"
)



load_dotenv()

GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", None) or os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    st.error(
        "GEMINI_API_KEY not found. "
        "For local use, add it in .env. "
        "For Streamlit Cloud, add it in App Settings -> Secrets."
    )
    st.stop()

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")


DEFAULT_STATE = {
    "source_mode": "YouTube URL",
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
    """
    Best-effort transcript fetch.
    Works locally more reliably.
    Can fail on Streamlit Cloud due to YouTube blocking cloud IPs.
    """
    try:
        api = YouTubeTranscriptApi()
        transcript = api.fetch(video_id)
        transcript_text = " ".join(
            item.text if hasattr(item, "text") else item["text"]
            for item in transcript
        )
        return transcript_text

    except Exception as e:
        error_text = str(e)

        if (
            "blocking requests from your IP" in error_text.lower()
            or "ip" in error_text.lower()
            or "requestblocked" in error_text.lower()
            or "could not retrieve a transcript" in error_text.lower()
        ):
            raise RuntimeError(
                "Could not fetch transcript from YouTube in the deployed app. "
                "This usually happens because YouTube blocks requests from cloud server IPs. "
                "Use the 'Paste Transcript' or 'Upload Transcript File' option on Streamlit Cloud."
            )

        raise RuntimeError(f"Failed to fetch transcript: {e}")


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
    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        error_message = str(e)

        if "429" in error_message or "quota" in error_message.lower():
            raise RuntimeError(
                "Gemini quota exceeded for this API key/project. "
                "Please wait 1-2 minutes and try again."
            )

        raise RuntimeError(f"LLM Error: {e}")


def generate_summary_and_article(transcript: str) -> tuple[str, str]:
    """
    Single Gemini call to reduce quota usage.
    """
    shortened_transcript = transcript[:12000]

    prompt = f"""
You are an expert technical content writer.

From the transcript below, do all tasks carefully.

TASK 1:
Write a short summary in 5 to 7 lines.

TASK 2:
Write 5 bullet point key takeaways.

TASK 3:
Write a detailed article in Markdown format.

Requirements for article:
- Add a suitable title
- Add an introduction
- Add proper section headings
- Add a conclusion
- Keep it professional, readable, clear, and beginner-friendly

Return output EXACTLY in this format:

===SUMMARY===
<short summary here>

===KEY TAKEAWAYS===
- point 1
- point 2
- point 3
- point 4
- point 5

===ARTICLE===
# Title
Article content in markdown...

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



st.title("YouTube Summarizer GenAI")
st.write("Convert a transcript into a summary and article-style content.")

source_mode = st.radio(
    "Choose input method",
    ["YouTube URL", "Paste Transcript", "Upload Transcript File"],
    horizontal=True
)
st.session_state.source_mode = source_mode

input_transcript = ""
youtube_url = ""
uploaded_file = None

if source_mode == "YouTube URL":
    st.info(
        "Note: On Streamlit Cloud, YouTube transcript fetching may fail because "
        "YouTube often blocks cloud-provider IPs. If that happens, use Paste Transcript."
    )
    youtube_url = st.text_input("Paste YouTube Video URL")

elif source_mode == "Paste Transcript":
    input_transcript = st.text_area(
        "Paste transcript here",
        height=250,
        placeholder="Paste the full transcript text here..."
    )

else:
    uploaded_file = st.file_uploader(
        "Upload transcript file (.txt)",
        type=["txt"]
    )

col1, col2 = st.columns(2)

with col1:
    generate_btn = st.button(
        "Generate Content",
        use_container_width=True,
        disabled=st.session_state.processing
    )

with col2:
    clear_btn = st.button("Clear", use_container_width=True)

if clear_btn:
    clear_app()
    st.rerun()

if generate_btn and not st.session_state.generated:
    st.session_state.processing = True

    try:
        with st.spinner("Processing..."):

            # -----------------------------
            # Get transcript based on source
            # -----------------------------
            if source_mode == "YouTube URL":
                if not youtube_url.strip():
                    st.warning("Please enter a YouTube URL.")
                    st.stop()

                st.subheader("Step 1: Extracting Video ID")
                video_id = extract_video_id(youtube_url)
                st.session_state.video_id = video_id
                st.success(f"Video ID: {video_id}")

                st.subheader("Step 2: Fetching Transcript")
                transcript = fetch_transcript(video_id)

            elif source_mode == "Paste Transcript":
                if not input_transcript.strip():
                    st.warning("Please paste a transcript.")
                    st.stop()

                transcript = input_transcript

            else:
                if uploaded_file is None:
                    st.warning("Please upload a transcript file.")
                    st.stop()

                transcript = uploaded_file.read().decode("utf-8", errors="ignore")

            st.subheader("Step 3: Cleaning Transcript")
            cleaned_transcript = clean_transcript(transcript)

            if not cleaned_transcript:
                raise RuntimeError("Transcript is empty after cleaning.")

            st.session_state.transcript = cleaned_transcript

            st.subheader("Step 4: Generating Summary + Article")
            summary, article_md = generate_summary_and_article(cleaned_transcript)

            st.subheader("Step 5: Converting Markdown to HTML")
            article_html = markdown_to_html(article_md)

            st.session_state.summary = summary
            st.session_state.article_md = article_md
            st.session_state.article_html = article_html
            st.session_state.generated = True

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



if st.session_state.generated:
    tab1, tab2, tab3, tab4 = st.tabs([
        "Summary",
        "Article (Markdown)",
        "Article (HTML Preview)",
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
