import streamlit as st
import os
from dotenv import load_dotenv
import zipfile


from summarizer import smart_summarizer 

load_dotenv()

st.set_page_config(page_title="YouTube → Article → Website", layout="wide")

st.title("YouTube to Article & Website Generator")
st.markdown("Convert YouTube videos into **professional articles + full webpage (HTML/CSS/JS)**")

youtube_url = st.text_input(" Enter YouTube Video URL")

generate_btn = st.button(" Generate")

if generate_btn:
    if not youtube_url:
        st.warning(" Please enter a YouTube URL")
    else:
        with st.spinner("⏳ Processing... Fetching transcript + generating article..."):

            try:
                result = smart_summarizer.invoke(youtube_url)

                if not result:
                    st.error("No output generated")
                else:
                    st.success("Generation Completed!")

                    # ------------------- SPLIT OUTPUT -------------------
                    try:
                        html = result.split('--html--')[1].split('--css--')[0]
                        css = result.split('--css--')[1].split('--js--')[0]
                        js = result.split('--js--')[1]

                        tab1, tab2, tab3 = st.tabs(["HTML", "CSS", "JS"])

                        with tab1:
                            st.code(html, language="html")

                        with tab2:
                            st.code(css, language="css")

                        with tab3:
                            st.code(js, language="javascript")

                        with open("index.html", "w", encoding="utf-8") as f:
                            f.write(html)

                        with open("style.css", "w", encoding="utf-8") as f:
                            f.write(css)

                        with open("script.js", "w", encoding="utf-8") as f:
                            f.write(js)

                        zip_filename = "website.zip"
                        with zipfile.ZipFile(zip_filename, 'w') as zipf:
                            zipf.write("index.html")
                            zipf.write("style.css")
                            zipf.write("script.js")

                        with open(zip_filename, "rb") as f:
                            st.download_button(
                                "Download Website ZIP",
                                f,
                                file_name="website.zip",
                                mime="application/zip"
                            )

                    except Exception as e:
                        st.error(f"Error parsing output: {e}")

            except Exception as e:
                st.error(f"Processing failed: {e}")
