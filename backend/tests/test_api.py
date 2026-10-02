
def test_officer_can_confirm_prediction(
    client, admin_token, officer_token
):
    """An assigned officer can review a prediction for their case."""
    from app.database import SessionLocal
    from app import models

    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    officer_headers = {"Authorization": f"Bearer {officer_token}"}

    # 1. Get the officer's database ID.
    db = SessionLocal()
    try:
        officer = (
            db.query(models.User)
            .filter(models.User.username == "officer_test")
            .first()
        )
        assert officer is not None, "Test officer was not seeded"
        officer_id = officer.id
    finally:
        db.close()

    # 2. Create a criminal using the project's existing API.
    criminal_res = client.post(
        "/api/criminals",
        json={
            "first_name": "OfficerReview",
            "last_name": "TestSubject",
            "crime_type": "Robbery",
            "threat_level": "medium",
            "prior_convictions": 1,
            "is_wanted": False,
        },
        headers=admin_headers,
    )
    assert criminal_res.status_code == 200, (
        f"Criminal creation failed: "
        f"{criminal_res.status_code} {criminal_res.text}"
    )
    criminal_id = criminal_res.json()["id"]

    # 3. Create a case containing the criminal.
    case_res = client.post(
        "/api/cases",
        json={
            "title": "Officer AI Review Test",
            "description": "Authorization test for AI prediction review",
            "crime_type": "Robbery",
            "priority": "high",
            "criminal_ids": [criminal_id],
        },
        headers=admin_headers,
    )
    assert case_res.status_code in (200, 201), (
        f"Case creation failed: {case_res.status_code} {case_res.text}"
    )
    case_id = case_res.json()["id"]

    # 4. Assign the case to the officer and verify the relationship.
    db = SessionLocal()
    try:
        case = (
            db.query(models.Case)
            .filter(models.Case.id == case_id)
            .first()
        )
        assert case is not None, "Created case was not found"

        case.assigned_officer_id = officer_id

        link = (
            db.query(models.CaseCriminal)
            .filter(
                models.CaseCriminal.case_id == case_id,
                models.CaseCriminal.criminal_id == criminal_id,
            )
            .first()
        )
        if link is None:
            db.add(
                models.CaseCriminal(
                    case_id=case_id,
                    criminal_id=criminal_id,
                )
            )

        db.commit()
    finally:
        db.close()

    # 5. Create a prediction associated with the case.
    prediction_res = client.post(
        "/api/ai/predict",
        json={
            "criminal_id": criminal_id,
            "case_id": case_id,
        },
        headers=admin_headers,
    )
    assert prediction_res.status_code == 200, (
        f"Prediction creation failed: "
        f"{prediction_res.status_code} {prediction_res.text}"
    )
    prediction_id = prediction_res.json()["id"]

    # 6. Review the prediction as the assigned officer.
    review_res = client.post(
        f"/api/ai/predictions/{prediction_id}/review",
        json={
            "status": "confirmed",
            "remarks": "Confirmed based on prior arrest records.",
        },
        headers=officer_headers,
    )
    assert review_res.status_code == 200, (
        f"Officer review failed: "
        f"{review_res.status_code} {review_res.text}"
    )

    result = review_res.json()
    assert result["review_status"] == "confirmed"
    assert result["officer_remarks"] == (
        "Confirmed based on prior arrest records."
    )
    assert result["reviewed_by_id"] == officer_id