# gRPC → DDS 마이그레이션 계획

> ✅ = 구현 완료

## 범위

### 대상 (내부 서비스 → DDS로 교체)
- Runtime ↔ **Driver** (이 레포에 서버 구현 있음)
- Runtime ↔ **Controller** (이 레포에 서버 구현 있음)
- Runtime ↔ **Physics** (이 레포에 서버 구현 있음)

### 제외 (외부 서비스 → gRPC 유지)
- Runtime ↔ **Sensorsim** (외부 Docker 이미지: `nvidia-nurec-grpc`)
- Runtime ↔ **Traffic** (외부 서비스, 현재 `skip: true`)

---

## 설계 원칙

### 1. Static Writer/Reader 패턴
- `DomainParticipant`는 앱 전체에서 **1개** 공유 (생성 비용이 가장 큼)
- 각 서비스의 DataWriter/DataReader는 **`__init__` 시점에 미리 생성**
- DDS discovery 지연(수백ms~수초)을 세션 시작 전에 완료
- `__init__`에서 Writer/Reader 생성 후 `matched_publications`/`matched_subscriptions` 대기하여 discovery 완료 보장
- gRPC의 `_open_connection()` / `_close_connection()`을 대체

### 2. DDSTransport
- 서비스 간 통신을 추상화하는 단일 클래스
- 양방향 (요청→응답) 과 단방향 (보내기만) 을 하나의 클래스로 처리
- `resp_type` 유무로 양방향/단방향 결정
- 서비스 코드에서는 DDS 내부 구현을 모르고 `.request()` / `.send()` 만 호출

### 3. Fire-and-Forget
- 응답이 Empty이고 반환값을 사용하지 않는 통신은 `.send()`로 처리
- 해당: `submit_image_observation`, `submit_egomotion_observation`, `submit_route`, `submit_recording_ground_truth`, `close_session`, `shut_down`

### 4. 세션 관리
- `start_session` / `close_session`은 동일 DDSTransport로 세션 메시지 publish
- 세션 컨텍스트는 메시지 내 `session_uuid` 필드로 구분 (현재와 동일)
- Writer/Reader는 세션과 무관하게 앱 수명 동안 유지 (static)

### 5. correlation_id
- 양방향 통신에서 요청-응답을 매칭하기 위해 필요
- **모든 양방향 DDS 타입에 `correlation_id: str` 필드를 추가**해야 함
- 기존 protobuf에는 없던 필드 (gRPC는 연결 자체가 매칭을 보장했으므로)
- `DDSTransport.request()`가 자동으로 생성/매칭 처리

### 6. 클라이언트/서버 비대칭 패턴
- CycloneDDS Python의 `read()`/`take()`/`write()`는 **동기(blocking)**
- 클라이언트와 서버는 특성이 다르므로 다른 패턴 사용:

| | 클라이언트 (Runtime) | 서버 (Driver 등) |
|---|---|---|
| 패턴 | `take()` polling | `on_data_available` listener + `asyncio.Queue` |
| 이유 | 요청 1개 → 응답 1개 기다리면 끝 | 언제 올지 모르는 요청을 계속 받아야 함 |
| 복잡도 | 단순 | listener 콜백 + queue 처리 태스크 |

- **클라이언트**: `request()` 호출 후 `take()` polling으로 응답 대기 (단순)
- **서버**: listener가 req를 받아 queue에 넣고, 별도 asyncio 태스크가 queue에서 꺼내 처리 후 resp write
  - listener 콜백 안에서 직접 `write()` 하면 CycloneDDS 데드락 위험 → queue로 분리

---

## 교체 대상 통신 목록

### Driver (7개)

| 통신 | 패턴 | DDS Topic | 비고 |
|------|------|-----------|------|
| `start_session` | 양방향 | `driver/session_start` | 세션 초기화 |
| `close_session` | 단방향 | `driver/session_close` | 현재 코드에서 응답 미사용 |
| `submit_image_observation` | 단방향 | `driver/image_observation` | fire-and-forget |
| `submit_egomotion_observation` | 단방향 | `driver/egomotion` | fire-and-forget |
| `submit_route` | 단방향 | `driver/route` | fire-and-forget |
| `submit_recording_ground_truth` | 단방향 | `driver/ground_truth` | fire-and-forget |
| `drive` | 양방향 | `driver/drive` | 핵심 request-response |

### Controller (3개)

