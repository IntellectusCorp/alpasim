# Proto 서비스 정의

### EgodriverService
- 파일: `src/grpc/alpasim_grpc/v0/egodriver.proto` (lines 11-21)

| RPC | Line |
|-----|------|
| `start_session(DriveSessionRequest) → SessionRequestStatus` | 12 |
| `close_session(DriveSessionCloseRequest) → Empty` | 13 |
| `submit_image_observation(RolloutCameraImage) → Empty` | 14 |
| `submit_egomotion_observation(RolloutEgoTrajectory) → Empty` | 15 |
| `submit_route(RouteRequest) → Empty` | 16 |
| `submit_recording_ground_truth(GroundTruthRequest) → Empty` | 17 |
| `drive(DriveRequest) → DriveResponse` | 18 |
| `get_version(Empty) → VersionId` | 19 |
| `shut_down(Empty) → Empty` | 20 |

### SensorsimService
- 파일: `src/grpc/alpasim_grpc/v0/sensorsim.proto` (lines 18-28)

| RPC | Line |
|-----|------|
| `render_rgb(RGBRenderRequest) → RGBRenderReturn` | 19 |
| `render_lidar(LidarRenderRequest) → LidarRenderReturn` | 20 |
| `render_aggregated(AggregatedRenderRequest) → AggregatedRenderReturn` | 21 |
| `get_version(Empty) → VersionId` | 22 |
| `get_available_scenes(Empty) → AvailableScenesReturn` | 23 |
| `get_available_cameras(AvailableCamerasRequest) → AvailableCamerasReturn` | 24 |
| `shut_down(Empty) → Empty` | 25 |
| `get_available_trajectories(AvailableTrajectoriesRequest) → AvailableTrajectoriesReturn` | 26 |
| `get_available_ego_masks(Empty) → AvailableEgoMasksReturn` | 27 |

### VDCService (Controller)
- 파일: `src/grpc/alpasim_grpc/v0/controller.proto` (lines 11-19)

| RPC | Line |
|-----|------|
| `get_version(Empty) → VersionId` | 12 |
| `start_session(VDCSessionRequest) → SessionRequestStatus` | 13 |
| `close_session(VDCSessionCloseRequest) → Empty` | 14 |
| `run_controller_and_vehicle(RunControllerAndVehicleModelRequest) → RunControllerAndVehicleModelResponse` | 15-17 |
| `shut_down(Empty) → Empty` | 18 |

### PhysicsService
- 파일: `src/grpc/alpasim_grpc/v0/physics.proto` (lines 10-15)

| RPC | Line |
|-----|------|
| `ground_intersection(PhysicsGroundIntersectionRequest) → PhysicsGroundIntersectionReturn` | 11 |
| `get_version(Empty) → VersionId` | 12 |
| `get_available_scenes(Empty) → AvailableScenesReturn` | 13 |
| `shut_down(Empty) → Empty` | 14 |

### TrafficService
- 파일: `src/grpc/alpasim_grpc/v0/traffic.proto` (lines 10-16)

| RPC | Line |
|-----|------|
| `start_session(TrafficSessionRequest) → SessionRequestStatus` | 11 |
| `close_session(TrafficSessionCloseRequest) → Empty` | 12 |
| `simulate(TrafficRequest) → TrafficReturn` | 13 |
| `get_metadata(Empty) → TrafficModuleMetadata` | 14 |
| `shut_down(Empty) → Empty` | 15 |

### RuntimeService
- 파일: `src/grpc/alpasim_grpc/v0/runtime.proto`

| RPC | Line |
|-----|------|
| `simulate(SimulationRequest) → SimulationReturn` | - |


## 서버 구현 (Server-side Servicer)

### Driver Server
- 파일: `src/driver/src/alpasim_driver/main.py`
- 클래스: `EgodriverServiceServicer`

