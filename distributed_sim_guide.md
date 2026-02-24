# Alpasim 분산 시뮬레이션 가이드

## 배경: 서버 분리 이유

Alpasim은 시뮬레이션(sensorsim, physics, runtime, controller)과 Alpamayo 드라이버 추론을 모두 GPU로 수행한다.
단일 서버(4090)에서 전부 돌리면 VRAM이 부족하여, **드라이버 추론만 별도 GPU 서버(Dell Pro Max GB10, ARM)로 분리**하여 운영 중이다.
시작할 때 현재 서버가 어디인지 확인하고 시작.

| 역할 | 서버 | GPU | 아키텍처 |
|------|------|-----|----------|
| 시뮬레이션 (sensorsim, physics, runtime, controller, eval) | Alpasim 서버 | RTX 4090 | x86_64 |
| Alpamayo 드라이버 추론 | Dell Pro Max GB10 | GB10 | ARM |

두 서버는 네트워크로 연결되며, Alpasim 서버의 `generated-network-config.yaml`에서 드라이버 주소를 GB10 서버 IP(`192.168.0.2:6000`)로 지정한다.

---

## 1. Alpasim 서버 설정 (4090, x86_64)

```bash
# alpasim_wizard 사용 전 local env setup
source setup_local_env.sh

# Wizard로 설정 생성
uv run alpasim_wizard +deploy=local \
    wizard.log_dir=$PWD/run_distributed \
    wizard.run_method=NONE \
    wizard.debug_flags.use_localhost=True \
    driver=[ar1,ar1_runtime_configs]
```

이후 설정 파일이 자동으로 생기며, `generated-network-config.yaml`을 수정하여 Alpamayo 드라이버 서버를 바라보게 만든다.

```bash
sed -i "s/driver-0:6000/192.168.0.2:6000/" run_distributed/generated-network-config.yaml
sed -i "s/localhost:6000/192.168.0.2:6000/" run_distributed/generated-network-config.yaml
```

---

## 2. Alpamayo 드라이버 서버 설정 (Dell Pro Max GB10, ARM)

설정파일 생성:

```bash
uv run alpasim_wizard +deploy=local \
    wizard.log_dir=$PWD/run_driver_only \
    wizard.run_method=NONE \
    wizard.debug_flags.use_localhost=True \
    driver=[ar1,ar1_runtime_configs]
```

`/home/int2/Workspace/alpasim/run_driver_only/driver-config.yaml` 주요 설정:
- Alpasim 서버의 `run_distributed/driver-config.yaml`과 **use_cameras 설정이 동일**해야 함
- **port는 6000으로 고정**

```yaml
host: 0.0.0.0
inference:
  context_length: 4
  max_batch_size: 1
  subsample_factor: 1
  use_cameras:
    - camera_cross_left_120fov
    - camera_front_wide_120fov
    - camera_cross_right_120fov
    - camera_front_tele_30fov
log_level: INFO
model:
  checkpoint_path: nvidia/Alpamayo-R1-10B
  device: cuda
  model_type: ALPAMAYO_R1
output_dir: /mnt/output/driver
plot_debug_images: false
port: 6000
route:
  command_distance_threshold: 3.0
  default_command: 2
  min_lookahead_distance: 20.0
  use_waypoint_commands: true
trajectory_optimizer:
  enabled: false
```

---

## 3. 시뮬레이션 실행

Docker Compose를 사용하며, 이미지가 빌드되어 있지 않으면 자동으로 빌드 후 시작한다.

```yaml
# ~/Workspace/alpasim/run_driver_only/docker_compose.yaml
build:
  context: /home/int2/Workspace/alpasim
  dockerfile: Dockerfile
  tags:
    - alpasim-base:0.1.3
```

### 실행 순서 (반드시 드라이버 먼저)

**Step 1) GB10에서 Alpamayo 드라이버 실행:**

```bash
cd /home/int2/Workspace/alpasim/run_driver_only
docker compose --profile sim up driver-0
```

**Step 2) 4090에서 Alpasim 시뮬레이션 실행:**

```bash
# 시뮬레이션 실행
docker compose --profile sim up runtime-0 controller-0 physics-0 sensorsim-0

# 끝나면 평가 실행 (비디오도 생성)
docker compose --profile aggregation up eval-0
```

