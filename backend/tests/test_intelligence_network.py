
from app import models
from app.routers.intelligence import _build_network


def create_officer(db, username, email):
    """Create and persist an officer with all required fields."""
    officer = models.User(
        username=username,
        email=email,
        full_name="Network Test Officer",
        hashed_password="test-hash",
        role=models.UserRole.investigating_officer,
    )
    db.add(officer)
    db.flush()
    return officer


def test_network_uses_real_relationships_and_shared_cases(db):
    # Create a real database user; do not assume a fixed user ID.
    officer = create_officer(
        db,
        username="network_relationship_officer",
        email="network-relationship-officer@example.test",
    )

    # Let the database generate primary keys for all records.
    gang = models.Gang(name="Alpha Network Test")

    c1 = models.Criminal(
        crn="NET-REL-CRN-101",
        first_name="Network",
        last_name="PersonOne",
        gang_id=None,
    )
    c2 = models.Criminal(
        crn="NET-REL-CRN-102",
        first_name="Network",
        last_name="PersonTwo",
        gang_id=None,
    )

    db.add_all([gang, c1, c2])
    db.flush()

    # Associate both criminals with the same gang.
    c1.gang_id = gang.id
    c2.gang_id = gang.id

    case = models.Case(
        case_number="NET-REL-CASE-2026-01",
        title="Network Relationship Test",
        assigned_officer_id=officer.id,
    )
    db.add(case)
    db.flush()

    db.add_all([
        models.CaseCriminal(
            case_id=case.id,
            criminal_id=c1.id,
            role="suspect",
        ),
        models.CaseCriminal(
            case_id=case.id,
            criminal_id=c2.id,
            role="accused",
        ),
    ])
    db.commit()

    graph = _build_network(db, officer, None, case.id, None, 2)

    node_ids = {node["id"] for node in graph["nodes"]}
    expected_nodes = {
        f"case:{case.id}",
        f"criminal:{c1.id}",
        f"criminal:{c2.id}",
        f"gang:{gang.id}",
        f"officer:{officer.id}",
    }

    assert expected_nodes <= node_ids

    edge_types = {edge["type"] for edge in graph["edges"]}
    assert {
        "criminal_case",
        "criminal_gang",
        "officer_case",
        "criminal_criminal",
    } <= edge_types


def test_network_depth_one_only_returns_direct_neighbors(db):
    officer = create_officer(
        db,
        username="network_depth_officer",
        email="network-depth-officer@example.test",
    )

    c1 = models.Criminal(
        crn="NET-DEPTH-CRN-101",
        first_name="Depth",
        last_name="PersonOne",
    )
    c2 = models.Criminal(
        crn="NET-DEPTH-CRN-102",
        first_name="Depth",
        last_name="PersonTwo",
    )

    db.add_all([c1, c2])
    db.flush()

    case = models.Case(
        case_number="NET-DEPTH-CASE-2026-01",
        title="Network Depth Test",
        assigned_officer_id=officer.id,
    )
    db.add(case)
    db.flush()

    db.add_all([
        models.CaseCriminal(
            case_id=case.id,
            criminal_id=c1.id,
        ),
        models.CaseCriminal(
            case_id=case.id,
            criminal_id=c2.id,
        ),
    ])
    db.commit()

    graph = _build_network(db, officer, None, case.id, None, 1)

    node_ids = {node["id"] for node in graph["nodes"]}
    expected_nodes = {
        f"case:{case.id}",
        f"criminal:{c1.id}",
        f"criminal:{c2.id}",
        f"officer:{officer.id}",
    }

    assert node_ids == expected_nodes