| RPC 구현 | Lines | 설명 |
|----------|-------|------|
| `start_session()` | 734-757 | Session 객체 생성, 드라이버 모델 초기화 |
| `close_session()` | 760-768 | 세션 종료 |
| `get_version()` | 771-780 | 드라이버 버전 반환 |
| `submit_image_observation()` | 783-808 | 카메라 이미지 저장 |
| `submit_egomotion_observation()` | 809-837 | ego trajectory 추정값 저장 |
| `submit_route()` | 838-856 | 경로 waypoints 저장 |
| `submit_recording_ground_truth()` | 857-867 | ground truth trajectory 저장 |
| `drive()` | 868-1039 | 모델 추론 실행 → trajectory 반환 |
| `shut_down()` | 1040-1050 | graceful shutdown |

서버 설정:
- Line 1063: `server = grpc.aio.server()` (async gRPC 서버 생성)
- Line 1071: `add_EgodriverServiceServicer_to_server(service, server)`
- Line 1074: `server.add_insecure_port(address)`

### Controller Server
- 파일: `src/controller/alpasim_controller/server.py`
- 클래스: `VDCSimService(VDCServiceServicer)` (lines 33-84)

| RPC 구현 | Lines | 설명 |
|----------|-------|------|
| `get_version()` | 45-46 | 컨트롤러 버전 반환 |
| `start_session()` | 48-54 | VDC 세션 초기화 (현재 no-op) |
| `close_session()` | 56-64 | 세션 종료 |
| `run_controller_and_vehicle()` | 66-76 | 차량 동역학 1 timestep 계산 |
| `shut_down()` | 78-84 | graceful shutdown |

서버 설정:
- Line 88: `server = grpc.server(futures.ThreadPoolExecutor(max_workers=1))`
- Line 89: `add_VDCServiceServicer_to_server(VDCSimService(...), server)`
- Line 94: `server.add_insecure_port(address)`

### Physics Server
- 파일: `src/physics/alpasim_physics/server.py`
- 클래스: `PhysicsSimService(PhysicsServiceServicer)` (lines 32-141)

| RPC 구현 | Lines | 설명 |
|----------|-------|------|
| `ground_intersection()` | 69-117 | ego/traffic pose 지면 보정 계산 |
| `get_version()` | 119-126 | 물리 엔진 버전 반환 |
| `get_available_scenes()` | 128-132 | 사용 가능한 scene ID 목록 반환 |
| `shut_down()` | 134-140 | graceful shutdown |

서버 설정:
- Line 184: `server = grpc.server(futures.ThreadPoolExecutor(max_workers=1))`
- Line 195: `add_PhysicsServiceServicer_to_server(service, server)`
- Line 186: `server.add_insecure_port(address)`

### Sensorsim Server
- **이 레포에 서버 구현 없음** (외부 서비스로 관리됨)
- 클라이언트 래퍼만 존재

### Traffic Server
- **이 레포에 서버 구현 없음** (외부 서비스로 관리됨)
- 클라이언트 래퍼만 존재

---

## 기타 RPC 호출 지점

### Validation (서비스 검증)
- 파일: `src/runtime/alpasim_runtime/validation.py`

| RPC 호출 | Line | 설명 |
|----------|------|------|
| `grpc.aio.insecure_channel(addresses[0])` | 33 | 검증용 채널 생성 |
| `stub.get_metadata(Empty(), ...)` | 38 | trafficsim 메타데이터 검증 |
| `stub.get_version(Empty(), ...)` | 43 | 서비스 버전 검증 |
| `grpc.aio.insecure_channel(address)` | 102 | 검증용 채널 생성 |
| `stub.get_metadata(Empty(), ...)` | 107 | trafficsim 메타데이터 검증 |
| `stub.get_available_scenes(Empty(), ...)` | 115 | 사용 가능한 scene 검증 |

### Shutdown (서비스 종료)
- 파일: `src/runtime/alpasim_runtime/simulate/__main__.py`

| RPC 호출 | Line | 설명 |
|----------|------|------|
| `grpc.aio.insecure_channel(address)` | 135 | 종료용 채널 생성 |
| `stub.shut_down(Empty(), timeout=5.0)` | 137 | 각 서비스에 shut_down 전송 |