---

## 4. 시뮬레이션 커스터마이징

설정 파일: `run_distributed/generated-user-config-0.yaml`

### 시뮬레이션 시간 조절

기본 200 step (20초). 1 step = 0.1초 (10Hz).

```yaml
n_sim_steps: 100  # 10초
```

### 카메라 해상도 및 프레임레이트

해상도를 낮춰도 크게 빨라지지는 않았음.

```yaml
cameras:
  camera_front_wide_120fov:
    width: 1920
    height: 1080
    frequency_hz: 10
  camera_front_tele_30fov:
    width: 1920
    height: 1080
    frequency_hz: 10
  camera_cross_left_120fov:
    width: 1920
    height: 1080
    frequency_hz: 10
  camera_cross_right_120fov:
    width: 1920
    height: 1080
    frequency_hz: 10
```

### Scene 변경

기본 제공 Scene은 1개(`clipgt-05bb8212-63e1-40a8-b4fc-3142c0e94646`)뿐이다.
다양한 환경을 테스트하려면 HuggingFace에서 추가 Scene을 다운로드해야 한다.

**HuggingFace NuRec 데이터셋:**
- 저장소: `nvidia/PhysicalAI-Autonomous-Vehicles-NuRec`
- 전체 924개 Scene, 총 약 4.5TB
- 각 Scene은 `.usdz` 파일 (뉴럴 렌더링 가중치 + OpenDRIVE 맵 + 차량 궤적 + 3D 메시)

**Scene 카테고리 (labels.json):**

| 카테고리 | 가능한 값 |
|----------|-----------|
| `behavior` | driving_straight, stop, left_lane_change, right_lane_change, right_turn, left_turn, reverse, unspecified |
| `layout` | straight_road, intersection, underpass, bridge, construction_zone, parking_lot, pedestrian_crossing, ramp, roundabout, railway_crossing, unspecified |
| `road_types` | residential, highways, urban, rural, other, unspecified |
| `weather` | clear/cloudy, rain, fog, unspecified |
| `surface_conditions` | dry, wet, unspecified |
| `lighting` | daytime, nighttime, unspecified |
| `vrus` | True, False (보행자/자전거 등 취약 도로 사용자 존재 여부) |
| `traffic_density` | low, medium, high, unspecified |

**Scene 다운로드:**

`~/Workspace/alpasim/download_scene_by_category.py` (커스텀 스크립트) 사용. HuggingFace 토큰 필요.

```bash
export HF_TOKEN=<토큰>

python3 download_scene_by_category.py \
  --local-dir ./all-usdzs \
  --filter traffic_density=high layout=intersection \
  --max-scenes 1
```

| 옵션 | 설명 |
|------|------|
| `--local-dir` | usdz 저장 경로 (플랫 구조, json 라벨 캐시도 여기에 저장) |
| `--filter` | `카테고리=값` 형식. 여러 개 지정 가능 |
| `--match-mode` | `all`: AND 조건, `any`: OR 조건 (기본: all) |
| `--max-scenes` | 다운로드할 최대 Scene 수 (기본: 1) |
| `--labels-only` | usdz 다운로드 없이 매칭되는 Scene UUID만 출력 |

첫 실행 시 전체 `labels.json`을 다운로드(캐시)하고, 이후에는 캐시된 라벨을 재사용한다.

**다운로드한 Scene 등록:**

```bash
sed -i "s|scene_id: clipgt-.*|scene_id: clipgt-<새로운-scene-id>|" generated-user-config-0.yaml
```

> 주의: `scene_id`의 UUID와 `.usdz` 파일명의 UUID는 다르다. 매핑 관계는 `data/scenes/sim_scenes.csv`에서 확인.

---

## 5. 시뮬레이션 로그 관리

시뮬레이션 결과는 `run_distributed/asl/clipgt-{scene_id}/` 하위에 `.asl` 파일로 저장된다.

- `_complete` 파일이 있는 폴더: 정상 완료
- `_complete` 파일이 없는 폴더: 중단된 불완전한 기록

완료된 시뮬레이션 1회당 약 **400MB**의 로그가 생성되며, 반복 실행 시 누적되므로 불필요한 미완료 기록은 주기적으로 정리한다.
