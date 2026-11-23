import logging

from mihomo_lite.utils.logger import RingBufferHandler


def _record(message: str) -> logging.LogRecord:
    return logging.LogRecord("test", logging.INFO, __file__, 1, message, (), None)


def test_sequence_survives_eviction():
    handler = RingBufferHandler(capacity=5)
    handler.setFormatter(logging.Formatter("%(message)s"))
    for index in range(12):
        handler.emit(_record(f"line{index}"))

    records = handler.snapshot()
    assert len(records) == 5
    seqs = [record[0] for record in records]
    assert seqs == list(range(8, 13))
    assert records[-1][3].endswith("line11")


def test_last_seq_tracks_every_record():
    handler = RingBufferHandler(capacity=2)
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler.emit(_record("a"))
    handler.emit(_record("b"))
    handler.emit(_record("c"))
    assert handler.last_seq == 3
    assert [record[0] for record in handler.snapshot()] == [2, 3]
