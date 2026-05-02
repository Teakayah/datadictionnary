with open("app.py", "r") as f:
    app_content = f.read()

# Fix the dangling else:
app_content = app_content.replace("""        st.markdown("</div>", unsafe_allow_html=True)
        render_footer()
        st.stop()
else:
    check_auth()""", """        st.markdown("</div>", unsafe_allow_html=True)
        render_footer()
        st.stop()
    else:
        check_auth()
""")

with open("app.py", "w") as f:
    f.write(app_content)