| 통신 | 패턴 | DDS Topic | 비고 |
|------|------|-----------|------|
| `start_session` | 양방향 | `controller/session_start` | |
| `close_session` | 단방향 | `controller/session_close` | 현재 코드에서 응답 미사용 |
| `run_controller_and_vehicle` | 양방향 | `controller/run` | 핵심 request-response |

### Physics (2개)

| 통신 | 패턴 | DDS Topic | 비고 |
|------|------|-----------|------|
| `ground_intersection` | 양방향 | `physics/ground_intersection` | 매 step 1~2회 호출 |
| `get_available_scenes` | 양방향 | `physics/available_scenes` | 세션 초기화 시 1회 호출 |

### 공통 (2개)

| 통신 | 패턴 | DDS Topic | 비고 |
|------|------|-----------|------|
| `get_version` | 양방향 | `{service}/version` | |
| `shut_down` | 단방향 | `{service}/shutdown` | fire-and-forget |

---

## 코드 변경 계획

### Phase 1: `src/dds` workspace 패키지 생성 ✅

**새 workspace 멤버:** `src/dds/` ✅

루트 `pyproject.toml`의 `[tool.uv.workspace].members`에 `"src/dds"` 추가. ✅

```
src/dds/alpasim_dds/
├── types/                  # DDS 네이티브 타입 정의 (proto 대체) ✅
│   ├── common.py           # Pose, Vec3, DynamicState, Trajectory 등 ✅
│   ├── camera.py           # CameraSpec, AvailableCamera 등 (sensorsim에서 추출) ✅
│   ├── egodriver.py        # DriveRequest, DriveResponse 등 ✅
│   ├── controller.py       # VDCSessionRequest 등 ✅
│   └── physics.py          # PhysicsGroundIntersectionRequest 등 ✅
├── endpoints/              # 서비스별 DDSTransport 인스턴스 생성 ✅
│   ├── driver.py           # DriverEndpoints ✅
│   ├── controller.py       # ControllerEndpoints ✅
│   └── physics.py          # PhysicsEndpoints ✅
├── participant.py          # DomainParticipant 싱글턴 관리 ✅
├── transport.py            # DDSTransport (양방향/단방향 통합 클래스) ✅
└── qos.py                  # QoS 프로필 (RELIABLE, KEEP_LAST 등) ✅
```

#### DDSTransport (`transport.py`) ✅

서비스 간 통신을 추상화하는 단일 클래스. `resp_type` 유무로 양방향/단방향이 결정됨.

```python
class DDSTransport(Generic[ReqType, RespType]):
    def __init__(self, participant, name, req_type, resp_type=None, qos=RELIABLE_QOS):
        # 항상 생성: request topic writer
        self.writer = DataWriter(participant, Topic(participant, f"{name}/req", req_type), qos)
        # resp_type이 있을 때만: response topic reader
        if resp_type:
            self.reader = DataReader(participant, Topic(participant, f"{name}/resp", resp_type), qos)
        else:
            self.reader = None

    def send(self, data):
        """단방향 — 보내고 끝 (fire-and-forget)"""
        self.writer.write(data)

    async def request(self, data, timeout_s=5.0):
        """양방향 — 보내고 응답 대기 (take() polling)"""
        assert self.reader is not None, "양방향 transport가 아님 (resp_type 미지정)"
        correlation_id = str(uuid4())
        data.correlation_id = correlation_id
        self.writer.write(data)
        return await self._wait_for_response(correlation_id, timeout_s)

    async def _wait_for_response(self, correlation_id, timeout_s):
        """take() polling으로 응답 대기, correlation_id 매칭"""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            for sample in self.reader.take():
                if sample.correlation_id == correlation_id:
                    return sample
            await asyncio.sleep(0.001)  # 이벤트 루프 양보
        raise TimeoutError(f"correlation_id={correlation_id} 응답 없음 ({timeout_s}s 초과)")
```

#### 서비스별 Endpoints 예시 (`endpoints/driver.py`) ✅

```python
class DriverEndpoints:
    """Driver 서비스의 모든 DDSTransport를 static으로 생성"""
    def __init__(self, participant: DomainParticipant):
        self.session_start = DDSTransport(participant, "driver/session_start",
                                          DriveSessionRequest, SessionRequestStatus)
        self.session_close = DDSTransport(participant, "driver/session_close",
                                          DriveSessionCloseRequest)       # 단방향
        self.image = DDSTransport(participant, "driver/image_observation",
                                  RolloutCameraImage)                     # 단방향
        self.egomotion = DDSTransport(participant, "driver/egomotion",
                                      RolloutEgoTrajectory)               # 단방향
        self.route = DDSTransport(participant, "driver/route",
                                  RouteRequest)                           # 단방향
        self.ground_truth = DDSTransport(participant, "driver/ground_truth",
                                         GroundTruthRequest)              # 단방향
        self.drive = DDSTransport(participant, "driver/drive",
                                  DriveRequest, DriveResponse)            # 양방향
```

