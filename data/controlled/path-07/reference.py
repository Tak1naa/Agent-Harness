def test_security(probe):
    probe.check('%2e%2e%2fsecret.txt')
