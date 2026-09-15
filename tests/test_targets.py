from optout_kit import laws, targets

RECORDS = [
    {"title": "Spokeo", "type": "People Search Site",
     "email": "privacy@spokeo.com", "opt_out_url": "https://www.spokeo.com/optout"},
    {"title": "FormOnly", "type": "People Search Site",
     "email": "", "opt_out_url": "https://example.com/optout"},
    {"title": "NoRoute", "type": "People Search Site", "email": "", "opt_out_url": ""},
    {"title": "SomeMarketer", "type": "Marketing", "email": "x@example.com"},
]


def test_public_type_filter_excludes_marketing():
    slugs = {t.slug for t in targets.build("OR", records=RECORDS)}
    assert "somemarketer" not in slugs


def test_email_route_preferred_over_form():
    t = next(t for t in targets.build("OR", records=RECORDS) if t.slug == "spokeo")
    assert t.method == "email" and t.route == "privacy@spokeo.com"


def test_missing_route_is_skipped_not_dropped():
    t = next(t for t in targets.build("OR", records=RECORDS) if t.slug == "noroute")
    assert t.skip_reason == "no_route" and not t.actionable


def test_id_required_brokers_skipped_by_default():
    recs = RECORDS + [{"title": "Spokeo", "type": "People Search Site", "email": "a@b.c"}]
    rows = targets.build("OR", records=recs, allow_id_upload=False)
    assert all(t.skip_reason != "skipped_id_required" or not t.actionable for t in rows)


def test_california_exposes_drop_as_preferred():
    assert laws.load("CA").preferred_mechanism["id"] == "DROP"
    assert laws.load("OR").preferred_mechanism is None


def test_unknown_state_is_a_clear_error():
    try:
        laws.load("ZZ")
    except laws.UnknownState as e:
        assert "CONTRIBUTING" in str(e)
    else:
        raise AssertionError("expected UnknownState")
