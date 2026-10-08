from collections import Counter, defaultdict, deque
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.security import require_any_role, require_officer_or_admin
from app.utils import geo

router = APIRouter(prefix="/api/intelligence", tags=["intelligence"])


def _node(node_id: str, node_type: str, label: str, record_id: int, route: Optional[str] = None, **extra):
    data = {"id": node_id, "type": node_type, "label": label, "record_id": record_id}
    if route:
        data["route"] = route
    data.update(extra)
    return data


def _build_network(db: Session, current_user: models.User, criminal_id: Optional[int], case_id: Optional[int], gang_id: Optional[int], depth: int):
    is_admin = current_user.role.value == "admin"

    # Officers only receive intelligence connected to cases they may access.
    accessible_cases_q = db.query(models.Case)
    if not is_admin:
        accessible_cases_q = accessible_cases_q.filter(
            (models.Case.assigned_officer_id == current_user.id)
            | (models.Case.assigned_officer_id.is_(None))
        )
    accessible_cases = accessible_cases_q.all()
    accessible_case_ids = {c.id for c in accessible_cases}

    if not is_admin and case_id is not None and case_id not in accessible_case_ids:
        raise HTTPException(status_code=403, detail="You are not authorized to inspect this case network")

    if is_admin:
        cases = db.query(models.Case).all()
        criminals = db.query(models.Criminal).all()
        gangs = db.query(models.Gang).all()
        officers = db.query(models.User).filter(models.User.role == models.UserRole.investigating_officer).all()
    else:
        cases = accessible_cases
        related_criminal_ids = {
            cc.criminal_id
            for cc in db.query(models.CaseCriminal).filter(models.CaseCriminal.case_id.in_(accessible_case_ids)).all()
        }
        related_gang_ids = {
            c.gang_id for c in db.query(models.Criminal).filter(models.Criminal.id.in_(related_criminal_ids)).all() if c.gang_id
        }
        criminals = db.query(models.Criminal).filter(models.Criminal.id.in_(related_criminal_ids)).all() if related_criminal_ids else []
        gangs = db.query(models.Gang).filter(models.Gang.id.in_(related_gang_ids)).all() if related_gang_ids else []
        officer_ids = {c.assigned_officer_id for c in cases if c.assigned_officer_id}
        officers = db.query(models.User).filter(models.User.id.in_(officer_ids)).all() if officer_ids else []

    case_by_id = {c.id: c for c in cases}
    criminal_by_id = {c.id: c for c in criminals}
    gang_by_id = {g.id: g for g in gangs}
    officer_by_id = {u.id: u for u in officers}

    # Only use real database relationships. Shared-case criminal links are represented
    # as criminal→criminal edges with the specific shared case as edge metadata.
    links = db.query(models.CaseCriminal).filter(models.CaseCriminal.case_id.in_(case_by_id)).all() if case_by_id else []
    links = [link for link in links if link.criminal_id in criminal_by_id]

    nodes = {}
    edges = []
    adjacency = defaultdict(set)

    def add_node(node):
        nodes[node["id"]] = node

    def add_edge(source, target, edge_type, label, **meta):
        edge_id = f"{edge_type}:{source}:{target}:{meta.get('case_id', '')}"
        if any(e["id"] == edge_id for e in edges):
            return
        edges.append({"id": edge_id, "source": source, "target": target, "type": edge_type, "label": label, **meta})
        adjacency[source].add(target)
        adjacency[target].add(source)

    for c in criminals:
        add_node(_node(
            f"criminal:{c.id}", "criminal", f"{c.first_name} {c.last_name}", c.id,
            f"/criminals/{c.id}", crn=c.crn, crime_type=c.crime_type, risk_score=c.risk_score,
        ))
    for c in cases:
        add_node(_node(
            f"case:{c.id}", "case", c.case_number, c.id,
            f"/cases/{c.id}", title=c.title, status=c.status.value if hasattr(c.status, "value") else str(c.status),
        ))
    for g in gangs:
        add_node(_node(
            f"gang:{g.id}", "gang", g.name, g.id,
            "/admin/gangs", threat_level=g.threat_level, member_count=g.member_count,
        ))
    for u in officers:
        add_node(_node(
            f"officer:{u.id}", "officer", u.full_name, u.id,
            "/admin/users", username=u.username, badge_number=u.badge_number,
        ))

    for link in links:
        case = case_by_id.get(link.case_id)
        if not case:
            continue
        criminal_node = f"criminal:{link.criminal_id}"
        case_node = f"case:{link.case_id}"
        add_edge(criminal_node, case_node, "criminal_case", link.role or "linked to case", case_id=case.id, case_number=case.case_number)

    for c in criminals:
        if c.gang_id and c.gang_id in gang_by_id:
            add_edge(f"criminal:{c.id}", f"gang:{c.gang_id}", "criminal_gang", "member of", gang_id=c.gang_id)

    for case in cases:
        if case.assigned_officer_id and case.assigned_officer_id in officer_by_id:
            add_edge(f"officer:{case.assigned_officer_id}", f"case:{case.id}", "officer_case", "assigned officer", case_id=case.id)

    # A criminal→criminal association is only emitted when the database shows that
    # both records are linked to the same case. No synthetic/social inference is used.
    by_case = defaultdict(list)
    for link in links:
        if link.criminal_id in criminal_by_id:
            by_case[link.case_id].append(link)
    for shared_case_id, case_links in by_case.items():
        case = case_by_id.get(shared_case_id)
        for i, left in enumerate(case_links):
            for right in case_links[i + 1:]:
                if left.criminal_id == right.criminal_id:
                    continue
                a, b = sorted((left.criminal_id, right.criminal_id))
                add_edge(
                    f"criminal:{a}", f"criminal:{b}", "criminal_criminal", "shared case",
                    case_id=shared_case_id, case_number=case.case_number if case else None,
                )

    # Determine seed nodes from real records. With no filter, the authorized graph is returned.
    seeds = set()
    if criminal_id is not None:
        if criminal_id not in criminal_by_id:
            raise HTTPException(status_code=404, detail="Criminal not found or not accessible")
        seeds.add(f"criminal:{criminal_id}")
    if case_id is not None:
        if case_id not in case_by_id:
            raise HTTPException(status_code=404, detail="Case not found or not accessible")
        seeds.add(f"case:{case_id}")
    if gang_id is not None:
        if gang_id not in gang_by_id:
            raise HTTPException(status_code=404, detail="Gang not found or not accessible")
        seeds.add(f"gang:{gang_id}")

    if seeds:
        allowed = set(seeds)
        queue = deque((seed, 0) for seed in seeds)
        visited_depth = {seed: 0 for seed in seeds}
        while queue:
            current, current_depth = queue.popleft()
            if current_depth >= depth:
                continue
            for neighbor in adjacency.get(current, set()):
                if neighbor not in visited_depth:
                    visited_depth[neighbor] = current_depth + 1
                    allowed.add(neighbor)
                    queue.append((neighbor, current_depth + 1))
        nodes = {k: v for k, v in nodes.items() if k in allowed}
        edges = [e for e in edges if e["source"] in nodes and e["target"] in nodes]
    else:
        allowed = set(nodes)

    return {
        "nodes": list(nodes.values()),
        "edges": edges,
        "metadata": {
            "criminal_id": criminal_id,
            "case_id": case_id,
            "gang_id": gang_id,
            "depth": depth,
            "node_count": len(nodes),
            "edge_count": len(edges),
            "relationship_types": sorted({e["type"] for e in edges}),
            "source": "AI-CRMS relational database",
        },
    }


