# Locale key reference

All i18n keys available via the `t()` function, with English and French values side by side.

Keys are dot-separated paths into the locale JSON structure (e.g. `t("search.placeholder")`). Curly-brace tokens (e.g. `{count}`) are substituted by keyword arguments passed to `t()`.

---

## nav

| Key | EN | FR |
|-----|----|----|
| `nav.search` | Search | Recherche |
| `nav.catalog` | Catalog | Catalogue |
| `nav.discovery` | Discovery | Découverte |
| `nav.health` | Health | Santé |
| `nav.glossary` | Glossary | Glossaire |
| `nav.admin` | Admin | Admin |
| `nav.sign_out` | Sign out | Déconnexion |

---

## auth

| Key | EN | FR |
|-----|----|----|
| `auth.title` | A card catalog for your warehouse. | Un catalogue pour votre entrepôt. |
| `auth.subtitle` | Search tables, columns, and business terms across Unity Catalog — filtered to what you have permission to see. | Recherchez des tables, des colonnes et des termes métier dans Unity Catalog — filtrés selon vos accès. |
| `auth.sign_in_button` | Sign in with Entra ID | Se connecter avec Entra ID |
| `auth.mock_button` | Sign in with Entra ID (mock) | Se connecter avec Entra ID (démo) |
| `auth.signed_in_as` | Signed in as | Connecté en tant que |

---

## search

| Key | EN | FR |
|-----|----|----|
| `search.hero_title` | Search the catalog. | Rechercher dans le catalogue. |
| `search.hero_subtitle` | Find data assets across the organization. | Trouvez des données dans toute l'organisation. |
| `search.placeholder` | Search tables or columns... | Rechercher des tables ou des colonnes… |
| `search.results_count` | {count} results | {count} résultats |
| `search.no_results` | No results found for '{query}' | Aucun résultat pour « {query} » |
| `search.loading` | Searching... | Recherche en cours… |
| `search.eyebrow` | § Catalog search | § Recherche au catalogue |
| `search.load_error` | Error loading catalog. | Erreur lors du chargement du catalogue. |
| `search.public_tables_filter` | Showing publicly accessible tables | Affichage des tables accessibles à tous |
| `search.group_filter_active` | Filtered by group: {group} | Filtré par groupe : {group} |
| `search.view_details` | View details | Voir les détails |
| `search.back_to_results` | Back to results | Retour aux résultats |

---

## catalog

| Key | EN | FR |
|-----|----|----|
| `catalog.eyebrow` | § Catalog browser | § Navigateur de catalogue |
| `catalog.hero_title` | Explore the hierarchy. | Explorez la hiérarchie. |
| `catalog.hero_subtitle` | Drill down from catalogs to schemas and tables. | Naviguez des catalogues aux schémas et aux tables. |
| `catalog.no_catalogs` | No catalogs accessible. | Aucun catalogue accessible. |
| `catalog.load_error` | Could not load catalog hierarchy. | Impossible de charger la hiérarchie du catalogue. |

---

## table

| Key | EN | FR |
|-----|----|----|
| `table.columns` | Columns | Colonnes |
| `table.grants` | Grants | Permissions |
| `table.lineage` | Lineage | Lignage |
| `table.comments` | Comments | Commentaires |
| `table.business_name` | Business name | Nom métier |
| `table.description` | Description | Description |
| `table.type` | Type | Type |
| `table.open_in_databricks` | Open in Databricks | Ouvrir dans Databricks |

---

## detail

