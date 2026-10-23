import datetime
import uuid
from typing import Any, Dict, List, Optional
from core.logging_otel import logger
from domain.events import DomainEvent


class TimeTravelFlightRecorder:
    """Event Sourcing deterministic state projection engine for historical playback and audit."""

    def __init__(self):
        self.state_incidents: Dict[str, Dict[str, Any]] = {}
        self.state_clusters: Dict[str, Dict[str, Any]] = {}
        self.state_teams: Dict[str, Dict[str, Any]] = {}
        self.state_dispatches: Dict[str, Dict[str, Any]] = {}

    def reset(self) -> None:
        self.state_incidents.clear()
        self.state_clusters.clear()
        self.state_teams.clear()
        self.state_dispatches.clear()

    def apply_event(self, event: DomainEvent) -> None:
        """Folds a single domain event into the projected state machine."""
        event_type = event.event_type
        payload = event.payload
        agg_id = str(event.aggregate_id)

        if event_type == "IncidentIngested":
            self.state_incidents[agg_id] = {
                "id": agg_id,
                "title": payload.get("title"),
                "urgency": payload.get("urgency"),
                "category": payload.get("category"),
                "latitude": payload.get("latitude"),
                "longitude": payload.get("longitude"),
                "triage_state": "INGESTED",
                "created_at": event.occurred_at.isoformat(),
            }

        elif event_type == "ModelTriageDispatched":
            if agg_id in self.state_incidents:
                self.state_incidents[agg_id]["triage_state"] = "TRIAGED"
                self.state_incidents[agg_id]["decision"] = payload.get("decision")
                self.state_incidents[agg_id]["confidence"] = payload.get("confidence")

        elif event_type == "HawkesClusterFormed":
            cluster_id = str(payload.get("cluster_id", agg_id))
            self.state_clusters[cluster_id] = {
                "id": cluster_id,
                "centroid_lat": payload.get("centroid_lat"),
                "centroid_lon": payload.get("centroid_lon"),
                "radius_meters": payload.get("radius_meters"),
                "incident_count": payload.get("incident_count", 1),
            }

        elif event_type == "SmtDispatchOptimized":
            dispatch_id = str(payload.get("dispatch_id", uuid.uuid4()))
            team_id = str(payload.get("team_id"))
            incident_id = str(payload.get("incident_id"))

            self.state_dispatches[dispatch_id] = {
                "id": dispatch_id,
                "incident_id": incident_id,
                "team_id": team_id,
                "eta_minutes": payload.get("eta_minutes"),
                "status": "DISPATCHED",
            }
            if incident_id in self.state_incidents:
                self.state_incidents[incident_id]["triage_state"] = "DISPATCHED"

        elif event_type == "HitlDecisionRecorded":
            incident_id = str(payload.get("incident_id"))
            if incident_id in self.state_incidents:
                self.state_incidents[incident_id]["hitl_decision"] = payload.get("decision")

    def project_state_as_of(
        self,
        event_stream: List[DomainEvent],
        as_of_time: Optional[datetime.datetime] = None,
    ) -> Dict[str, Any]:
        """Plays event stream chronologically up to cutoff timestamp and returns reconstructed world state."""
        self.reset()
        applied_count = 0

        for event in event_stream:
            if as_of_time is not None and event.occurred_at > as_of_time:
                break
            self.apply_event(event)
            applied_count += 1

        snapshot = {
            "applied_events_count": applied_count,
            "as_of_timestamp": as_of_time.isoformat() if as_of_time else datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "incidents": dict(self.state_incidents),
            "clusters": dict(self.state_clusters),
            "dispatches": dict(self.state_dispatches),
        }
        logger.info("time_travel_state_projected", applied_events=applied_count)
        return snapshot
