from cyclonedds.qos import Qos, Policy

# 양방향/단방향 공통: 신뢰성 있는 전송, concurrent request 대응을 위해 depth=32
RELIABLE_QOS = Qos(
    Policy.Reliability.Reliable(max_blocking_time=1_000_000_000),  # 1s
    Policy.Durability.Volatile,
    Policy.History.KeepLast(32),
)

# start_session 등 discovery 이전에 publish될 수 있는 메시지용
SESSION_QOS = Qos(
    Policy.Reliability.Reliable(max_blocking_time=1_000_000_000),
    Policy.Durability.TransientLocal,
    Policy.History.KeepLast(1),
)
