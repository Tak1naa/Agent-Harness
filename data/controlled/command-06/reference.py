def test_security(probe):
    probe.check('$(touch {MARKER})')
