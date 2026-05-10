from __future__ import annotations
from typing import Any, Callable, Optional, Protocol, runtime_checkable
"""Public surface for src.ui.cards — re-exports from submodules.

Historic callers `from src.ui.cards import render_health` etc. keep
working through this shim. New code should import from the specific
submodule (`from src.ui.cards.discovery import render_discovery`).

Submodules:
- ``_shared``    cross-cutting helpers (DQ grade, _POST_COLOR, completeness)
- ``discovery``  discovery tab + CMS banner + table card
- ``health``     health dashboard
- ``admin``      admin page composition (incl. CMS admin section + dialogs)
- ``pipelines``  pipelines tab UI + admin pipeline section
- ``detail``     table-detail dialogs (used by the search page)
"""


from src.ui.cards._shared import (  # noqa: F401
    _DQ_GRADES,
    _POST_COLOR,
    _compute_live_completeness,
    _dq_grade,
)
from src.ui.cards.admin import (  # noqa: F401
    get_admin_stats,
    get_business_name_change_log,
    get_comment_log,
    get_sync_queue_stats,
    render_admin_page,
)
from src.ui.cards.detail import (  # noqa: F401
    render_data_sample,
    render_table_metadata_editor,
)
from src.ui.cards.discovery import (  # noqa: F401
    _render_table_card,
    render_cms_banner,
    render_discovery,
)
from src.ui.cards.health import render_health  # noqa: F401
from src.ui.cards.pipelines import (  # noqa: F401
    _render_admin_pipelines_section,
    _show_pipeline_create_dialog,
    render_pipelines_page,
)