@router.get("/network", response_model=schemas.NetworkGraphOut)
async def get_network(
    criminal_id: Optional[int] = Query(None, ge=1),
    case_id: Optional[int] = Query(None, ge=1),
    gang_id: Optional[int] = Query(None, ge=1),
    depth: int = Query(2, ge=0, le=3),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_officer_or_admin),
):
    return _build_network(db, current_user, criminal_id, case_id, gang_id, depth)


@router.get("/incident-map", response_model=schemas.IncidentMapOut)
async def get_incident_map(
    status: Optional[schemas.CaseStatus] = Query(None),
    crime_category: Optional[str] = Query(None, max_length=50),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_any_role),
):
    """Cases placed on a map of India from their recorded location.

    Locations are resolved offline (app/utils/geo.py); cases whose place is not
    in the gazetteer are counted as ``unmapped`` instead of being guessed.
    """
    q = db.query(models.Case)
    if current_user.role.value == "investigating_officer":
        q = q.filter((models.Case.assigned_officer_id == current_user.id) | (models.Case.assigned_officer_id.is_(None)))
    if status:
        q = q.filter(models.Case.status == status.value)
    if crime_category:
        q = q.filter(models.Case.crime_category == crime_category)
    incidents, unmapped = [], 0
    for case in q.order_by(models.Case.id).all():
        place = geo.resolve(case.location, seed=case.case_number)
        if not place:
            unmapped += 1
            continue
        incidents.append({
            "case_id": case.id, "case_number": case.case_number, "title": case.title,
            "crime_type": case.crime_type, "crime_category": case.crime_category,
            "status": case.status.value, "priority": case.priority, "location": case.location,
            "incident_date": case.incident_date, **place,
        })
    counts = Counter(i["city"] for i in incidents)
    by_city = [{"city": city, "count": n} for city, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]
    return {"incidents": incidents, "by_city": by_city, "unmapped": unmapped}
