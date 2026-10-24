def test_security(probe):
    probe.check('../public_backup/secret.txt')
