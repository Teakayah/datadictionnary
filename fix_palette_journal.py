with open(".jules/palette.md", "r") as f:
    lines = f.readlines()
with open(".jules/palette.md", "w") as f:
    f.writelines([line for line in lines if "Empty state polish" not in line and "Replace `st.info` with custom styled" not in line])
