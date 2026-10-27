def test_security(probe):
    probe.check('x; touch {MARKER};')
