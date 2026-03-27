import os
import re
import time
from pathlib import Path

import streamlit as st
import markdown
from dotenv import load_dotenv
from youtube_transcript_api import YouTubeTranscriptApi
import google.generativeai as genai

from prompts import SUMMARY_PROMPT, ARTICLE_PROMPT


# -----------------------------
# Page config
# -----------------------------
st.set_page_config(
    page_title="YouTube Summarizer",
    page_icon="🎥",
    layout="wide"
)


# -----------------------------
# Load environment variables
# -----------------------------
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    st.error("GEMINI_API_KEY not found in .env file")
    st.stop()

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")


# -----------------------------
# Helper functions
# -----------------------------
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


def fetch_transcript(video_id: str) -> str:
    try:
        api = YouTubeTranscriptApi()
        transcript = api.fetch(video_id)

        transcript_text = " ".join(
            item.text if hasattr(item, "text") else item["text"]
            for item in transcript
        )
        return transcript_text

    except Exception as e:
        raise RuntimeError(f"Failed to fetch transcript: {e}")


def clean_transcript(text: str) -> str:
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def chunk_text(text: str, max_chars: int = 10000) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + max_chars
        chunks.append(text[start:end])
        start = end
    return chunks


def call_llm(prompt: str) -> str:
    try:
        time.sleep(6)
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        raise RuntimeError(f"LLM Error: {e}")


def summarize_long_transcript(transcript: str) -> str:
    if len(transcript) <= 10000:
        prompt = SUMMARY_PROMPT.format(transcript=transcript)
        return call_llm(prompt)

    chunks = chunk_text(transcript, max_chars=10000)
    chunk_summaries = []

    for i, chunk in enumerate(chunks, start=1):
        prompt = f"""
Summarize this transcript chunk clearly.

Requirements:
- Write 4 to 5 lines
- Keep only the important information

Chunk {i}:
{chunk}
"""
        chunk_summary = call_llm(prompt)
        chunk_summaries.append(chunk_summary)

    combined_summary_text = "\n".join(chunk_summaries)

    final_prompt = f"""
Below are partial summaries of a long YouTube transcript.

Create:
1. A final short summary in 5 to 7 lines
2. 5 bullet point key takeaways

Partial summaries:
{combined_summary_text}
"""
    return call_llm(final_prompt)


def generate_article(transcript: str) -> str:
    if len(transcript) <= 10000:
        prompt = ARTICLE_PROMPT.format(transcript=transcript)
        return call_llm(prompt)

    summary = summarize_long_transcript(transcript)
    prompt = f"""
Create a detailed article in Markdown format based on this YouTube summary.

Requirements:
- Add a suitable title
- Add introduction
- Add section headings
- Add conclusion
- Keep it professional and readable

Summary:
{summary}
"""
    return call_llm(prompt)


def markdown_to_html(markdown_text: str) -> str:
    return markdown.markdown(markdown_text)


def save_outputs(transcript: str, summary: str, article_md: str, article_html: str) -> None:
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    (output_dir / "transcript.txt").write_text(transcript, encoding="utf-8")
    (output_dir / "summary.txt").write_text(summary, encoding="utf-8")
    (output_dir / "article.md").write_text(article_md, encoding="utf-8")
    (output_dir / "article.html").write_text(article_html, encoding="utf-8")


# -----------------------------
# UI
# -----------------------------
st.title("🎥 YouTube Transcript Summarizer")
st.write("Convert a YouTube transcript into a short summary and article-style content.")

youtube_url = st.text_input("Paste YouTube Video URL")

col1, col2 = st.columns(2)
with col1:
    generate_btn = st.button("Generate Content", use_container_width=True)
with col2:
    clear_btn = st.button("Clear", use_container_width=True)

if clear_btn:
    st.rerun()

if generate_btn:
    if not youtube_url.strip():
        st.warning("Please enter a YouTube URL.")
    else:
        try:
            with st.spinner("Processing video..."):
                st.subheader("Step 1: Extracting Video ID")
                video_id = extract_video_id(youtube_url)
                st.success(f"Video ID: {video_id}")

                st.subheader("Step 2: Fetching Transcript")
                transcript = fetch_transcript(video_id)

                st.subheader("Step 3: Cleaning Transcript")
                cleaned_transcript = clean_transcript(transcript)

                st.subheader("Step 4: Generating Summary")
                summary = summarize_long_transcript(cleaned_transcript)

                st.subheader("Step 5: Generating Article")
                article_md = generate_article(cleaned_transcript)

                st.subheader("Step 6: Converting to HTML")
                article_html = markdown_to_html(article_md)

                save_outputs(cleaned_transcript, summary, article_md, article_html)

            st.success("Content generated successfully.")

            tab1, tab2, tab3, tab4 = st.tabs([
                "Summary",
                "Article (Markdown)",
                "Article (HTML Preview)",
                "Transcript"
            ])

            with tab1:
                st.text_area("Generated Summary", summary, height=300)

            with tab2:
                st.text_area("Generated Markdown Article", article_md, height=400)

            with tab3:
                st.markdown(article_md)

            with tab4:
                st.text_area("Transcript", cleaned_transcript, height=400)

            st.subheader("Download Files")
            d1, d2, d3 = st.columns(3)

            with d1:
                st.download_button(
                    label="Download Summary",
                    data=summary,
                    file_name="summary.txt",
                    mime="text/plain",
                    use_container_width=True
                )

            with d2:
                st.download_button(
                    label="Download Markdown",
                    data=article_md,
                    file_name="article.md",
                    mime="text/markdown",
                    use_container_width=True
                )

            with d3:
                st.download_button(
                    label="Download HTML",
                    data=article_html,
                    file_name="article.html",
                    mime="text/html",
                    use_container_width=True
                )

        except Exception as e:
            st.error(str(e))