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


def test_excluded_statuses_are_all_terminal():
    # cmd_draft filters on clocks.TERMINAL, so every status that should suppress
    # a draft has to be in that set. A status missing here silently generates
    # mail to a broker the user deliberately excluded.
    from optout_kit import clocks
    for status in ("skipped_employer_conflict", "skipped_id_required",
                   "no_route", "abandoned", "confirmed"):
        assert status in clocks.TERMINAL, status
    for status in ("skipped_employer_conflict", "skipped_id_required"):
        assert status in clocks.NEVER_ESCALATE, status


def test_canary_tag_is_deterministic_and_reversible():
    from optout_kit import canary
    addr = canary.tag_for("someone@gmail.com", "spokeo")
    assert addr == "someone+spokeo@gmail.com"
    assert canary.source_of(addr) == "spokeo"


def test_canary_does_not_stack_tags():
    from optout_kit import canary
    assert canary.tag_for("someone+old@gmail.com", "radaris") == "someone+radaris@gmail.com"


def test_canary_off_unless_base_configured():
    from optout_kit import canary
    assert canary.for_broker({}, "spokeo") is None
    assert canary.for_broker({"canary_email_base": "a@b.com"}, "spokeo") == "a+spokeo@b.com"


def test_canary_supplements_rather_than_replaces_real_email():
    # Replacing the real address would hurt the broker's ability to match the
    # record at all, which defeats the point of sending the request.
    from optout_kit import render
    profile = {"full_name": "A B", "emails": ["real@gmail.com"]}
    block = render.identity_block(profile, canary_email="real+spokeo@gmail.com")
    assert "real@gmail.com" in block
    assert "real+spokeo@gmail.com" in block