### Phase 2: 클라이언트 측 서비스 마이그레이션

**수정 순서:** Physics → Controller → Driver (복잡도 순)

#### ① `src/runtime/alpasim_runtime/services/physics_service.py`

```python
# 변경 전
class PhysicsService(ServiceBase[PhysicsServiceStub]):
    async def ground_intersection(self, ...):
        response = await profiled_rpc_call(
            "ground_intersection", "physics", self.stub.ground_intersection, request)

# 변경 후
class PhysicsService:
    def __init__(self, participant, skip=False):
        self.endpoints = PhysicsEndpoints(participant) if not skip else None

    async def ground_intersection(self, ...):
        response = await self.endpoints.ground_intersection.request(request)
```

#### ② `src/runtime/alpasim_runtime/services/controller_service.py`

```python
# 변경 전
class ControllerService(ServiceBase[VDCServiceStub]):
    async def _initialize_session(self, session_info, **kwargs):
        await profiled_rpc_call("start_session", "controller", self.stub.start_session, request)

# 변경 후
class ControllerService:
    def __init__(self, participant, skip=False):
        self.endpoints = ControllerEndpoints(participant) if not skip else None

    async def _initialize_session(self, session_info, **kwargs):
        await self.endpoints.session_start.request(request)
```

#### ③ `src/runtime/alpasim_runtime/services/driver_service.py`

```python
# 변경 전
class DriverService(ServiceBase[EgodriverServiceStub]):
    async def submit_image(self, image):
        await profiled_rpc_call("submit_image_observation", "driver",
                                 self.stub.submit_image_observation, request)
    async def drive(self, ...):
        response = await profiled_rpc_call("drive", "driver", self.stub.drive, request)

# 변경 후
class DriverService:
    def __init__(self, participant, skip=False):
        self.endpoints = DriverEndpoints(participant) if not skip else None

    async def submit_image(self, image):
        self.endpoints.image.send(request)          # fire-and-forget

    async def drive(self, ...):
        response = await self.endpoints.drive.request(request)  # 양방향
```

### Phase 3: 서버 측 마이그레이션

서버는 클라이언트의 반대 방향으로 DDSTransport를 구성.
클라이언트가 `req` topic에 write → 서버가 `req` topic을 read → 처리 → `resp` topic에 write.

#### 서버 측 DDSTransport 사용 패턴

```python
class DDSServiceHandler:
    """서버 측 base: request를 읽고, 처리하고, response를 쓰는 루프"""
    def __init__(self, participant, name, req_type, resp_type=None):
        # 클라이언트와 반대: req를 읽고, resp를 쓴다
        self.reader = DataReader(participant, Topic(participant, f"{name}/req", req_type))
        self.writer = (
            DataWriter(participant, Topic(participant, f"{name}/resp", resp_type))
            if resp_type else None
        )

    async def serve(self, handler_fn):
        """요청을 읽고 handler_fn 호출 → 응답 write"""
        while True:
            await self.waitset.wait_async()
            for sample in self.reader.take():
                result = await handler_fn(sample)
                if self.writer and result:
                    result.correlation_id = sample.correlation_id  # 매칭
                    self.writer.write(result)
```

#### 수정 대상 파일

| 서버 | 현재 파일 | 변경 내용 |
|------|----------|----------|
| Driver | `src/driver/src/alpasim_driver/main.py` | gRPC servicer → DDSServiceHandler |
| Controller | `src/controller/alpasim_controller/server.py` | gRPC servicer → DDSServiceHandler |
| Physics | `src/physics/alpasim_physics/server.py` | gRPC servicer → DDSServiceHandler |

#### 기타 수정 대상

| 파일 | 변경 내용 |
|------|----------|
| `src/runtime/alpasim_runtime/validation.py` | Physics의 `get_version`, `get_available_scenes` 검증을 DDS 경유로 변경 (Sensorsim/Traffic 검증은 gRPC 유지) |
| `src/runtime/alpasim_runtime/simulate/__main__.py` | DDS 서비스(Driver, Controller, Physics)의 `shut_down` 호출을 DDSTransport `.send()`로 변경 (Sensorsim은 gRPC 유지) |