### Telemetry RPC Wrapper
- 파일: `src/runtime/alpasim_runtime/telemetry/rpc_wrapper.py`
- `profiled_rpc_call()` (lines 80-140): 모든 Runtime 클라이언트의 RPC 호출을 감싸서 지연시간/성공/실패 메트릭 수집

---

## Replay 서비스 구현 (테스트/리플레이용)

ASL 녹화 데이터를 재생하는 mock 서비스 구현들.

### 공통 베이스
- 파일: `src/runtime/alpasim_runtime/replay_services/base_replay_servicer.py`
- 클래스: `BaseReplayServicer` (lines 21-149)
- 공통 메서드: `get_version()` (112-124), `start_session()` (126-129), `close_session()` (131-133), `shut_down()` (135-138), `get_available_scenes()` (140-148)

### DriverReplayService
- 파일: `src/runtime/alpasim_runtime/replay_services/driver_replay_service.py`
- 클래스: `DriverReplayService(BaseReplayServicer, EgodriverServiceServicer)` (lines 23-61)

| RPC 구현 | Lines | 설명 |
|----------|-------|------|
| `drive()` | 31-33 | ASL에서 녹화된 trajectory 반환 |
| `submit_image_observation()` | 35-39 | 이미지 제출 검증 |
| `submit_egomotion_observation()` | 41-45 | egomotion 검증 |
| `submit_route()` | 47-49 | route 검증 |
| `submit_recording_ground_truth()` | 51-55 | ground truth 검증 |

### SensorsimReplayService
- 파일: `src/runtime/alpasim_runtime/replay_services/sensorsim_replay_service.py`
- 클래스: `SensorsimReplayService(BaseReplayServicer, SensorsimServiceServicer)` (lines 22-70)

| RPC 구현 | Lines | 설명 |
|----------|-------|------|
| `render_rgb()` | 30-51 | ASL에서 녹화된 이미지 반환 |
| `get_available_cameras()` | 53-60 | ASL의 카메라 설정 반환 |
| `get_available_trajectories()` | 62-69 | 사용 가능한 trajectory 반환 |

### TrafficReplayService
- 파일: `src/runtime/alpasim_runtime/replay_services/traffic_replay_service.py`
- 클래스: `TrafficReplayService(BaseReplayServicer, TrafficServiceServicer)` (lines 22-46)

| RPC 구현 | Lines | 설명 |
|----------|-------|------|
| `get_metadata()` | 28-39 | ASL의 traffic 메타데이터 반환 |
| `simulate()` | 41-45 | ASL에서 녹화된 traffic 위치 반환 |

### PhysicsReplayService
- 파일: `src/runtime/alpasim_runtime/replay_services/physics_replay_service.py`
- 클래스: `PhysicsReplayService(BaseReplayServicer, PhysicsServiceServicer)` (lines 23-31)

| RPC 구현 | Lines | 설명 |
|----------|-------|------|
| `ground_intersection()` | 29-31 | ASL에서 녹화된 보정 pose 반환 |

### ControllerReplayService
- 파일: `src/runtime/alpasim_runtime/replay_services/controller_replay_service.py`
- 클래스: `ControllerReplayService(BaseReplayServicer, VDCServiceServicer)` (lines 23-35)

| RPC 구현 | Lines | 설명 |
|----------|-------|------|
| `run_controller_and_vehicle()` | 31-35 | ASL에서 녹화된 propagated pose 반환 |

### Replay 테스트 서버 등록
- 파일: `src/runtime/tests/test_runtime_integration_replay.py`

| 등록 | Line | 설명 |
|------|------|------|
| `add_PhysicsServiceServicer_to_server` | 69 | Physics replay 등록 |
| `add_EgodriverServiceServicer_to_server` | 73 | Driver replay 등록 |
| `add_TrafficServiceServicer_to_server` | 77 | Traffic replay 등록 |
| `add_VDCServiceServicer_to_server` | 81 | Controller replay 등록 |
| `add_SensorsimServiceServicer_to_server` | 85 | Sensorsim replay 등록 |
| `server = grpc.server(...)` | 194 | 테스트 서버 생성 |
| `server.add_insecure_port(address)` | 208 | 테스트 포트 바인딩 |

