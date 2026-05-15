# Personalization & User Profiles

The Data Dictionary builds user profiles to deliver a personalized experience through "Recommended" assets, "Recently Viewed" history, and "New & Notable" highlights.

---

## How it works

Personalization is driven by two data streams: **User Preferences** (private to the user) and **Audit Logs** (aggregated for the group).

### 1. User Preferences (Passive & Explicit)
Stored in the `user_data.user_preferences` table.
- **Bookmarks (Explicit):** When a user stars a table or column, it is saved with `pref_type='bookmark'`.
- **Recent History (Passive):** Every time a user opens a table detail page, the app automatically upserts a `pref_type='recent'` entry.
- **Persistence:** These are tied to the user's Entra ID Object ID (`user_oid`).

### 2. Audit Logs (Group Activity)
Stored in the `user_data.audit_log` table.
- **Active Interactions:** Events like `table_description_change`, `business_name_change`, and `comment_added` are logged with the table name and the actor's email.
- **Popularity Signals:** The "Recommended" algorithm aggregates these logs to identify which data assets are generating the most "buzz" within the organization.

---

## Discovery Tabs

| Tab | Profile Engine | Logic |
|-----|----------------|-------|
| **My Bookmarks** | Explicit Preferences | Shows everything the user has manually starred. |
| **Recently Viewed** | Passive Preferences | Shows the last 50 tables the user has opened, most recent first. |
| **Recommended** | Audit Log Aggregation | Identifies popular tables based on recent edits and comments. It **excludes** tables the user has already viewed recently to ensure discovery of *new* assets. |
| **New & Notable** | Group-based Metadata | Shows the most recently updated tables that the user's primary group has access to. |

---

## Testing Profile Building

To verify that profiles are correctly building up:
1. **Navigate** to several tables. Verify they appear in the **Recently Viewed** tab.
2. **Comment** on or **Edit** a table.
3. In a separate session (or as another user in the same group), verify that the table now appears higher in the **Recommended** tab (it may take a cache refresh or a few more interactions to surface if the catalog is large).
