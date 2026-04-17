# 📖 Business Data Dictionary for Unity Catalog

An enterprise-grade, business-friendly frontend for navigating Databricks Unity Catalog metadata. This application bridges the gap between technical data engineering and business users by providing a searchable, digestable, and securely filtered view of your organization's data assets.

## 🎯 Project Goals

*   **Business Accessibility:** Provide a non-technical interface for business users to find data without navigating the Databricks workspace.
*   **Secure by Design:** Leverage **Microsoft Entra ID (Active Directory)** to ensure users only see metadata for data assets they are authorized to access in Unity Catalog.
*   **High Performance:** Use a "Synced Search Engine" approach powered by a **Databricks SQL Warehouse** to provide a lightning-fast search experience.
*   **Python Native:** Built entirely in Python to leverage existing team expertise in data science and engineering.

## 🏗️ Architecture

The solution consists of three main components:

1.  **Frontend (Streamlit):** A modern web application built in Python that handles user authentication and provides the search interface.
2.  **Metadata Cache (Databricks SQL Warehouse):** A dedicated schema in Unity Catalog that stores optimized, searchable metadata and permission ACLs.
3.  **Sync Job (Databricks SDK):** A background process that periodically extracts structural metadata and permission grants from Unity Catalog and updates the cache.

## 🛠️ Tech Stack

*   **UI/Application:** [Streamlit](https://streamlit.io/)
*   **Authentication:** Microsoft Entra ID (via `msal`)
*   **Data Integration:** [Databricks SDK for Python](https://github.com/databricks/databricks-sdk-python)
*   **Database:** Databricks Serverless SQL Warehouse
*   **Connectivity:** `databricks-sql-connector`

## 🚀 Getting Started

### 1. Prerequisites
*   Python 3.9+
*   A Databricks Workspace with Unity Catalog enabled.
*   A Microsoft Entra ID (Azure AD) Tenant with permission to create an App Registration.

### 2. Installation
```bash
# Clone the repository
git clone <repository-url>
cd datadictionnary

# Install dependencies
pip install -r requirements.txt
```

### 3. Configuration
1.  Copy the example environment file:
    ```bash
    cp .env.example .env
    ```
2.  Fill in your **Databricks** (Host, Token, SQL HTTP Path) and **Entra ID** (Client ID, Tenant ID) credentials.

### 4. Running the App
```bash
streamlit run app.py
```

## 📅 Roadmap
- [x] **Phase 1:** UI Scaffolding & Project Structure
- [ ] **Phase 2:** Metadata Sync Job (Unity Catalog -> SQL Warehouse)
- [ ] **Phase 3:** Entra ID Integration & Permission-Trimmed Search
- [ ] **Phase 4:** Advanced Features (Lineage visualization, Data Quality tags)
