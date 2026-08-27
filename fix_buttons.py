import re
import os

files_to_update = ["src/ui/cards/pipelines.py", "src/ui/cards/cms_admin.py", "src/ui/cards/detail.py", "src/pages/glossary.py"]

for filepath in files_to_update:
    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
            content = f.read()

        # Find buttons lacking aria labels where icons might be the only content
        # Note: we need to parse carefully.
        # For simplicity, we just add aria-label if we have an icon-only button like "＋" or "⤢" or similar.

        content = re.sub(r'st\.button\("＋"', r'st.button("＋", aria_label=t("cms.new_post") if "cms_new_post" in \g<0> else t("pipelines.new_pipeline")', content)
        # However, st.button doesn't natively support aria-label. Streamlit buttons use `help` for tooltips.
        # So we should look for accessibility things to do...
