def test_security(probe):
    probe.check("x' OR 1=1 --")
