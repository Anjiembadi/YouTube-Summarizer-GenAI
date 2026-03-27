SUMMARY_PROMPT = """
You are a helpful AI assistant.

Summarize the following YouTube transcript in a clear and concise way.

Requirements:
- Write a short summary in 5 to 7 lines
- Then provide 5 bullet point key takeaways
- Keep the language simple
- Stay faithful to the transcript

Transcript:
{transcript}
"""

ARTICLE_PROMPT = """
You are a content writer.

Convert the following YouTube transcript into a well-structured article in Markdown format.

Requirements:
- Create a strong title
- Write a short introduction
- Organize content using proper headings and subheadings
- Make the article clear, readable, and informative
- End with a conclusion
- Do not invent information not present in the transcript

Transcript:
{transcript}
"""