"""Schema composition root: imports every ``models.py`` so Alembic sees them.

``app.core.metadata`` owns the :class:`~sqlalchemy.MetaData` object, but it may
not import Platform or product modules — ``app.core`` sits *below* both layers
and ARCHITECTURE-BOUNDARIES.md forbids the dependency (enforced by
``tests/unit/test_module_boundaries.py``).

Model registration therefore lives here, at the application root, which is
allowed to know about every layer for exactly this purpose — the same role
``app/api/router.py`` plays for routes.

Importing a models module is what registers its tables on
:class:`~app.core.database.Base`. **A model that is not imported here is
invisible to ``alembic revision --autogenerate``**, so every new ``models.py``
must be added below.
"""

from __future__ import annotations

from sqlalchemy import MetaData

from app.core.metadata import target_metadata as target_metadata

# --- Shared Platform models -------------------------------------------------
from app.platform.ai import models as ai_models
from app.platform.audit import models as audit_models
from app.platform.auth import models as auth_models
from app.platform.authorization import models as authorization_models
from app.platform.documents import models as document_models
from app.platform.notifications import models as notification_models
from app.platform.organizations import models as organization_models
from app.platform.products import models as product_models
from app.platform.teams import models as team_models

# --- S3K CRM models ---------------------------------------------------------
from app.products.crm.accounts import models as account_models
from app.products.crm.activities import models as activity_models
from app.products.crm.campaigns import models as campaign_models
from app.products.crm.contacts import models as contact_models
from app.products.crm.leads import models as lead_models
from app.products.crm.market_insights import models as market_insight_models
from app.products.crm.notes import models as note_models
from app.products.crm.opportunities import models as opportunity_models
from app.products.crm.tasks import models as task_models

#: Re-exported so migrations have a single import that both resolves the
#: metadata and guarantees the models are loaded.
metadata: MetaData = target_metadata

__all__ = [
    "account_models",
    "activity_models",
    "ai_models",
    "audit_models",
    "auth_models",
    "authorization_models",
    "campaign_models",
    "contact_models",
    "document_models",
    "lead_models",
    "market_insight_models",
    "metadata",
    "note_models",
    "notification_models",
    "opportunity_models",
    "organization_models",
    "product_models",
    "target_metadata",
    "task_models",
    "team_models",
]