| Key | EN | FR |
|-----|----|----|
| `detail.section_columns` | § Columns | § Colonnes |
| `detail.section_grants` | § Group permissions | § Permissions des groupes |
| `detail.section_lineage` | § Lineage | § Lignage |
| `detail.section_comments` | § Comments | § Commentaires |
| `detail.section_related` | § Related tables | § Tables liées |
| `detail.title` | § Table detail | § Détails de la table |
| `detail.related_count` | related | liées |
| `detail.same_schema` | Same schema | Même schéma |
| `detail.shared_column` | Shared column | Colonne partagée |
| `detail.open_related` | Open → | Ouvrir → |
| `detail.search_tables_accessible` | Search tables accessible to: {principal} ({privilege}) | Rechercher les tables accessibles à: {principal} ({privilege}) |
| `detail.browse_public_tables` | Browse tables accessible to all users ({privilege}) | Parcourir les tables accessibles à tous ({privilege}) |
| `detail.load_error` | Error displaying details. | Erreur lors de l'affichage des détails. |
| `detail.preview_data` | Preview data | Aperçu des données |
| `detail.export_dictionary` | Export dictionary | Exporter le dictionnaire |
| `detail.edit_table` | Edit table metadata | Modifier les métadonnées |
| `detail.table_description` | Table description | Description de la table |
| `detail.steward_email` | Data steward email | Email du responsable |
| `detail.unauthorized` | You do not have permission to access this asset. | Vous n'avez pas la permission d'accéder à cet élément. |
| `detail.data_sample` | Data sample | Aperçu des données |
| `detail.lineage_graph` | Lineage graph | Graphe de lignage |
| `detail.lineage_graph_subtitle` | {table} — full lineage | {table} — lignage complet |
| `detail.preview_not_available` | Preview not available for this table in local mode. | Aperçu non disponible pour cette table en mode local. |
| `detail.preview_needs_data` | No row data found. Regenerate the test dataset with --with-data to enable preview. | Aucune donnée trouvée. Régénérez le jeu de test avec --with-data pour activer l'aperçu. |
| `detail.preview_error` | Could not fetch data sample. You may not have permission to view the underlying data. | Impossible de récupérer l'échantillon. Vous n'avez peut-être pas la permission d'accéder aux données. |

---

## comment

| Key | EN | FR |
|-----|----|----|
| `comment.add_comment` | Add a comment | Ajouter un commentaire |
| `comment.reply` | Reply | Répondre |
| `comment.save` | Save comment | Enregistrer le commentaire |
| `comment.cancel` | Cancel | Annuler |
| `comment.steward` | Steward | Responsable |
| `comment.posted_by` | Posted by | Posté par |
| `comment.no_comments` | No comments yet. | Aucun commentaire pour le moment. |
| `comment.leave_a_comment` | Leave a comment | Laisser un commentaire |

---

## editor

| Key | EN | FR |
|-----|----|----|
| `editor.edit_business_name` | Edit business name | Modifier le nom métier |
| `editor.business_name_label` | Business name | Nom métier |
| `editor.definition_label` | Definition | Définition |
| `editor.save` | Save | Enregistrer |
| `editor.cancel` | Cancel | Annuler |
| `editor.saved_by` | Saved by {user} | Enregistré par {user} |

---

## admin

| Key | EN | FR |
|-----|----|----|
| `admin.title` | § Admin | § Admin |
| `admin.subtitle` | System health, usage statistics, and sync logs. | Santé du système, statistiques d'utilisation et journaux de synchronisation. |
| `admin.stats_tables` | Total tables | Total tables |
| `admin.stats_columns` | Total columns | Total colonnes |
| `admin.stats_comments` | Total comments | Total commentaires |
| `admin.stats_overrides` | Business name overrides | Surcharges de noms métier |
| `admin.biz_log_title` | Business name change log | Historique des noms métier |
| `admin.comment_log_title` | Comment log | Historique des commentaires |
| `admin.sync_title` | Synchronization status | État de la synchronisation |
| `admin.no_data` | No audit data available. | Aucune donnée d'audit disponible. |
| `admin.access_denied` | Admin access required. | Accès administrateur requis. |

---

## health

| Key | EN | FR |
|-----|----|----|
| `health.title` | § Catalog health | § Santé du catalogue |
| `health.subtitle` | Coverage and documentation status across the catalog. | Couverture et état de la documentation. |
| `health.hero_title` | Documentation scorecard. | Tableau de bord documentaire. |
| `health.hero_subtitle` | Audit the completeness and quality of your catalog metadata. | Vérifiez la complétude et la qualité de vos métadonnées. |
| `health.total_tables` | Total tables | Total tables |
| `health.documented` | Documented | Documenté |
| `health.with_grants` | With grants | Avec permissions |
| `health.last_sync` | Last sync 04:12 UTC | Dernière synchro à 04:12 UTC |
| `health.table_coverage` | Table Coverage | Couverture des tables |
| `health.column_coverage` | Column Coverage | Couverture des colonnes |
| `health.freshness_index` | Freshness Index | Indice de fraîcheur |
| `health.tables_described` | {n_desc} of {n_tables} described | {n_desc} sur {n_tables} décrites |
| `health.columns_defined` | {n_col_desc} of {n_cols} defined | {n_col_desc} sur {n_cols} définies |
| `health.no_data` | No data accessible to audit. | Aucune donnée accessible à auditer. |
| `health.missing_descriptions` | The following tables are missing descriptions. Documentation is recommended. | Les tables suivantes manquent de descriptions. La documentation est recommandée. |
| `health.all_documented` | All visible tables are documented. Great work! | Toutes les tables visibles sont documentées. Excellent travail ! |
| `health.load_error` | Could not load health metrics. | Impossible de charger les métriques de santé. |