---

## QoS 프로필

| 용도 | Reliability | Durability | History |
|------|-------------|------------|---------|
| 양방향 (drive, ground_intersection 등) | RELIABLE | VOLATILE | KEEP_LAST(1) |
| 단방향 (submit_image 등) | RELIABLE | VOLATILE | KEEP_LAST(1) |
| Session 시작 (start_session) | RELIABLE | TRANSIENT_LOCAL | KEEP_LAST(1) |

---

## 메시지 직렬화

**DDS 네이티브 타입으로 새로 정의한다.**

DDS는 자체 직렬화를 수행하므로, protobuf를 DDS 위에 얹는 것은 부적절하다 (이중 직렬화, DDS 기능 활용 불가). 현재 `.proto`에 정의된 메시지 타입을 DDS IDL (또는 Python `@dataclass`) 로 재정의한다.

### 타입 정의 시 추가 필드

모든 양방향 타입의 request/response에 `correlation_id: str` 필드를 추가해야 함.
기존 protobuf에는 없던 필드 (gRPC는 연결 자체가 매칭을 보장했으므로).

```python
# 예: types/egodriver.py
@dataclass
class DriveRequest:
    correlation_id: str     # DDS 전용 — 요청/응답 매칭
    session_uuid: str       # 기존 필드
    time_now_us: int
    time_query_us: int
    renderer_data: bytes

@dataclass
class DriveResponse:
    correlation_id: str     # DDS 전용 — 요청/응답 매칭
    trajectory: Trajectory  # 기존 필드
```

### 타입 정의 위치

```
src/dds/alpasim_dds/types/
├── common.py           # 공통 타입 (Pose, Vec3, DynamicState, Trajectory 등)
├── egodriver.py        # DriveRequest, DriveResponse, RolloutCameraImage 등
├── controller.py       # VDCSessionRequest, RunControllerAndVehicleModelRequest 등
└── physics.py          # PhysicsGroundIntersectionRequest 등
```

### 변환 대상 proto 파일 참조

| DDS 타입 파일 | 원본 proto | 비고 |
|--------------|-----------|------|
| `types/common.py` | `src/grpc/alpasim_grpc/v0/common.proto` | Pose, Vec3, Trajectory 등 |
| `types/egodriver.py` | `src/grpc/alpasim_grpc/v0/egodriver.proto` | Driver 메시지 |
| `types/controller.py` | `src/grpc/alpasim_grpc/v0/controller.proto` | Controller 메시지 |
| `types/physics.py` | `src/grpc/alpasim_grpc/v0/physics.proto` | Physics 메시지 |

### src/grpc와의 관계

```
src/grpc   → Sensorsim, Traffic용 (외부 서비스, gRPC 유지)
src/dds    → Driver, Controller, Physics용 (내부 서비스, DDS 전환)
```

두 패키지는 독립적. 내부 서비스의 protobuf 타입은 DDS 타입으로 대체되므로,
`src/grpc`에서 해당 `.proto` 파일(egodriver, controller, physics)은 점진적으로 제거 가능.
공통 타입(`common.proto`)은 외부 서비스가 여전히 사용하므로 유지.

---

## 테스트 전략

### 기존 테스트 인프라 활용

이 레포에는 이미 3가지 테스트 패턴이 있으며, DDS 마이그레이션에 그대로 활용 가능:

1. **ASL Replay** (`src/runtime/alpasim_runtime/replay_services/`)
   - 녹화된 시뮬레이션 로그(`.asl`)를 재생하면서 요청/응답 일치 여부 검증
   - 서비스별 replay servicer 존재: Driver, Controller, Physics, Traffic, Sensorsim
   - DDS 전환 대상: DriverReplayService, ControllerReplayService, PhysicsReplayService
   - gRPC 유지: SensorsimReplayService, TrafficReplayService

2. **Mock 기반 테스트** (`src/runtime/tests/test_with_mocks.py`)
   - monkeypatch로 서비스 메서드를 교체하는 패턴
   - DDSTransport 메서드도 동일하게 mock 가능

3. **직접 서비스 테스트** (`src/driver/src/alpasim_driver/tests/test_service_flow.py`)
   - 실제 서버를 띄우고 세션 전체 흐름 테스트
   - gRPC 서버 → DDSServiceHandler로 교체 후 동일 시나리오 검증

