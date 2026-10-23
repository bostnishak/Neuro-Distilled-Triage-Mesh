from typing import Any, Dict, List
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from infrastructure.database.connection import get_db
from infrastructure.database.orm_models import IncidentClusterOrm, UserOrm
from presentation.api.dependencies import get_current_user
from domain.services.hawkes_process_engine import HawkesProcessEngine, HawkesParameters

router = APIRouter(prefix="/clusters", tags=["Hawkes Spatio-Temporal Clusters"])
_hawkes_engine = HawkesProcessEngine()


@router.get("")
async def list_clusters(
    current_user: UserOrm = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> List[Dict[str, Any]]:
    """Lists all active Hawkes spatio-temporal clusters with aftershock forecasts."""
    stmt = (
        select(
            IncidentClusterOrm.id,
            IncidentClusterOrm.radius_meters,
            IncidentClusterOrm.cluster_urgency,
            IncidentClusterOrm.incident_count,
            IncidentClusterOrm.hawkes_mu,
            IncidentClusterOrm.hawkes_alpha,
            IncidentClusterOrm.hawkes_beta,
            IncidentClusterOrm.status,
            IncidentClusterOrm.created_at,
            func.ST_X(IncidentClusterOrm.centroid).label("lon"),
            func.ST_Y(IncidentClusterOrm.centroid).label("lat"),
        )
        .where(IncidentClusterOrm.status == "ACTIVE")
        .order_by(IncidentClusterOrm.incident_count.desc())
    )
    res = await session.execute(stmt)
    rows = res.fetchall()

    clusters_out = []
    for r in rows:
        # Compute aftershock probability from Hawkes branching ratio
        branching_ratio = r.hawkes_alpha / r.hawkes_beta if r.hawkes_beta > 0 else 0.5
        aftershock_prob = min(0.99, max(0.05, branching_ratio * (1.0 - (1.0 / (r.incident_count + 1)))))

        clusters_out.append({
            "id": str(r.id),
            "centroid": {"latitude": r.lat, "longitude": r.lon},
            "radius_meters": r.radius_meters,
            "cluster_urgency": r.cluster_urgency,
            "incident_count": r.incident_count,
            "hawkes_parameters": {
                "mu": r.hawkes_mu,
                "alpha": r.hawkes_alpha,
                "beta": r.hawkes_beta,
                "branching_ratio": round(branching_ratio, 3),
            },
            "aftershock_probability": round(aftershock_prob, 3),
            "status": r.status,
            "created_at": r.created_at.isoformat(),
        })

    return clusters_out
