import os
import re
from pathlib import Path

from dotenv import load_dotenv
from youtube_transcript_api import YouTubeTranscriptApi
import google.generativeai as genai
import markdown

from prompts import SUMMARY_PROMPT, ARTICLE_PROMPT


# -----------------------------
# Load environment variables
# -----------------------------
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY not found in .env file")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")


import time

def call_llm(prompt: str) -> str:
    try:
        time.sleep(6)  # safe delay
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"LLM Error: {e}"
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


def chunk_text(text: str, max_chars: int = 12000) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + max_chars
        chunks.append(text[start:end])
        start = end
    return chunks


def call_llm(prompt: str) -> str:
    response = model.generate_content(prompt)
    return response.text.strip()


def summarize_long_transcript(transcript: str) -> str:
    if len(transcript) <= 12000:
        prompt = SUMMARY_PROMPT.format(transcript=transcript)
        return call_llm(prompt)

    chunks = chunk_text(transcript, max_chars=12000)
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
    if len(transcript) <= 12000:
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


def save_text_file(content: str, filepath: Path) -> None:
    filepath.write_text(content, encoding="utf-8")


def markdown_to_html(markdown_text: str) -> str:
    return markdown.markdown(markdown_text)


# -----------------------------
# Main pipeline
# -----------------------------
def main():
    print("\n=== YouTube Transcript Summarizer ===\n")
    url = input("Enter YouTube video URL: ").strip()

    try:
        print("\n[1] Extracting video ID...")
        video_id = extract_video_id(url)
        print(f"Video ID: {video_id}")

        print("\n[2] Fetching transcript...")
        transcript = fetch_transcript(video_id)

        print("\n[3] Cleaning transcript...")
        cleaned_transcript = clean_transcript(transcript)

        output_dir = Path("output")
        output_dir.mkdir(exist_ok=True)

        transcript_file = output_dir / "transcript.txt"
        summary_file = output_dir / "summary.txt"
        article_md_file = output_dir / "article.md"
        article_html_file = output_dir / "article.html"

        print("\n[4] Saving transcript...")
        save_text_file(cleaned_transcript, transcript_file)

        print("\n[5] Generating summary...")
        summary = summarize_long_transcript(cleaned_transcript)
        save_text_file(summary, summary_file)

        print("\n[6] Generating article in Markdown...")
        article_md = generate_article(cleaned_transcript)
        save_text_file(article_md, article_md_file)

        print("\n[7] Converting Markdown to HTML...")
        article_html = markdown_to_html(article_md)
        save_text_file(article_html, article_html_file)

        print("\n=== Done Successfully ===")
        print(f"Transcript saved at  : {transcript_file}")
        print(f"Summary saved at     : {summary_file}")
        print(f"Article MD saved at  : {article_md_file}")
        print(f"Article HTML saved at: {article_html_file}")

        print("\n--- Summary Preview ---")
        print(summary[:1000])

    except Exception as e:
        print(f"\nError: {e}")


if __name__ == "__main__":
    main()