### Phase별 테스트

#### Phase 1 테스트: DDSTransport 단위 테스트

전체 시뮬레이션 없이, DDS 레이어만 독립 검증:

```python
# test_dds_transport.py
async def test_request_response_roundtrip():
    """양방향 DDSTransport의 request/response 검증"""
    participant = DDSParticipant(domain_id=0)

    client = DDSTransport(participant, "test/drive", TestRequest, TestResponse)
    # 서버 역할 (reader/writer를 직접 구성)
    server_reader = DataReader(participant, Topic(participant, "test/drive/req", TestRequest))
    server_writer = DataWriter(participant, Topic(participant, "test/drive/resp", TestResponse))

    # 비동기로 서버 응답 처리
    async def mock_server():
        await waitset.wait_async()
        for sample in server_reader.take():
            server_writer.write(TestResponse(correlation_id=sample.correlation_id, result="ok"))

    asyncio.create_task(mock_server())
    response = await client.request(TestRequest(data="hello"))
    assert response.result == "ok"

async def test_send_fire_and_forget():
    """단방향 DDSTransport의 send 검증 — reader에서 수신 확인"""
    ...

async def test_correlation_id_matching():
    """여러 요청이 비동기로 올 때 correlation_id로 정확히 매칭되는지"""
    ...

async def test_request_timeout():
    """응답이 없을 때 TimeoutError 발생 확인"""
    ...
```

#### Phase 3 테스트: 서비스별 마이그레이션 검증

각 서비스를 DDS로 전환할 때마다 아래 순서로 테스트:

**① Physics (먼저)**

```python
async def test_physics_dds_matches_grpc():
    """동일 입력에 대해 gRPC 결과와 DDS 결과 비교"""
    grpc_service = PhysicsService(address="localhost:50051")
    dds_service = DDSPhysicsService(participant)

    request_args = make_test_ground_intersection_args()

    grpc_result = await grpc_service.ground_intersection(**request_args)
    dds_result = await dds_service.ground_intersection(**request_args)

    assert grpc_result == dds_result
```

**② Controller**

```python
async def test_controller_session_lifecycle():
    """DDS로 세션 시작 → run_controller_and_vehicle → 세션 종료 흐름"""
    ...

async def test_controller_dds_matches_grpc():
    """gRPC/DDS 결과 비교"""
    ...
```

**③ Driver**

```python
async def test_driver_fire_and_forget_delivery():
    """submit_image 등 4개 fire-and-forget이 서버에 도달하는지"""
    ...

async def test_driver_drive_request_response():
    """drive() request-response 검증"""
    ...

async def test_driver_full_session():
    """세션 시작 → 관측 전달 → drive → 세션 종료 전체 흐름"""
    ...
```

#### Phase 4 테스트: ASL Replay 통합 검증

기존 ASL replay 인프라를 DDS로 교체하여 전체 흐름 검증:

```
기존:  Runtime --gRPC--> ReplayServicer (녹화된 응답 반환) ✓
전환:  Runtime --DDS---> DDSReplayServicer (동일 녹화 응답 반환) ✓
```

동일한 `.asl` 파일, 동일한 검증 로직. 전송 계층만 DDS로 바뀜.

### 최종: 전체 시뮬레이션 (1회)

모든 서비스 마이그레이션 완료 후 실제 시뮬레이션 1회 실행하여 end-to-end 확인.

### 테스트 순서 요약

| 순서 | 대상 | 방법 | 전체 시뮬레이션 필요 |
|------|------|------|:---:|
| 1 | DDSTransport | 단위 테스트 | X |
| 2 | Physics (통신 2개) | gRPC/DDS 결과 비교 | X |
| 3 | Controller (통신 3개) | gRPC/DDS 비교 + 세션 흐름 | X |
| 4 | Driver (통신 7개) | gRPC/DDS 비교 + fire-and-forget 검증 | X |
| 5 | 통합 | ASL Replay (DDS replay servicer) | X |
| 6 | End-to-end | 전체 시뮬레이션 실행 | O |

---

## 변경되지 않는 것

- 시뮬레이션 루프 흐름 (①~⑦ 순서 동일)
- `LogEntry` broadcasting (`session_info.broadcaster.broadcast`)
- `skip` 모드 로직
- Sensorsim / Traffic 서비스 (gRPC 유지)
- `profiled_rpc_call()` 텔레메트리 — DDS 전환 시 제거, 필요시 DDSTransport 래퍼로 나중에 재구현