---

## glossary

| Key | EN | FR |
|-----|----|----|
| `glossary.title` | § Business glossary | § Glossaire métier |
| `glossary.hero_title` | Speak the same language. | Parlez le même langage. |
| `glossary.subtitle` | Define business concepts and map them to technical data assets. | Définissez les concepts métier et liez-les aux données techniques. |
| `glossary.search_placeholder` | Search for a term... | Rechercher un terme… |
| `glossary.no_terms` | No terms found. | Aucun terme trouvé. |
| `glossary.term_details` | § Term Details | § Détails du terme |
| `glossary.definition` | Definition | Définition |
| `glossary.logic_calculation` | Logic / Calculation | Logique / Calcul |
| `glossary.linked_tables` | Linked Tables | Tables liées |
| `glossary.stewardship` | § Stewardship | § Intendance |
| `glossary.domain` | Domain | Domaine |
| `glossary.steward` | Steward | Responsable |
| `glossary.business_domain` | Business domain | Domaine métier |
| `glossary.data_steward` | Data steward | Responsable des données |
| `glossary.concept_map` | § Concept Map | § Carte des concepts |

---

## discovery

| Key | EN | FR |
|-----|----|----|
| `discovery.title` | § Discovery | § Découverte |
| `discovery.subtitle` | Browse the catalog by catalog, schema, and table. | Parcourez le catalogue par catalogue, schéma et table. |
| `discovery.hero_title` | New & Notable. | Nouveau & Remarquable. |
| `discovery.hero_subtitle` | Recently updated data assets across your primary domains. | Données récemment mises à jour dans vos domaines principaux. |
| `discovery.group_highlights` | Highlights for your primary group: {group} | Faits saillants pour votre groupe principal : {group} |
| `discovery.no_updates` | No recent updates found for this group. | Aucune mise à jour récente pour ce groupe. |
| `discovery.load_error` | Could not load discovery feed. | Impossible de charger le flux de découverte. |
| `discovery.sign_in_prompt` | Please sign in or select a group to view discovery highlights. | Connectez-vous ou sélectionnez un groupe pour voir les faits saillants. |
| `discovery.date_format` | %b %d, %H:%M UTC | %d %b, %H:%M UTC |
| `discovery.explore_button` | Explore {name} → | Explorer {name} → |
| `discovery.updated` | Updated | Mis à jour |

---

## footer

| Key | EN | FR |
|-----|----|----|
| `footer.built_with` | Data Dictionary · v0.1.0 · synced nightly from Unity Catalog | Data Dictionary · v0.1.0 · synchronisé chaque nuit depuis Unity Catalog |

---

## common

| Key | EN | FR |
|-----|----|----|
| `common.loading` | Loading... | Chargement… |
| `common.error` | An error occurred. | Une erreur est survenue. |
| `common.empty` | No data available. | Aucune donnée. |
| `common.save` | Save | Enregistrer |
| `common.cancel` | Cancel | Annuler |
| `common.edit` | Edit | Modifier |
| `common.delete` | Delete | Supprimer |
| `common.search` | Search | Rechercher |
| `common.back` | Back | Retour |
| `common.coming_soon` | Coming soon in v0.4.0 | Bientôt disponible en v0.4.0 |

---

## language

| Key | EN | FR |
|-----|----|----|
| `language.en` | EN | EN |
| `language.fr` | FR | FR |
| `language.switch_to_en` | Switch to English | Switch to English |
| `language.switch_to_fr` | Passer en français | Passer en français |

---

## personalization

| Key | EN | FR |
|-----|----|----|
| `personalization.tab_notable` | New & Notable | Nouveau & Notable |
| `personalization.tab_bookmarks` | My Bookmarks | Mes favoris |
| `personalization.tab_recent` | Recently Viewed | Récemment consulté |
| `personalization.add_bookmark` | Bookmark | Ajouter aux favoris |
| `personalization.remove_bookmark` | Bookmarked | Favori enregistré |
| `personalization.no_bookmarks` | No bookmarks yet. Star a table to save it here. | Aucun favori pour l'instant. Marquez une table pour la retrouver ici. |
| `personalization.no_recent` | No recently viewed tables yet. | Aucune table consultée récemment. |
| `personalization.bookmarked_columns` | Bookmarked columns | Colonnes favorites |
| `personalization.no_col_bookmarks` | No column bookmarks yet. Star a column to save it here. | Aucune colonne favorite. Marquez une colonne pour la retrouver ici. |
