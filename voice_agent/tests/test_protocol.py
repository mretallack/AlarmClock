from voice_agent import protocol


def test_play_roundtrip():
    cmd = protocol.play("http://10.0.0.78:8000/reply.wav")
    assert cmd.encode() == b"PLAY http://10.0.0.78:8000/reply.wav\n"
    assert protocol.decode(cmd.encode()) == cmd


def test_stop_and_ping():
    assert protocol.decode(protocol.stop().encode()).verb == "STOP"
    assert protocol.decode(protocol.ping().encode()).verb == "PING"


def test_decode_tolerates_newlines_and_case():
    assert protocol.decode(b"play  x\r\n").verb == "PLAY"
    assert protocol.decode(b"play  x\r\n").arg == "x"
